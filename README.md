# 社内アシスタント Agent (HR + IT)

Microsoft 365 Agents SDK (Python) と Azure AI Foundry を使用した、社内文書 (HR規程・ITヘルプデスク) を対象とした RAG チャットボットです。

- **ローカル**: Microsoft 365 Agents Playground で動作確認
- **クラウド**: Azure App Service にデプロイし、Azure Bot Service 経由で Web Chat / Teams / Copilot Studio から利用

将来的には Copilot Studio の co-agent として接続することを想定しています。

## 目次

1. [前提条件](#前提条件)
2. [リポジトリのクローン](#リポジトリのクローン)
3. [Azure AI Foundry のセットアップ](#azure-ai-foundry-のセットアップ)
4. [ローカル開発](#ローカル開発)
5. [Azure へのデプロイ](#azure-へのデプロイ)
6. [動作確認用の質問例](#動作確認用の質問例)
7. [ナレッジ文書の更新](#ナレッジ文書の更新)
8. [プロジェクト構成](#プロジェクト構成)
9. [アーキテクチャ](#アーキテクチャ)
10. [よくあるトラブル](#よくあるトラブル)
11. [今後の拡張予定](#今後の拡張予定)

---

## 前提条件

以下のツールが PC にインストールされていることを確認してください。

| ツール | 推奨バージョン | 確認コマンド |
| --- | --- | --- |
| Python | 3.11 (3.9 ~ 3.11 対応) | `python --version` |
| Git | 任意 | `git --version` |
| Node.js | v22 以上 (ローカル Playground 用) | `node --version` |
| Azure サブスクリプション | Pay-as-you-go 推奨 | Azure ポータルにログイン |

Microsoft 365 Agents SDK の Python 対応バージョンは **3.9 ~ 3.11** です。Python 3.12 以上では未サポートのためご注意ください。

> **注意**: Azure Free Trial サブスクリプションは VM クォータが 0 のため、App Service の作成に失敗します。Pay-as-you-go へのアップグレードが必須です ($200 クレジットは保持されます)。

---

## リポジトリのクローン

```powershell
git clone https://github.com/CollabCentralOrganization/m365-copilot-agent.git
cd m365-copilot-agent
```

GitHub CLI を使用する場合:

```powershell
gh repo clone CollabCentralOrganization/m365-copilot-agent
cd m365-copilot-agent
```

---

## Azure AI Foundry のセットアップ

Azure AI Foundry でチャットモデルと埋め込みモデルをデプロイし、エンドポイントと API キーを取得します。

### 1. プロジェクトの作成

1. [Azure AI Foundry ポータル](https://ai.azure.com/) にアクセス
2. 新しい Project を作成 (推奨リージョン: Japan East)
3. 作成完了後、左メニューの **Models + Endpoints** を開く

### 2. モデルのデプロイ

以下の 2 つのモデルをデプロイします。

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

## ローカル開発

### 1. Python 仮想環境の作成

PowerShell で以下を実行します。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> **注意**: システムに Python 3.12 など複数バージョンが混在する場合は、必ず `py -3.11` で 3.11 を明示してください。`python -m venv` だけだと既定バージョンで venv が作成され、SDK が正しく動作しない可能性があります。

PowerShell の実行ポリシーエラーが出る場合は、以下を一度だけ実行してください。

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

活性化の確認 (`Python 3.11.x` と表示されること):

```powershell
python --version
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

最低限設定すべき項目:

```ini
AZURE_OPENAI_ENDPOINT=https://<your-resource>.services.ai.azure.com
AZURE_OPENAI_API_KEY=<Foundry で発行されたキー>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=<チャットモデルのデプロイ名>
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<埋め込みモデルのデプロイ名>
```

Entra ID / Bot Service と接続する場合は以下も設定 (ローカル Playground のみなら空欄可):

```ini
CLIENT_ID=<Entra ID で登録したアプリケーション ID>
CLIENT_SECRET=<同アプリで発行したシークレットの "値">
TENANT_ID=<Entra ID のテナント ID>
```

社内向けの fallback 連絡先 (該当情報がない時の案内):

```ini
HR_CONTACT=HR: 内線2001
IT_CONTACT=IT: 内線1234
```

> **注意**: `.env` は `.gitignore` 対象です。API キー・シークレットをリポジトリにコミットしないよう注意してください。

### 4. ナレッジ文書のインデックス構築

`sample-docs/` 配下のマークダウン文書をチャンキング・埋め込み生成・FAISS インデックス化します。

```powershell
python build_index.py
```

実行後、以下のような出力が表示されます。

```
対象文書: 2 件
  - hr-policy-guide-ja.md: 46 チャンク
  - it-helpdesk-guide-ja.md: 32 チャンク
合計チャンク数: 78
埋め込み生成 + FAISS インデックス構築中...
FAISS インデックス構築完了: 78 ベクトル
保存完了: index/ (index.faiss + index.pkl)
```

### 5. サーバ起動

```powershell
python app.py
```

起動成功時:

```
======== Running on http://0.0.0.0:3978 ========
```

停止する場合は `Ctrl+C` で終了します (`Ctrl+Z` は一時停止のためポートが解放されないので注意)。

### 6. Microsoft 365 Agents Playground でテスト

別ターミナルで以下を実行 (初回のみ `npm install -g`):

```powershell
npm install -g @microsoft/teams-app-test-tool
teamsapptester
```

ブラウザが自動的に開き、`http://localhost:56150` の Playground UI に接続されます。

---

## Azure へのデプロイ

ローカル動作確認後、Azure へデプロイする手順です。

### 全体の流れ

```
1. Entra ID アプリ登録              (Client ID / Secret / Tenant ID 発行)
2. Azure App Service 作成 + デプロイ (GitHub Actions 経由)
3. 環境変数の登録                    (App Service の Configuration)
4. Azure Bot Service 作成 + 接続    (Messaging endpoint 設定)
5. Web Chat で動作確認              (Test in Web Chat)
```

詳細手順と試行錯誤の記録は [`DEPLOYMENT_JOURNAL_20260518.md`](./DEPLOYMENT_JOURNAL_20260518.md) を参照してください。

### App Service 必須環境変数

オリジナルの `.env` の値に加え、Azure 側で以下を**必ず**設定します:

| 変数名 | 値 | 役割 |
| --- | --- | --- |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` | `pip install` を自動実行 |
| `WEBSITE_RUN_FROM_PACKAGE` | `0` | zstd 圧縮を解除し wwwroot に直接配置 |
| `WEBSITES_PORT` | `8000` | ゲートウェイのポートルーティング |
| `PYTHONUNBUFFERED` | `1` | Python stdout のバッファリングを無効化 (ログ即時出力) |

### App Service 起動コマンド

```
python build_index.py && python app.py
```

(App Service > Configuration > General Settings > Startup Command に設定)

---

## 動作確認用の質問例

| 質問 | 期待する動作 |
| --- | --- |
| `年休は何日もらえますか?` | HR 規程の「1.1 年次有給休暇」セクションを参照して回答 |
| `VPNが繋がりません` | IT ヘルプデスクの「5.2 VPN (社外接続)」を参照して回答 |
| `リモートワーク時のセキュリティ要件を教えてください` | IT「6.3 セキュリティ要件」をマルチドキュメント検索 |
| `今月の給与振込日はいつですか？` | 該当情報がない旨と `.env` の連絡先を案内 (fallback 動作確認) |
| `/help` | 案内メッセージ |

回答には参照した社内文書のセクション名 (出典) が末尾に表示されます。

---

## ナレッジ文書の更新

`sample-docs/` 配下のマークダウン文書を編集・追加した場合は、インデックスを再構築する必要があります。

```powershell
python build_index.py
```

再構築後、`python app.py` を再起動するとインデックスが反映されます。

> **注意**: 文書を追加するだけの場合も再構築は必須です (差分インデックスは未対応)。

---

## プロジェクト構成

```
ms-365-sdk-agent-copilot/
├── app.py                          # M365 Agents SDK エントリポイント
├── start_server.py                 # aiohttp サーバ起動
├── rag.py                          # FAISS インデックス検索ロジック
├── build_index.py                  # ナレッジ文書のチャンキング・インデックス化スクリプト
├── requirements.txt                # Python 依存パッケージ
├── .env.example                    # 環境変数テンプレート
├── .env                            # 環境変数 (git 管理外)
├── .gitignore
├── README.md                       # 本ドキュメント
├── DEPLOYMENT_JOURNAL_20260518.md  # Azure デプロイ作業日誌 (試行錯誤含む)
├── TECHNICAL_DECISIONS.md          # 技術選定の根拠
├── sample-docs/                    # ナレッジ文書 (マークダウン)
│   ├── hr-policy-guide-ja.md       # HR 規程ガイド (サンプル)
│   └── it-helpdesk-guide-ja.md     # IT ヘルプデスクガイド (サンプル)
└── index/                          # FAISS インデックス (git 管理外、build_index.py で生成)
    ├── index.faiss
    └── index.pkl
```

---

## アーキテクチャ

### ローカル開発時

```
[ユーザー]
    ↓ 日本語質問
[M365 Agents Playground (localhost:56150)]
    ↓ POST /api/messages
[aiohttp サーバ (localhost:3978)]
    ↓
[M365 Agents SDK (AgentApplication)]
    ↓
[rag.py: FAISS 類似検索]
    ↓ 上位 5 件のチャンク
[Azure OpenAI / Foundry: gpt-4o-mini]
    ↓
[ユーザーへ回答 (出典付き)]
```

### Azure 本番デプロイ時

```
[ユーザー]
    ↓
[Azure Bot Service (Web Chat / Teams / Copilot Studio)]
    ↓ HTTPS + JWT (Entra ID で署名)
[Azure App Service]
    ├─ JWT 検証ミドルウェア (cryptography で RS256 署名検証)
    ├─ MsalConnectionManager (outbound token 発行)
    ├─ RAG 検索
    └─ Azure OpenAI / Foundry 呼び出し
        ↓
[ユーザーへ回答]
```

### 主な技術スタック

| 層 | 使用技術 |
| --- | --- |
| エージェントフレームワーク | Microsoft 365 Agents SDK (`microsoft-agents-hosting-aiohttp`) |
| 認証 (inbound) | Entra ID OAuth 2.0 + JWT (PyJWT + cryptography) |
| 認証 (outbound) | `MsalConnectionManager` (`microsoft-agents-authentication-msal`) |
| Web サーバ | aiohttp |
| LLM | Azure OpenAI / Foundry (`gpt-4o-mini`) |
| 埋め込み | Azure OpenAI / Foundry (`text-embedding-3-small`) |
| ベクトル検索 | FAISS (`langchain-community.vectorstores.FAISS`) |
| チャンキング | LangChain `MarkdownHeaderTextSplitter` (H2/H3 単位) |
| ホスティング | Azure App Service (Linux, Python 3.11) |
| デプロイ | GitHub Actions |
| チャネル | Azure Bot Service (Web Chat / Teams / Copilot Studio) |

---

## よくあるトラブル

### ローカル開発

**ポート 3978 がすでに使われている**

`Ctrl+Z` で誤って一時停止した場合に発生しがちです。

```powershell
Get-NetTCPConnection -LocalPort 3978 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
```

**`api-version query parameter is not allowed when using /v1 path`**

`AZURE_OPENAI_ENDPOINT` に Responses API パス (`/openai/v1/responses`) が含まれていると発生します。以下のいずれかの形式に修正してください。

- `https://<your-resource>.services.ai.azure.com`
- `https://<your-resource>.openai.azure.com/`

**`openai.OpenAIError: Missing credentials`**

`build_index.py` 実行時に発生する場合、`.env` ファイルに値が入っていない可能性があります。`.env.example` をコピーしただけでは値が空のままです。

**`faiss-cpu` のインストールエラー (Windows)**

```powershell
pip install faiss-cpu --no-cache-dir
```

それでも失敗する場合は Python 3.11 を使用してください。

**Playground 接続後にメッセージが届かない**

`python app.py` 再起動後、Playground のブラウザタブをリロードしてください (`teamsapptester` 自体の再起動は不要)。

### Azure デプロイ

`DEPLOYMENT_JOURNAL_20260518.md` の「主要な試行錯誤」セクションを参照してください。代表的なエラーパターン:

| エラーメッセージ | 原因 | 対応 |
| --- | --- | --- |
| `Operation cannot be completed without additional quota` | サブスクリプションの VM クォータ不足 | Pay-as-you-go へアップグレード |
| `can't open file '/home/site/wwwroot/build_index.py'` | zstd 圧縮が解除されていない | `WEBSITE_RUN_FROM_PACKAGE=0` を追加 |
| コンテナ無限再起動 + ログ無し | stdout バッファリング + ポート未認識 | `PYTHONUNBUFFERED=1` + `WEBSITES_PORT=8000` |
| `MissingCryptographyError` | PyJWT が署名検証ライブラリを認識できない | `cryptography>=42.0.0` を `requirements.txt` に追加 |
| `Invalid audience: <GUID>` | `AgentAuthConfiguration` に `client_id` 未指定 | `client_id` / `client_secret` / `tenant_id` を渡す |
| `'NoneType' object has no attribute 'get_token_provider'` | `CloudAdapter` の `connection_manager` 未注入 | `microsoft-agents-authentication-msal` を導入し `MsalConnectionManager` を渡す |

### Python バージョン

**Python 3.12 以上を使用していて 3.11 に切り替えたい**

```powershell
winget install Python.Python.3.11

# 既存の .venv を削除
Remove-Item -Recurse -Force .venv

# 3.11 で venv 再作成
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version    # Python 3.11.x

pip install -r requirements.txt
```

`py --list` で利用可能なバージョン一覧を確認できます。

---

## 今後の拡張予定

| 項目 | 状態 |
| --- | --- |
| Azure App Service への本番デプロイ | ✅ 完了 |
| Entra ID 認証 (`anonymous_allowed=False`) への切り替え | ✅ 完了 |
| Azure Bot Service への登録 | ✅ 完了 |
| Web Chat での日本語動作検証 | ✅ 完了 |
| 実際の社内ドキュメントへの差し替え | 🔲 未着手 |
| Teams チャネル有効化 | 🔲 未着手 (M365 Admin 連携必要) |
| Copilot Studio への co-agent 登録 | 🔲 未着手 (M365 Copilot ライセンス必要) |
| 部署・役職に基づくドキュメント権限フィルタリング | 🔲 未着手 |
| Application Insights 連携・構造化ログ | 🔲 未着手 |
| RAG スコアしきい値による無関連質問のガード | 🔲 未着手 |
| マルチターン会話メモリ | 🔲 未着手 |
| AWS 側エージェントとの A2A 連携 | 🔲 別チーム担当 |
| FAISS → Azure AI Search 移行 (大規模化時) | 🔲 未着手 |

---

*本ドキュメントは 2026年5月18日時点の構成を反映しています。*
