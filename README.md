# MARKEY 週次レポート自動生成システム

住宅会社向けに、時事情報をもとにした4点セットを **火・金の朝7時に自動生成**します。
専用のダッシュボードアプリ（ブラウザ）で確認・修正・微調整ができます。すべてGemini無料枠で動くため**ランニングコストは¥0**です。

生成される4点：
1. Wordレポート（A4縦・各社対応事例）
2. X投稿文（3パターン）
3. クライアント用メール（Gmail下書き）
4. NotebookLM用インフォグラフィック素材

---

## 全体の仕組み

```
[GitHub Actions] 火・金 朝7時に自動起動
      ↓ Geminiで4点生成
      ↓ Google Driveに保存 / Gmailに下書き作成
      ↓ 生成データをアプリ(docs)に反映
[ダッシュボードアプリ] ブラウザで確認・修正・今すぐ生成
      ↓
[あなた] 確認 → 修正 → 宛名入れて送信（約30分）
```

**重要：自動では誰にも送信・投稿されません。** メールは下書きまで、SNSは文章生成まで。送信・投稿は必ずあなたの操作を挟みます。

---

## ファイル構成

```
markey-report/
├── config.yaml              今週のテーマ（アプリの設定画面からも変更可）
├── prompts/                 文章の型（アプリの編集画面からも変更可）
│   ├── 01_research.txt
│   ├── 02_report.txt
│   ├── 03_sns.txt
│   ├── 04_email.txt
│   └── 05_notebooklm.txt
├── main.py                  実行本体
├── authorize.py             初回Google認証用（1回だけ実行）
├── scripts/
│   ├── report_builder.py    Word生成
│   └── google_utils.py      Drive保存・Gmail下書き（OAuth版）
├── docs/                    ダッシュボードアプリ（GitHub Pagesで公開）
│   ├── index.html
│   └── data/                生成データ（自動更新される）
├── requirements.txt
└── .github/workflows/weekly-report.yml
```

---

## 初回セットアップ（一度だけ）

### STEP 1. GitHubリポジトリを作る
このフォルダ一式を新規リポジトリ（private可）にアップロード。

### STEP 2. Gemini APIキーを取得
https://aistudio.google.com/apikey で「Create API key」（無料）。

### STEP 3. Google認証（Drive保存・Gmail下書き用）
個人Gmailのため、OAuth認証を使います。

1. https://console.cloud.google.com でプロジェクト作成
2. 「APIとサービス」→ ライブラリ → **Google Drive API** と **Gmail API** を有効化
3. 「OAuth同意画面」を設定（外部・テストユーザーに自分のGmailを追加）
4. 「認証情報」→ OAuthクライアントID作成 → 種類は**デスクトップアプリ** → JSONをダウンロードし `client_secret.json` という名前でこのフォルダに置く
5. ターミナルで初回認証を実行：
   ```bash
   pip install -r requirements.txt
   cd scripts && cp ../client_secret.json . && python ../authorize.py
   ```
   ブラウザが開くので m.tsu... のアカウントでログイン・許可
6. 表示された `token.json` の中身をコピー

### STEP 4. GitHub Secretsに登録
リポジトリの Settings → Secrets and variables → Actions → New repository secret：

| Secret名 | 中身 |
|---|---|
| `GEMINI_API_KEY` | STEP2のキー |
| `GOOGLE_TOKEN` | STEP3でコピーした token.json の中身（全部） |

### STEP 5. ダッシュボードアプリを公開（GitHub Pages）
1. リポジトリの Settings → Pages
2. Source を「Deploy from a branch」、Branch を `main` / フォルダを `/docs` に設定して保存
3. 数分後 `https://(ユーザー名).github.io/(リポジトリ名)/` でアプリが開く

### STEP 6. アプリの接続設定
1. 公開されたアプリURLを開く（スマホでもOK。ブックマーク推奨）
2. 左メニュー「接続設定」を開く
3. GitHubユーザー名・リポジトリ名・個人アクセストークンを入力
   - トークンは GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens で発行
   - 対象リポジトリに対し **Contents: Read and write** と **Actions: Read and write** を許可
4. 「接続テスト」→ 成功すれば完了

これで全自動で回り始めます。

---

## 毎週の運用

1. （任意）アプリの「今週のテーマ設定」で次回テーマを入力 → 保存
2. 火・金 朝7時に自動生成 → アプリのダッシュボードに反映、Driveに保存、Gmailに下書き
3. あなたの作業（約30分）
   - レポートを確認、必要なら「修正モード」で直して「Wordで保存」
   - メール下書きに宛名を入れて送信
   - SNS文をコピーしてXに投稿
   - NotebookLM素材をコピーしてNotebookLMでインフォグラフィック生成

---

## 文章の型を変えるには

アプリの「文章の型を編集」画面で書き換えて保存すれば、次回以降の自動生成に反映されます（コード不要）。
ローカルで `prompts/` を直接編集してもOKです。

---

## コスト

| 項目 | 費用 |
|---|---|
| GitHub Actions / Pages | 無料 |
| Gemini API | 無料枠内 |
| Google Drive / Gmail API | 無料 |
| **合計** | **¥0 / 月** |
