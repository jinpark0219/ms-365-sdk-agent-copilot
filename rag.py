"""RAG 検索モジュール。

LangChain の FAISS ベクトルストアからチャンクを読み込み、
ユーザークエリに対して上位 K 件の関連チャンクを返す。
"""
import os
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_openai import AzureOpenAIEmbeddings

# --- パス設定 ---
PROJECT_ROOT = Path(__file__).parent
INDEX_DIR = PROJECT_ROOT / "index"


class RAGIndex:
    """LangChain FAISS インデックスのラッパー。

    プロセス起動時に1度だけ読み込み、以降のクエリで再利用する(遅延ロード)。
    """

    def __init__(self) -> None:
        self.vectorstore: FAISS | None = None

    def load(self) -> None:
        """インデックスをディスクから読み込む。"""
        if self.vectorstore is not None:
            return
        if not INDEX_DIR.exists():
            raise FileNotFoundError(
                "インデックスが見つかりません。先に `python build_index.py` を実行してください。"
            )
        embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            azure_deployment=os.getenv(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
            ),
        )
        # 自分で作成したインデックスなので deserialize 許可
        self.vectorstore = FAISS.load_local(
            str(INDEX_DIR), embeddings, allow_dangerous_deserialization=True
        )

    async def search(self, query: str, k: int = 5) -> list[dict]:
        """クエリを埋め込み、上位 k 件のチャンクをスコア付きで返す。"""
        if self.vectorstore is None:
            self.load()

        # asimilarity_search_with_score: 非同期検索(スコアは距離ベース、低いほど近い)
        results = await self.vectorstore.asimilarity_search_with_score(query, k=k)

        return [
            {
                "text": doc.page_content,
                "source": doc.metadata.get("source", ""),
                "section": " > ".join(
                    filter(None, [doc.metadata.get("h2"), doc.metadata.get("h3")])
                )
                or "(no section)",
                "score": float(score),
            }
            for doc, score in results
        ]


# シングルトン(app.py から import)
rag_index = RAGIndex()


def format_context(results: list[dict]) -> str:
    """検索結果を LLM 用のコンテキスト文字列に整形する。"""
    return "\n\n---\n\n".join(
        f"[文書 {i}] 出典: {r['source']} / セクション: {r['section']}\n{r['text']}"
        for i, r in enumerate(results, 1)
    )
