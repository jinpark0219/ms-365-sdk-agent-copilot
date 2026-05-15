# 社内アシスタント Agent (HR + IT)

Microsoft 365 Agents SDK (Python) と Azure AI Foundry を使用した、社内文書 (HR規程・ITヘルプデスク) を対象とした RAG チャットボットです。Microsoft 365 Agents Playground でローカル起動・動作確認する手順を説明します。

将来的には Copilot Studio の co-agent として接続することを想定しています。

## 目次

1. [前提条件](#前提条件)
2. [リポジトリのクローン](#リポジトリのクローン)
3. [Azure AI Foundry のセットアップ](#azure-ai-foundry-のセットアップ)
4. [セットアップ (初回のみ)](#セットアップ-初回のみ)
5. [ローカル起動](#ローカル起動)
6. [動作確認](#動作確認)
7. [ナレッジ文書の更新](#ナレッジ文書の更新)
8. [プロジェクト構成](#プロジェクト構成)
9. [アーキテクチャ](#アーキテクチャ)
10. [コードを修正したときの反映方法](#コードを修正したときの反映方法)
11. [よくあるトラブル](#よくあるトラブル)
12. [今後の拡張予定](#今後の拡張予定)

---

## 前提条件

以下のツールが PC にインストールされていることを確認してください。

| ツール | 推奨バージョン | 確認コマンド |
| --- | --- | --- |
| Python | 3.11 (3.9 ~ 3.11 対応) | `python --version` |
| Git | 任意 | `git --version` |
| Node.js | v22 以上 (Playground 用) | `node --version` |
| Azure サブスクリプション | 個人/会社いずれか可 | Azure ポータルにログイン |

Microsoft 365 Agents SDK の Python 対応バージョンは **3.9 ~ 3.11** です。Python 3.12 以上では未サポートのためご注意ください。

---

## リポジトリのクローン

```powershell
gh repo clone jinpark0219/ms-365-sdk-agent-copilot
cd ms-365-sdk-agent-copilot
```

GitHub CLI を使用しない場合:

```powershell
git clone https://github.com/jinpark0219/ms-365-sdk-agent-copilot.git
cd ms-365-sdk-agent-copilot
```

---

## Azure AI Foundry のセットアップ

Azure AI Foundry でチャットモデルと埋め込みモデルをデプロイし、エンドポイントと API キーを取得します。

### 1. プロジェクトの作成

1. [Azure AI Foundry ポータル](https://ai.azure.com/) にアクセスします。
2. 新しい Project を作成します (推奨リージョン: Japan East)。
3. 作成完了後、左メニューの **Models + Endpoints** を開きます。

### 2. モデルのデプロイ

以下の2つのモデルをデプロイします。

| 用途 | モデル | デプロイ名の例 |
| --- | --- | --- |
| チャット | `gpt-4o-mini` | `gpt-4o-mini` |
| 埋め込み (RAG用) | `text-embedding-3-small` | `text-embedding-3-small` |

### 3. エンドポイントとキーの取得

**Models + Endpoints** からデプロイしたモデルを開き、以下の値を控えておきます。

- エンドポイント URL (例: `https://<your-resource>.services.ai.azure.com/`)
- API キー (Key 1 または Key 2)
- 各モデルのデプロイ名

---

## セットアップ (初回のみ)

### 1. Python 仮想環境の作成

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

PowerShell の実行ポリシーエラーが出る場合は、以下を一度だけ実行してください。

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**macOS / Linux:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 2. 依存パッケージのインストール

```powershell
pip install -r requirements.txt
```

### 3. 環境変数ファイルの作成

`.env.example` をコピーして `.env` を作成し、Foundry から取得した値を設定します。

```powershell
copy .env.example .env
notepad .env
```

設定する項目:

```ini
AZURE_OPENAI_ENDPOINT=https://<your-resource>.services.ai.azure.com
AZURE_OPENAI_API_KEY=<Foundry で発行されたキー>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=<チャットモデルのデプロイ名>
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<埋め込みモデルのデプロイ名>
```

> ⚠️ `.env` は `.gitignore` 対象です。API キーをリポジトリにコミットしないようご注意ください。

### 4. ナレッジ文書のインデックス構築

`sample-docs/` 配下のマークダウン文書をチャンキング・埋め込み生成・FAISS インデックス化します。

```powershell
python build_index.py
```

実行後、以下のような出力が表示されます。

```
📂 対象文書: 2 件
  - hr-policy-guide-ja.md: 46 チャンク
  - it-helpdesk-guide-ja.md: 32 チャンク
📦 合計チャンク数: 78
🔢 埋め込み生成 + FAISS インデックス構築中...
🔍 FAISS インデックス構築完了: 78 ベクトル
💾 保存完了: index/ (index.faiss + index.pkl)
```

`index/` フォルダが作成され、`index.faiss` と `index.pkl` が保存されます。

---

## ローカル起動

```powershell
python app.py
```

起動成功時、以下のように表示されます。

```
======== Running on http://localhost:3978 ========
(Press CTRL+C to quit)
```

停止する場合は `Ctrl+C` で終了します (`Ctrl+Z` は一時停止のためポートが解放されないので注意)。

---

## 動作確認

### Microsoft 365 Agents Playground の起動

別ターミナルで以下を実行します (初回のみ npm install)。

```powershell
npm install -g @microsoft/teams-app-test-tool
teamsapptester
```

ブラウザが自動的に開き、`http://localhost:56150` の Playground UI に接続されます。

### 動作確認用の質問例

| 質問 | 期待する動作 |
| --- | --- |
| `年休は何日もらえますか?` | HR 規程の「1.1 年次有給休暇」セクションを参照して回答 |
| `VPNが繋がりません` | IT ヘルプデスクの「5.2 VPN (社外接続)」を参照して回答 |
| `ハラスメント相談したい` | 「11. 緊急相談窓口」(内線 2099) を案内 |
| `/help` | 案内メッセージ |
| `今日の天気は?` | コンテキストに該当情報がない旨を案内 |

回答には参照した社内文書のセクション名 (出典) が末尾に表示されます。

---

## ナレッジ文書の更新

`sample-docs/` 配下のマークダウン文書を編集・追加した場合は、インデックスを再構築する必要があります。

```powershell
python build_index.py
```

再構築後、`python app.py` を再起動するとインデックスが反映されます。

> 💡 文書を追加するだけの場合も再構築は必須です (差分インデックスは未対応)。

---

## プロジェクト構成

```
ms-365-sdk-agent-copilot/
├── app.py                      # M365 Agents SDK エントリポイント
├── start_server.py             # aiohttp サーバ起動 (ポート 3978)
├── rag.py                      # FAISS インデックス検索ロジック
├── build_index.py              # ナレッジ文書のチャンキング・インデックス化スクリプト
├── requirements.txt            # Python 依存パッケージ
├── .env.example                # 環境変数テンプレート
├── .env                        # 環境変数 (git 管理外)
├── .gitignore
├── sample-docs/                # ナレッジ文書 (マークダウン)
│   ├── hr-policy-guide-ja.md   # HR 規程ガイド
│   └── it-helpdesk-guide-ja.md # IT ヘルプデスクガイド
└── index/                      # FAISS インデックス (git 管理外、build_index.py で生成)
    ├── index.faiss
    └── index.pkl
```

---

## アーキテクチャ

```
[ユーザー]
    ↓ 日本語質問
[Microsoft 365 Agents Playground (localhost:56150)]
    ↓ POST /api/messages
[aiohttp サーバ (localhost:3978)]
    ↓ ルーティング
[M365 Agents SDK (AgentApplication)]
    ↓
[rag.py: FAISS 類似検索 (LangChain)]
    ↓ 上位5件のチャンク + メタデータ
[Azure OpenAI / Foundry: gpt-4o-mini]
    ↓ システムプロンプト + コンテキスト + 質問
[ユーザーへ回答 (出典付き)]
```

### 主な技術スタック

| 層 | 使用技術 |
| --- | --- |
| エージェントフレームワーク | Microsoft 365 Agents SDK (`microsoft-agents-hosting-aiohttp`) |
| Web サーバ | aiohttp |
| LLM | Azure OpenAI / Foundry (`gpt-4o-mini`) |
| 埋め込み | Azure OpenAI / Foundry (`text-embedding-3-small`) |
| ベクトル検索 | FAISS (LangChain `langchain-community.vectorstores.FAISS`) |
| チャンキング | LangChain `MarkdownHeaderTextSplitter` (H2/H3 単位) |
| テスト UI | Microsoft 365 Agents Playground (`@microsoft/teams-app-test-tool`) |

---

## コードを修正したときの反映方法

aiohttp はデフォルトでホットリロードに対応していません。コード変更後はサーバを再起動してください。

| 変更内容 | 必要な操作 |
| --- | --- |
| `app.py` / `rag.py` / `start_server.py` の編集 | `Ctrl+C` で停止後、`python app.py` で再起動 |
| `sample-docs/` 配下の文書追加・編集 | `python build_index.py` → `python app.py` 再起動 |
| `requirements.txt` の変更 | `pip install -r requirements.txt` → `python app.py` 再起動 |
| `.env` の変更 | `python app.py` 再起動のみ |

---

## よくあるトラブル

### ポート 3978 がすでに使われている

`Ctrl+Z` で誤って一時停止した場合に発生しがちです。以下で残存プロセスを終了します。

**Windows (PowerShell):**

```powershell
Get-NetTCPConnection -LocalPort 3978 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
```

**macOS / Linux:**

```bash
lsof -ti:3978 | xargs kill -9
```

### `AttributeError: 'NoneType' object has no attribute 'ANONYMOUS_ALLOWED'`

公式サンプル由来の既知の問題です。本リポジトリではすでに `AgentAuthConfiguration(anonymous_allowed=True)` を渡すよう修正済みです。古いコードを使用している場合は `app.py` の `start_server` 呼び出しを確認してください。

### `api-version query parameter is not allowed when using /v1 path`

`AZURE_OPENAI_ENDPOINT` に Foundry の Responses API パス (`/openai/v1/responses` 付き) を設定すると発生します。エンドポイントは以下のいずれかの形式に修正してください。

- `https://<your-resource>.services.ai.azure.com`
- `https://<your-resource>.openai.azure.com/`

### Playground 接続後にメッセージが届かない

`python app.py` を起動し直しても改善しない場合は、Playground のブラウザタブをリロードしてください (`teamsapptester` 自体の再起動は不要)。

### `faiss-cpu` のインストールエラー (Windows)

```powershell
pip install faiss-cpu --no-cache-dir
```

それでも失敗する場合は Python のバージョンを確認してください (3.11 推奨)。

---

## 今後の拡張予定

PoC 段階につき、以下は今後の対応予定です。

| 項目 | 状態 |
| --- | --- |
| Azure App Service への本番デプロイ | 未対応 |
| Entra ID 認証 (`anonymous_allowed=False`) への切り替え | 未対応 |
| Azure Bot Service への登録 | 未対応 |
| Copilot Studio への co-agent 登録 | 未対応 |
| 部署・役職に基づくドキュメント権限フィルタリング | 未対応 |
| 構造化ログ (Application Insights 連携) | 未対応 |
| RAG スコアしきい値による無関連質問のガード | 未対応 |
| マルチターン会話メモリ | 未対応 |
| AWS 側エージェントとの A2A 連携 | 別チーム担当 |

---

*本ドキュメントは 2026年5月版です。*
