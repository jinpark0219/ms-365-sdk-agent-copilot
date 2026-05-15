"""社内文書をチャンキング・埋め込み・FAISS インデックス化するスクリプト。

LangChain を使用してチャンキング・埋め込み・ベクトルストア保存を行う。

実行: .venv/bin/python build_index.py
出力: index/  (LangChain FAISS 形式: index.faiss + index.pkl)
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import AzureOpenAIEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter

load_dotenv()

# --- パス設定 ---
PROJECT_ROOT = Path(__file__).parent
DOCS_DIR = PROJECT_ROOT / "sample-docs"
INDEX_DIR = PROJECT_ROOT / "index"
INDEX_DIR.mkdir(exist_ok=True)

# --- Azure OpenAI 埋め込み設定 ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
)

# --- マークダウン分割設定 ---
# H2/H3 ヘッダ単位でチャンク化(ヘッダはメタデータと本文の両方に保持)
splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("##", "h2"), ("###", "h3")],
    strip_headers=False,
)


def main():
    # --- 1. 文書を読み込みチャンク化 ---
    all_docs = []
    md_files = sorted(DOCS_DIR.glob("*.md"))
    print(f"📂 対象文書: {len(md_files)} 件")

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        docs = splitter.split_text(text)

        # 各チャンクに「出典ファイル名」と「H2 タイトルを文頭に付与」を追加
        # (H2 を本文に含めることで、H3 だけのチャンクでも親カテゴリの文脈が保持される)
        for doc in docs:
            doc.metadata["source"] = md_file.name
            h2 = doc.metadata.get("h2", "")
            if h2 and not doc.page_content.startswith(f"# {h2}"):
                doc.page_content = f"# {h2}\n\n{doc.page_content}"

        print(f"  - {md_file.name}: {len(docs)} チャンク")
        all_docs.extend(docs)

    print(f"📦 合計チャンク数: {len(all_docs)}")

    # --- 2. Azure OpenAI 埋め込みで FAISS インデックスを構築 ---
    print(f"🔢 埋め込み生成 + FAISS インデックス構築中...")
    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    )
    vectorstore = FAISS.from_documents(all_docs, embeddings)
    print(f"🔍 FAISS インデックス構築完了: {vectorstore.index.ntotal} ベクトル")

    # --- 3. ディスクへ保存 ---
    vectorstore.save_local(str(INDEX_DIR))
    print(f"💾 保存完了: {INDEX_DIR}/ (index.faiss + index.pkl)")


if __name__ == "__main__":
    main()
