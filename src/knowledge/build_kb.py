"""知识库构建工具 — 将 Markdown 文档向量化存入 FAISS"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent.parent
DOCS_DIR = Path(__file__).parent / "docs"
FAISS_DIR = Path.home() / ".running_coach_faiss"

def build_knowledge_base():
    print("正在构建跑步知识库...")

    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_core.documents import Document

    # 加载文档
    documents = []
    for md_file in sorted(DOCS_DIR.glob("*.md")):
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
        doc = Document(
            page_content=content,
            metadata={"source": md_file.name, "title": md_file.stem}
        )
        documents.append(doc)

    print(f"  加载了 {len(documents)} 篇文档")

    # 切分
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
        separators=["\n## ", "\n### ", "\n", "。", ".", " "]
    )
    chunks = splitter.split_documents(documents)
    print(f"  切分为 {len(chunks)} 个文本块")

    # 向量化
    embeddings = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese")

    # 存入 FAISS
    vectorstore = FAISS.from_documents(chunks, embeddings)
    FAISS_DIR.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(FAISS_DIR))

    print(f"  ✅ 知识库构建完成！存储位置: {FAISS_DIR}")
    print(f"  📊 共 {len(chunks)} 个文本块")
    return vectorstore

if __name__ == "__main__":
    build_knowledge_base()
