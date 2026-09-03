"""Day 1 端到端验证：上传 PDF → 解析 → 分片 → 向量化 → 入库

用法（在项目根目录执行）：
    .venv/Scripts/python.exe scripts/e2e_ingest.py

流程：
    1. 生成一个测试 PDF（纯文本、多段落）
    2. 通过 FastAPI 上传接口 POST /api/documents/upload
    3. 直接用 psycopg2 连库校验 chunks 表：分片数量、content、向量维度、document_id
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 保证能从任意目录运行：把 backend/ 加入 sys.path，并切到 backend 下执行
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# 先压低 SQLAlchemy echo 日志，保持输出可读
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("e2e")


# ── 最小可用的 PDF 生成器（无第三方依赖，纯手写 PDF 结构） ──────────────

def build_test_pdf(paragraphs: list[str]) -> bytes:
    """生成一个单页 PDF，把每段文字绘制成一行。

    使用标准 Helvetica 字体，只支持 ASCII 文本（中文需内嵌 CJK 字体，
    这里用英文段落即可验证整条链路）。
    """

    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    # 内容流：每段一行，逐行下移
    stream_lines = ["BT", "/F1 11 Tf"]
    y = 760
    for p in paragraphs:
        stream_lines.append(f"1 0 0 1 56 {y} Tm ({esc(p)}) Tj")
        y -= 24
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        (b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
         + stream + b"\nendstream"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1")
        out += obj
        out += b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n").encode("latin-1")
    return bytes(out)


TEST_PARAGRAPHS = [
    "Introduction to Retrieval Augmented Generation",
    "Retrieval augmented generation, commonly known as RAG, combines a retrieval "
    "system with a large language model to produce answers that are grounded in an "
    "external knowledge base instead of relying only on the model's internal parameters.",
    "The retrieval step first converts the user query into a dense vector using an "
    "embedding model such as BGE. This vector is then compared against a vector index "
    "of document chunks using cosine similarity to find the most relevant passages.",
    "Chunking is a critical preprocessing step. Documents are split into smaller pieces "
    "so that each chunk fits the embedding model's context window while preserving enough "
    "semantic information to remain useful for retrieval and answer generation.",
    "A good chunking strategy respects the natural structure of the source document. "
    "It prefers heading and section boundaries, then paragraph boundaries, and finally "
    "falls back to a fixed length window with overlap to avoid cutting sentences in half.",
    "PostgreSQL with the pgvector extension provides an efficient way to store and query "
    "vector embeddings. It supports exact and approximate nearest neighbor search through "
    "operators such as cosine distance and inner product.",
    "Metadata is attached to every chunk so that the system can trace the source document, "
    "page number, and section title of each retrieved passage. This enables citation and "
    "auditability in an enterprise knowledge management platform.",
    "The ingestion pipeline runs in three stages: parsing the raw document into text blocks, "
    "splitting those blocks into chunks, and embedding each chunk into a high dimensional "
    "vector before inserting it into the database.",
    "Once ingestion is complete, the system can answer natural language questions by "
    "retrieving the top ranked chunks and passing them as context to the language model.",
    "This end to end test verifies that an uploaded PDF is parsed, chunked, embedded, and "
    "stored correctly with a vector dimension matching the embedding model.",
]


def main() -> int:
    import os
    os.chdir(BACKEND_DIR)  # 让 ./uploads 等相对路径与正常启动保持一致

    log.info("step 1/4: 生成测试 PDF")
    pdf_bytes = build_test_pdf(TEST_PARAGRAPHS)

    # 快速自检：确认生成的 PDF 能被 pdfplumber 解析出文本
    from app.services.parser import parser
    tmp_pdf = BACKEND_DIR / "_e2e_test.pdf"
    tmp_pdf.write_bytes(pdf_bytes)
    blocks = list(parser.parse(str(tmp_pdf)))
    assert blocks, "测试 PDF 未能解析出任何文本"
    log.info(f"       PDF 自检通过：解析出 {len(blocks)} 个文本块，共 {sum(len(b.content) for b in blocks)} 字符")

    log.info("step 2/4: 通过上传接口提交 PDF")
    from fastapi.testclient import TestClient
    from app import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("e2e_test.pdf", pdf_bytes, "application/pdf")},
        )
    assert resp.status_code == 200, f"上传失败 HTTP {resp.status_code}: {resp.text}"
    data = resp.json()
    doc_id = data["id"]
    log.info(f"       文档 ID={doc_id}, status={data['status']}, total_chunks={data['total_chunks']}")
    assert data["status"] == "ready", f"文档状态异常: {data['status']}"
    assert data["total_chunks"] > 0, "入库后应产生至少 1 个分片"

    log.info("step 3/4: 直接连库校验 chunks 表")
    import psycopg2
    from app.config import settings

    conn = psycopg2.connect(settings.sync_database_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, document_id, chunk_index, content, vector_dims(embedding), embedding
        FROM chunks
        WHERE document_id = %s
        ORDER BY chunk_index
        """,
        (doc_id,),
    )
    rows = cur.fetchall()
    conn.close()

    assert len(rows) == data["total_chunks"], (
        f"chunks 表行数({len(rows)}) 与 API 返回 total_chunks({data['total_chunks']}) 不一致"
    )
    for row in rows:
        chunk_id, document_id, chunk_index, content, dims, embedding = row
        assert document_id == doc_id, f"chunk {chunk_id} 的 document_id 不匹配"
        assert content and content.strip(), f"chunk {chunk_id} 内容为空"
        assert dims == settings.embedding_dimension, (
            f"chunk {chunk_id} 向量维度 {dims} != {settings.embedding_dimension}"
        )
        assert embedding is not None, f"chunk {chunk_id} 缺少向量"

    log.info(f"       共 {len(rows)} 个分片，向量维度均为 {settings.embedding_dimension}，document_id 匹配")

    log.info("step 4/4: 抽样展示首个分片")
    first = rows[0]
    chunk_id, document_id, chunk_index, content, dims, embedding = first
    # embedding 是 pgvector 的 text 表示，如 "[0.012,-0.034,...]"，只展示前几个分量
    head = str(embedding)[:80]
    log.info(f"       chunk id={chunk_id} index={chunk_index} dims={dims}")
    log.info(f"       content: {content[:80]}...")
    log.info(f"       embedding: {head}...")

    tmp_pdf.unlink(missing_ok=True)
    log.info(f"\n✅ 端到端验证通过：文档 {doc_id} 已入库，chunk 与向量均可查到")
    return 0


if __name__ == "__main__":
    sys.exit(main())
