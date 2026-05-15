"""RAG 検索モジュール。

ディスクから FAISS インデックスとチャンクを読み込み、
ユーザークエリに対して上位 K 件の関連チャンクを返す。
"""
import json
from pathlib import Path

import faiss
import numpy as np
from openai import AsyncAzureOpenAI

# --- パス設定 ---
PROJECT_ROOT = Path(__file__).parent
INDEX_DIR = PROJECT_ROOT / "index"
CHUNKS_FILE = INDEX_DIR / "chunks.json"
FAISS_FILE = INDEX_DIR / "faiss.index"


class RAGIndex:
    """RAG インデックス。

    プロセス起動時に1度だけディスクから読み込み、
    以降のクエリで再利用する(遅延ロード方式)。
    """

    def __init__(self) -> None:
        self.chunks: list[dict] = []
        self.index: faiss.Index | None = None
        self._loaded = False

    def load(self) -> None:
        """インデックスをディスクから読み込む。"""
        if self._loaded:
            return
        if not CHUNKS_FILE.exists() or not FAISS_FILE.exists():
            raise FileNotFoundError(
                "インデックスが見つかりません。先に `python build_index.py` を実行してください。"
            )
        self.chunks = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
        self.index = faiss.read_index(str(FAISS_FILE))
        self._loaded = True

    async def search(
        self,
        client: AsyncAzureOpenAI,
        embedding_deployment: str,
        query: str,
        k: int = 5,
    ) -> list[dict]:
        """クエリ文字列を埋め込み、上位 k 件のチャンクを類似度スコア付きで返す。"""
        if not self._loaded:
            self.load()

        # クエリを埋め込みベクトル化
        response = await client.embeddings.create(
            model=embedding_deployment, input=[query]
        )
        query_vec = np.array([response.data[0].embedding], dtype=np.float32)
        # インデックス側と同じく L2 正規化(内積=コサイン類似度として扱うため)
        faiss.normalize_L2(query_vec)

        # FAISS で類似ベクトル検索
        scores, indices = self.index.search(query_vec, k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk = dict(self.chunks[idx])
            chunk["score"] = float(score)
            results.append(chunk)
        return results


# シングルトンとして利用(app.py から import)
rag_index = RAGIndex()


def format_context(results: list[dict]) -> str:
    """検索結果を LLM 用のコンテキスト文字列に整形する。"""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"[文書 {i}] 出典: {r['source']} / セクション: {r['section']}\n{r['text']}"
        )
    return "\n\n---\n\n".join(parts)
