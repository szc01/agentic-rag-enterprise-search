"""Day 2 端到端验证：混合检索（真实库）+ Agentic 查询（真实 LLM）

用法（项目根目录）：
    HF_ENDPOINT=https://hf-mirror.com .venv/Scripts/python.exe scripts/e2e_search.py

依赖：
    - 库里已有 e2e_test.pdf 的 chunks（Day 1 已入库）
    - BGE 模型已缓存；LLM（DeepSeek）key 有效

Phase A：真实 pgvector + BM25 + RRF 检索，断言命中预期 chunk（无需 LLM）
Phase B：跑 LangGraph（planner→retrieval→critic→synthesizer），断言引用/置信度/迭代上限
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
log = logging.getLogger("e2e-search")

QUERY = "What is retrieval augmented generation?"


async def phase_a_retrieval() -> None:
    """Phase A：真实混合检索，无需 LLM。"""
    from app.database import AsyncSessionLocal
    from app.services.retriever import retriever
    from app.services.embedding import embedding_service

    log.info("Phase A: 混合检索（pgvector + BM25 + RRF）")
    async with AsyncSessionLocal() as db:
        q_emb = await asyncio.to_thread(embedding_service.embed_query, QUERY)
        results = await retriever.hybrid_search(QUERY, q_emb, db, top_k=5)

    assert results, "检索应返回至少 1 条结果"
    for r in results:
        log.info(
            f"  chunk_id={r.chunk_id} doc='{r.document_title}' "
            f"final={r.final_score} vector={r.vector_score} bm25={r.bm25_score}\n"
            f"     {r.content[:80].strip()}..."
        )

    # 断言：命中 e2e_test.pdf 的预期 chunk（介绍 RAG 的分片）
    assert all(r.document_id != 0 for r in results), "结果应回填 document_id"
    assert any("retrieval" in r.content.lower() for r in results), \
        "检索结果应包含介绍 retrieval 的分片"
    log.info("Phase A 通过 ✅")


async def phase_b_agentic() -> None:
    """Phase B：跑 LangGraph 全链路（需要有效 LLM key）。"""
    from app.database import AsyncSessionLocal
    from app.graph import run_agentic_query

    log.info("Phase B: Agentic 查询（planner → retrieval → critic → synthesizer）")
    async with AsyncSessionLocal() as db:
        result = await run_agentic_query(QUERY, db)

    answer = result["answer"]
    citations = result["citations"]
    conf = result["confidence_score"]
    trace = result["trace"]

    log.info(f"  answer: {answer[:200]}...")
    log.info(f"  citations: {len(citations)} 条, confidence={conf}")
    log.info(f"  trace: iterations={trace['iterations']}, "
             f"sub_queries={trace['sub_queries']}, "
             f"chunks_retrieved={trace['chunks_retrieved']}")

    assert answer.strip(), "应返回非空答案"
    assert citations, "应返回至少 1 条引用"
    assert 0.0 <= conf <= 1.0, "置信度应在 0-1 之间"
    assert trace["iterations"] <= 3, "自循环不应超过 3 轮"
    log.info("Phase B 通过 ✅")


async def main() -> int:
    # 建表 + 建 HNSW 索引（幂等），确保向量检索能命中索引
    import app.models  # noqa: F401  注册 ORM 模型到 metadata
    from app.database import ensure_schema
    await ensure_schema()

    await phase_a_retrieval()

    try:
        await phase_b_agentic()
    except Exception as e:
        log.error(f"Phase B 失败: {type(e).__name__}: {e}")
        log.error("（若为 401 认证错误，说明 .env 里的 DeepSeek key 无效，需更新 key 后重试）")
        return 1

    log.info("\n✅ Day 2 端到端验证全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
