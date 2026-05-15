# app.py
# 社内アシスタント(HR + IT)のエントリポイント。
# Microsoft 365 Agents SDK を使用し、RAG 経由で社内文書を参照して回答する。
from dotenv import load_dotenv

load_dotenv()

import os

from microsoft_agents.hosting.core import (
    AgentApplication,
    AgentAuthConfiguration,
    TurnState,
    TurnContext,
    MemoryStorage,
)
from microsoft_agents.hosting.aiohttp import CloudAdapter
from openai import AsyncAzureOpenAI

from rag import rag_index, format_context
from start_server import start_server


AGENT_APP = AgentApplication[TurnState](
    storage=MemoryStorage(), adapter=CloudAdapter()
)

# --- Azure OpenAI / Foundry 設定 ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")

# --- 検索する関連文書数 ---
TOP_K = 5

# --- システムプロンプト(日本語) ---
SYSTEM_PROMPT = """あなたは社内アシスタントです。HR規程およびITヘルプデスクに関する質問に日本語で回答します。

回答ルール:
- 必ず提供されたコンテキスト(社内文書の抜粋)に基づいて回答してください
- コンテキストに該当情報がない場合は推測せず、「該当情報が見つかりませんでした。担当部署(HR: 内線2001 / IT: 内線1234)にお問い合わせください」と案内してください
- 回答は簡潔かつ実務的に
- 該当箇所がある場合は出典セクション(例: 「1.1 年次有給休暇」)を末尾に記載してください"""


_azure_openai_client: AsyncAzureOpenAI | None = None


def _get_azure_openai_client() -> AsyncAzureOpenAI:
    """Azure OpenAI クライアントを遅延初期化する。"""
    global _azure_openai_client
    if _azure_openai_client is None:
        _azure_openai_client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    return _azure_openai_client


async def _help(context: TurnContext, _: TurnState):
    """会話開始時 / `/help` 時の案内メッセージ。"""
    await context.send_activity(
        "こんにちは、社内アシスタントです 🚀\n"
        "HR規程(休暇・勤務時間・出張・評価・福利厚生など)や"
        "ITヘルプデスク(アカウント・VPN・セキュリティなど)について何でも質問してください。\n"
        "再度この案内を見るには `/help` と入力してください。"
    )


AGENT_APP.conversation_update("membersAdded")(_help)
AGENT_APP.message("/help")(_help)


@AGENT_APP.activity("message")
async def on_message(context: TurnContext, _: TurnState):
    """ユーザーメッセージを RAG 経由で処理する。"""
    user_text = (context.activity.text or "").strip()
    if not user_text:
        return

    try:
        # 1. RAG 検索: ユーザー質問に関連する社内文書チャンクを取得
        results = await rag_index.search(query=user_text, k=TOP_K)
        context_text = format_context(results)

        # 2. LLM 呼び出し: コンテキスト + ユーザー質問
        completion = await _get_azure_openai_client().chat.completions.create(
            model=AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "system",
                    "content": f"以下は質問に関連する社内文書の抜粋です:\n\n{context_text}",
                },
                {"role": "user", "content": user_text},
            ],
        )
        reply = (
            completion.choices[0].message.content or "応答を生成できませんでした。"
        )
        await context.send_activity(reply)
    except Exception as err:
        await context.send_activity(f"エラーが発生しました: {err}")


if __name__ == "__main__":
    # 起動時にインデックスを読み込む(失敗時は早期に検知)
    rag_index.load()
    try:
        start_server(AGENT_APP, AgentAuthConfiguration(anonymous_allowed=True))
    except Exception as error:
        raise error
