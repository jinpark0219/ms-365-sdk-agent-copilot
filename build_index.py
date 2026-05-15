"""社内文書をチャンキング・埋め込み・FAISS インデックス化するスクリプト。

実行: .venv/bin/python build_index.py
出力: index/chunks.json + index/faiss.index
"""
import asyncio
import json
import os
import re
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

load_dotenv()

# --- パス設定 ---
PROJECT_ROOT = Path(__file__).parent
DOCS_DIR = PROJECT_ROOT / "sample-docs"
INDEX_DIR = PROJECT_ROOT / "index"
INDEX_DIR.mkdir(exist_ok=True)
CHUNKS_FILE = INDEX_DIR / "chunks.json"
FAISS_FILE = INDEX_DIR / "faiss.index"

# --- Azure OpenAI 設定 ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
)

# 埋め込み API の1回あたり最大入力数(API 制約に余裕を持たせる)
EMBEDDING_BATCH_SIZE = 50


def chunk_markdown(text: str, source: str) -> list[dict]:
    """マークダウンを H2/H3 単位で意味的にチャンキングする。

    - H3 がある H2 セクションは H3 ごとにチャンク(H2 タイトルを文頭に付与)
    - H3 がない H2 セクションは H2 全体を1チャンクに
    - 50文字未満のチャンクは破棄(意味のあるテキストのみ残す)
    """
    chunks: list[dict] = []

    # H2 ヘッダで大きく分割(各セクションは "## " で始まる)
    h2_blocks = re.split(r"\n(?=## )", text)

    for h2_block in h2_blocks:
        if not h2_block.strip().startswith("## "):
            # 文書冒頭(H1 とその前後)はスキップ
            continue

        h2_title = h2_block.split("\n", 1)[0].lstrip("# ").strip()

        # H3 でさらに分割を試みる
        h3_parts = re.split(r"\n(?=### )", h2_block)

        if len(h3_parts) <= 1:
            # H3 なし → H2 全体を1チャンクに
            content = h2_block.strip()
            if len(content) >= 50:
                chunks.append(
                    {
                        "text": content,
                        "source": source,
                        "section": h2_title,
                    }
                )
        else:
            # H3 ごとにチャンク化(最初の h3_parts[0] は H2 ヘッダ + 導入文)
            h2_intro = h3_parts[0].strip()
            for h3_part in h3_parts[1:]:
                h3_title = h3_part.split("\n", 1)[0].lstrip("# ").strip()
                # H2 タイトルを文頭に付与してコンテキストを保持
                content = f"# {h2_title}\n\n{h3_part.strip()}"
                if len(content) >= 50:
                    chunks.append(
                        {
                            "text": content,
                            "source": source,
                            "section": f"{h2_title} > {h3_title}",
                        }
                    )

    return chunks


async def embed_batch(
    client: AsyncAzureOpenAI, deployment: str, texts: list[str]
) -> list[list[float]]:
    """テキストのバッチを埋め込みベクトルに変換する。"""
    response = await client.embeddings.create(model=deployment, input=texts)
    return [d.embedding for d in response.data]


async def main():
    # --- 1. 文書を読み込みチャンク化 ---
    all_chunks: list[dict] = []
    md_files = sorted(DOCS_DIR.glob("*.md"))
    print(f"📂 対象文書: {len(md_files)} 件")

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(text, source=md_file.name)
        print(f"  - {md_file.name}: {len(chunks)} チャンク")
        all_chunks.extend(chunks)

    print(f"📦 合計チャンク数: {len(all_chunks)}")

    # --- 2. Azure OpenAI で埋め込みを生成 ---
    client = AsyncAzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
    )

    print(f"🔢 埋め込み生成中(モデル: {AZURE_OPENAI_EMBEDDING_DEPLOYMENT})...")
    all_vectors: list[list[float]] = []
    for i in range(0, len(all_chunks), EMBEDDING_BATCH_SIZE):
        batch = all_chunks[i : i + EMBEDDING_BATCH_SIZE]
        texts = [c["text"] for c in batch]
        vectors = await embed_batch(client, AZURE_OPENAI_EMBEDDING_DEPLOYMENT, texts)
        all_vectors.extend(vectors)
        print(f"  - バッチ {i // EMBEDDING_BATCH_SIZE + 1}: {len(batch)} 件完了")

    vectors_array = np.array(all_vectors, dtype=np.float32)
    print(f"📐 ベクトル次元: {vectors_array.shape}")

    # --- 3. FAISS インデックス構築(コサイン類似度) ---
    # L2 正規化することで内積 = コサイン類似度として扱える
    faiss.normalize_L2(vectors_array)

    dim = vectors_array.shape[1]
    index = faiss.IndexFlatIP(dim)  # 内積(Inner Product)ベース
    index.add(vectors_array)
    print(f"🔍 FAISS インデックス構築完了: {index.ntotal} ベクトル")

    # --- 4. ディスク保存 ---
    CHUNKS_FILE.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    faiss.write_index(index, str(FAISS_FILE))
    print(f"💾 保存完了:")
    print(f"  - {CHUNKS_FILE}")
    print(f"  - {FAISS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
