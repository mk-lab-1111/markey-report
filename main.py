"""
週次レポート自動生成 - 実行本体
GitHub Actions から呼び出される。基本的に編集不要。
文章の型を変えたい → prompts/ フォルダを編集（またはアプリの編集画面）
今週のテーマを変えたい → config.yaml を編集（またはアプリの設定画面）

【重要】google-generativeai は2026年に廃止されたため、
新しい google-genai SDK を使用している。
"""
import os
import sys
import json
import datetime
import yaml
from google import genai
from google.genai import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from report_builder import build_report_docx
from google_utils import upload_to_drive, create_gmail_draft

BASE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(BASE, "prompts")
OUTPUT = os.path.join(BASE, "output")
DOCS = os.path.join(BASE, "docs")  # GitHub Pages（アプリ）が読む場所


def load_prompt(name):
    with open(os.path.join(PROMPTS, name), encoding="utf-8") as f:
        return f.read()


def ask_gemini(client, model, prompt, use_search=False):
    """Geminiに1回問い合わせる。use_search=Trueで検索グラウンディング有効"""
    config = None
    if use_search:
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[grounding_tool])
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return resp.text.strip()


def main():
    with open(os.path.join(BASE, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = cfg.get("model", "gemini-2.5-flash")
    sender = cfg["sender"]
    today = datetime.date.today().strftime("%Y年%m月%d日")
    stamp = datetime.date.today().strftime("%Y%m%d")
    os.makedirs(OUTPUT, exist_ok=True)
    os.makedirs(os.path.join(DOCS, "data"), exist_ok=True)

    print(f"▶ 指定テーマ: {cfg['theme'] or '（未指定・自動探索）'}")

    print("① 情報収集中...")
    research_raw = ask_gemini(
        client, model,
        load_prompt("01_research.txt").format(keywords=cfg.get("keywords", ""), theme=cfg.get("theme", "")),
        use_search=True,
    )

    # 1行目の SELECTED_THEME: ... を抜き出し、今回使うテーマとして確定する
    selected_theme = cfg.get("theme") or ""
    research_lines = research_raw.splitlines()
    if research_lines and research_lines[0].startswith("SELECTED_THEME:"):
        selected_theme = research_lines[0].replace("SELECTED_THEME:", "").strip()
        research = "\n".join(research_lines[1:]).strip()
    else:
        research = research_raw
    theme = selected_theme or "住宅業界の最新動向"
    print(f"   採用テーマ: {theme}")

    print("② レポート生成中...")
    report = ask_gemini(
        client, model,
        load_prompt("02_report.txt").format(theme=theme, research=research, today=today),
    )

    print("③ SNS投稿生成中...")
    sns = ask_gemini(client, model, load_prompt("03_sns.txt").format(report=report))

    print("④ メール文面生成中...")
    email_template_name = cfg.get("email_template", "v2_simple")
    email_prompt_file = f"04_email_{email_template_name}.txt"
    if not os.path.exists(os.path.join(PROMPTS, email_prompt_file)):
        email_prompt_file = "04_email_v2_simple.txt"
    email_raw = ask_gemini(
        client, model,
        load_prompt(email_prompt_file).format(theme=theme, report=report),
    )
    subject, _, email_body = email_raw.partition("---")
    subject = subject.replace("SUBJECT:", "").strip() or f"{theme}に関する各社対応事例のご共有"

    print("⑤ NotebookLM素材生成中...")
    notebooklm = ask_gemini(client, model, load_prompt("05_notebooklm.txt").format(report=report))

    # --- ファイル出力 ---
    docx_path = os.path.join(OUTPUT, f"report_{stamp}.docx")
    build_report_docx(report, sender, docx_path)
    for name, content in [
        (f"sns_{stamp}.txt", sns),
        (f"notebooklm_input_{stamp}.txt", notebooklm),
        (f"email_{stamp}.txt", f"件名: {subject}\n\n{email_body.strip()}"),
    ]:
        with open(os.path.join(OUTPUT, name), "w", encoding="utf-8") as f:
            f.write(content)
    print("📄 ファイル生成完了")

    # --- アプリ表示用データ（マニフェスト）を docs/data に書き出す ---
    manifest = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "theme": theme,
        "report_text": report,
        "sns_text": sns,
        "email_subject": subject,
        "email_body": email_body.strip(),
        "notebooklm_text": notebooklm,
        "stamp": stamp,
        "drive_folder": "",
    }

    signature = (
        "-----------------------------------------------------------------\n"
        f"{sender['company']}\n代表　{sender['name']}\n"
        f"TEL：{sender['tel']}\nMail：{sender['mail']}\nHP：{sender['hp']}"
    )

    if os.environ.get("GOOGLE_TOKEN") or os.path.exists(os.path.join(BASE, "token.json")):
        print("☁ Google Driveへ保存中...")
        try:
            folder_link, _ = upload_to_drive(
                [os.path.join(OUTPUT, f"report_{stamp}.docx"),
                 os.path.join(OUTPUT, f"sns_{stamp}.txt"),
                 os.path.join(OUTPUT, f"notebooklm_input_{stamp}.txt"),
                 os.path.join(OUTPUT, f"email_{stamp}.txt")],
                f"週次レポート_{stamp}",
                cfg.get("drive_folder_id", ""),
            )
            manifest["drive_folder"] = folder_link
            print(f"   フォルダ: {folder_link}")

            print("✉ Gmail下書きを作成中...")
            create_gmail_draft(subject, email_body, signature,
                               attachment_path=os.path.join(OUTPUT, f"report_{stamp}.docx"))
            print("   下書き作成完了")
        except Exception as e:
            print(f"⚠ Google連携でエラー: {e}")
    else:
        print("⚠ Google認証未設定のため、ローカル出力のみ")

    # マニフェストとWordコピーをアプリ用フォルダへ
    with open(os.path.join(DOCS, "data", "latest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    import shutil
    shutil.copy(docx_path, os.path.join(DOCS, "data", f"report_{stamp}.docx"))

    print("✅ 完了")


if __name__ == "__main__":
    main()
