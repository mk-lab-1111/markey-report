"""
初回認証スクリプト（最初の1回だけ実行する）

使い方：
1. Google Cloud で OAuth クライアント（デスクトップアプリ）を作成し、
   client_secret.json をこのフォルダに置く
2. このスクリプトを実行：  python authorize.py
3. ブラウザが開くので、m.tsu... のGoogleアカウントでログイン・許可
4. token.json が作られる
5. token.json の中身を GitHub Secret「GOOGLE_TOKEN」に貼り付ける

これで GitHub Actions 上でもあなたのGoogleアカウントとして
Drive保存・Gmail下書き作成ができるようになる。
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.compose",
]


def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.json", "w") as f:
        f.write(creds.to_json())
    print("\n✅ token.json を作成しました。")
    print("   この中身を GitHub Secret『GOOGLE_TOKEN』に貼り付けてください。\n")
    print("--- token.json の中身（ここから下をコピー）---\n")
    print(creds.to_json())


if __name__ == "__main__":
    main()
