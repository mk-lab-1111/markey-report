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
import time
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


_last_call_time = [0.0]  # 直近のAPI呼び出し時刻を記録（1分制限対策の間隔調整用）
MIN_INTERVAL = 7  # 各呼び出しの最低間隔（秒）。無料枠の1分制限(RPM)に当たりにくくする


def ask_gemini(client, model, prompt, use_search=False, max_retries=6):
    """Geminiに1回問い合わせる。use_search=Trueで検索グラウンディング有効。
    一時的なエラー（429レート制限 / 503混雑 / 500サーバーエラー）に当たった場合は、
    少し待ってから自動でやり直す。また、呼び出しが立て続けにならないよう最低間隔を空ける。"""
    # 前回の呼び出しから MIN_INTERVAL 秒未満なら、その分だけ待つ
    elapsed = time.time() - _last_call_time[0]
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)

    config = None
    if use_search:
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[grounding_tool])

    import re as _re
    import random as _random
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            _last_call_time[0] = time.time()
            return resp.text.strip()
        except Exception as e:
            last_err = e
            msg = str(e)
            low = msg.lower()
            # 「待てば直る」タイプの一時的エラーかどうかを判定
            is_rate_limit = "429" in msg or "resource_exhausted" in low or "quota" in low
            is_overloaded = ("503" in msg or "500" in msg or "unavailable" in low
                             or "overloaded" in low or "high demand" in low
                             or "internal" in low or "deadline" in low)
            is_transient = is_rate_limit or is_overloaded

            if is_transient and attempt < max_retries - 1:
                if is_rate_limit:
                    # レート制限：長めに待つ（20s, 40s, 60s...）。retryDelayがあれば優先
                    wait = 20 * (attempt + 1)
                    m = _re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", msg)
                    if m:
                        wait = max(wait, int(m.group(1)) + 3)
                    reason = "レート制限"
                else:
                    # 混雑・サーバーエラー：指数的に待つ（10s, 20s, 40s...）＋ランダムなゆらぎ
                    wait = min(10 * (2 ** attempt), 90) + _random.uniform(0, 5)
                    reason = "アクセス集中(503等)"
                print(f"   ⏳ {reason}のため {wait:.0f}秒待って再試行します（{attempt+1}/{max_retries-1}）")
                time.sleep(wait)
                continue
            # 一時的でないエラー、またはリトライ上限に達したら諦める
            raise
    # 全リトライ失敗。検索グラウンディング使用時は、検索なしで再挑戦する（フォールバック）
    if use_search:
        print("   ⚠ 検索付きでは失敗しました。検索なしで再挑戦します...")
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            _last_call_time[0] = time.time()
            return resp.text.strip()
        except Exception:
            pass  # フォールバックも失敗したら元のエラーを投げる
    raise last_err


def main():
    with open(os.path.join(BASE, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = cfg.get("model", "gemini-2.5-flash")
    sender = cfg["sender"]
    today = datetime.date.today().strftime("%Y年%m月%d日")
    year = datetime.date.today().strftime("%Y")
    stamp = datetime.date.today().strftime("%Y%m%d")
    os.makedirs(OUTPUT, exist_ok=True)
    os.makedirs(os.path.join(DOCS, "data"), exist_ok=True)

    print(f"▶ 指定テーマ: {cfg['theme'] or '（未指定・自動探索）'}")

    print("① 情報収集中...")
    research_raw = ask_gemini(
        client, model,
        load_prompt("01_research.txt").format(keywords=cfg.get("keywords", ""), theme=cfg.get("theme", ""), today=today, year=year),
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
        load_prompt("02_report.txt").format(theme=theme, research=research, today=today, year=year),
    )

    print("③ SNS投稿生成中...")
    sns = ask_gemini(client, model, load_prompt("03_sns.txt").format(report=report, year=year))

    print("④ メール文面生成中（3パターン）...")
    # 3つのトーン（丁寧／シンプル／簡潔）でそれぞれ生成する
    # 全メールの末尾に付ける定型の締め文
    EMAIL_CLOSING = (
        "\n\n何かご不明な点やご質問等ございましたら、お気軽にメールにてご返信いただければ幸いです。\n\n"
        "差しつかえがなければ、引き続き有益な時事情報や弊社での成果手法・イベント情報などの"
        "ご共有をさせていただければと思います。\n"
        "成果につながる情報提供を心掛けて参りますので、今後とも何卒宜しくお願い申し上げます。"
    )

    email_patterns = [
        ("v1_polite", "丁寧・関係重視"),
        ("v2_simple", "シンプル・標準"),
        ("v3_summary", "メルマガ・要約型"),
    ]
    email_variants = []
    for tmpl_name, label in email_patterns:
        email_prompt_file = f"04_email_{tmpl_name}.txt"
        if not os.path.exists(os.path.join(PROMPTS, email_prompt_file)):
            # テンプレートが無い場合はv2_simpleで代替
            email_prompt_file = "04_email_v2_simple.txt"
        try:
            email_raw = ask_gemini(
                client, model,
                load_prompt(email_prompt_file).format(theme=theme, report=report),
            )
            v_subject, _, v_body = email_raw.partition("---")
            v_subject = v_subject.replace("SUBJECT:", "").strip() or f"{theme}に関する各社対応事例のご共有"
            email_variants.append({
                "id": tmpl_name,
                "label": label,
                "subject": v_subject,
                "body": v_body.strip() + EMAIL_CLOSING,
            })
            print(f"   ✓ {label} 生成完了")
        except Exception as e:
            print(f"   ⚠ {label} の生成に失敗: {e}")

    # 後方互換：1案目（または最初に成功したもの）を代表として従来フィールドにも入れる
    if email_variants:
        subject = email_variants[0]["subject"]
        email_body = email_variants[0]["body"]
    else:
        subject = f"{theme}に関する各社対応事例のご共有"
        email_body = ""

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
        "email_variants": email_variants,
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

    # --- アーカイブ（過去レポートの蓄積。WEBサイト連携・一覧表示用） ---
    # レポート本文とNotebookLM素材のみを残す（SNS文・メール文は残さない）。
    # 直近 MAX_ARCHIVE 件を超えたら古いものから自動的に削除し、容量が際限なく増えないようにする。
    MAX_ARCHIVE = 30
    archive_path = os.path.join(DOCS, "data", "archive.json")
    archive = []
    if os.path.exists(archive_path):
        try:
            with open(archive_path, encoding="utf-8") as f:
                archive = json.load(f)
            if not isinstance(archive, list):
                archive = []
        except Exception:
            archive = []  # 壊れていた場合は作り直す

    # 同じ日付(stamp)の古いエントリがあれば差し替え、なければ新規追加
    archive = [a for a in archive if a.get("stamp") != stamp]
    archive.append({
        "stamp": stamp,
        "generated_at": manifest["generated_at"],
        "theme": theme,
        "report_text": report,
        "notebooklm_text": notebooklm,
    })
    # 日付の新しい順に並べ替え、MAX_ARCHIVE件まで保持
    archive.sort(key=lambda a: a.get("stamp", ""), reverse=True)
    archive = archive[:MAX_ARCHIVE]

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    print(f"🗂 アーカイブ更新（保持件数: {len(archive)}/{MAX_ARCHIVE}）")

    print("✅ 完了")


if __name__ == "__main__":
    main()
