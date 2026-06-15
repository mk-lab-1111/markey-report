"""
Google連携モジュール（個人Gmailアカウント対応・OAuth版）
Drive保存 + Gmail下書き作成を行う。

【サービスアカウント版との違い】
個人の @gmail.com ではドメイン委任が使えないため、OAuth認証を使う。
初回だけブラウザでログイン承認し、token.json を作る（authorize.py を実行）。
GitHub Actions上では、その token.json の中身を Secret から復元して使う。
"""
import os
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.compose",
]


def _get_credentials():
    """
    認証情報を取得する。優先順位：
    1. 環境変数 GOOGLE_TOKEN（GitHub Actions用。token.jsonの中身）
    2. ローカルの token.json ファイル
    期限切れの場合はリフレッシュトークンで自動更新する。
    """
    creds = None
    token_env = os.environ.get("GOOGLE_TOKEN", "")

    if token_env:
        info = json.loads(token_env)
        creds = Credentials.from_authorized_user_info(info, SCOPES)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        raise RuntimeError(
            "Google認証が見つかりません。先に authorize.py を実行して token.json を作成してください。"
        )
    return creds


def upload_to_drive(file_paths, folder_name, parent_folder_id=""):
    """複数ファイルをDriveの日付フォルダにまとめてアップロード"""
    creds = _get_credentials()
    service = build("drive", "v3", credentials=creds)

    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_folder_id:
        meta["parents"] = [parent_folder_id]
    folder = service.files().create(body=meta, fields="id, webViewLink").execute()
    folder_id = folder["id"]

    links = []
    for path in file_paths:
        media = MediaFileUpload(path, resumable=False)
        f = service.files().create(
            body={"name": os.path.basename(path), "parents": [folder_id]},
            media_body=media,
            fields="id, webViewLink",
        ).execute()
        links.append((os.path.basename(path), f.get("webViewLink", "")))

    return folder.get("webViewLink", ""), links


def create_gmail_draft(subject, body, sender_signature, attachment_path=""):
    """Gmailに下書きを作成する（送信はしない）"""
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    full_body = body.strip() + "\n\n\n" + sender_signature
    message = MIMEMultipart()
    message["subject"] = subject
    message.attach(MIMEText(full_body, "plain", "utf-8"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(attachment_path)}",
        )
        message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return draft.get("id", "")
