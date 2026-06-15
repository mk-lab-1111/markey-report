"""
週次レポート自動生成 - 実行本体
GitHub Actions から呼び出される。基本的に編集不要。
文章の型を変えたい → prompts/ フォルダを編集（またはアプリの編集画面）
今週のテーマを変えたい → config.yaml を編集（またはアプリの設定画面）
"""
import os
import sys
import json
import datetime
import yaml
import google.generativeai as genai

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


def ask_gemini(model, prompt, use_search=False):
    """Geminiに1回問い合わせる。use_search=Trueで検索グラウンディング有効"""
    tools = "google_search_retrieval" if use_search else None
    m = genai.GenerativeModel(model_name=model, tools=tools)
    resp = m.generate_content(prompt)
    return resp.text.strip()


def main():
    with open(os.path.join(BASE, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = cfg.get("model", "gemini-2.0-flash")
    sender = cfg["sender"]
    today = datetime.date.today().strftime("%Y年%m月%d日")
    stamp = datetime.date.today().strftime("%Y%m%d")
    os.makedirs(OUTPUT, exist_ok=True)
    os.makedirs(os.path.join(DOCS, "data"), exist_ok=True)

    print(f"▶ テーマ: {cfg['theme']}")

    print("① 情報収集中...")
    research = ask_gemini(
        model,
        load_prompt("01_research.txt").format(keywords=cfg["keywords"], theme=cfg["theme"]),
        use_search=True,
    )

    print("② レポート生成中...")
    report = ask_gemini(
        model,
        load_prompt("02_report.txt").format(theme=cfg["theme"], research=research, today=today),
    )

    print("③ SNS投稿生成中...")
    sns = ask_gemini(model, load_prompt("03_sns.txt").format(report=report))

    print("④ メール文面生成中...")
    email_raw = ask_gemini(model, load_prompt("04_email.txt").format(theme=cfg["theme"]))
    subject, _, email_body = email_raw.partition("---")
    subject = subject.replace("SUBJECT:", "").strip() or f"{cfg['theme']}に関する各社対応事例のご共有"

    print("⑤ NotebookLM素材生成中...")
    notebooklm = ask_gemini(model, load_prompt("05_notebooklm.txt").format(report=report))

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
        "theme": cfg["theme"],
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
