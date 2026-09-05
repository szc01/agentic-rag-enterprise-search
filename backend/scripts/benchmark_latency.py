"""检索性能基准：延迟分布 + 分阶段耗时 + Reranker 开/关 + 并发吞吐（Task 4）

用法（在 backend 目录执行）：
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/benchmark_latency.py

输出：backend/output/benchmark.md

口径：
  - 单次检索端到端延迟（P50 / P95 / P99），分阶段计时：BM25 / 向量 / RRF / 回填 / Reranker。
  - 对比 Reranker 开 / 关。
  - 并发吞吐（1 / 4 / 8 并发，queries/sec）。

注意：本机为 CPU 推理，Reranker（CrossEncoder）是主要瓶颈；离线模式避免 HuggingFace 走代理。
"""
from __future__ import annotations

import asyncio
import logging
import math
import statistics
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
log = logging.getLogger("benchmark")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT_PATH = BACKEND_DIR / "output" / "benchmark.md"
TOP_K = 5
N_SAMPLES = 30
CONCURRENCIES = [1, 4, 8]


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _summarize(vals: list[float]) -> dict:
    s = sorted(vals)
    return {
        "p50": _percentile(s, 50),
        "p95": _percentile(s, 95),
        "p99": _percentile(s, 99),
        "mean": statistics.mean(s) if s else 0.0,
    }


async def _time_phases(retriever, db, query, emb, reranker_on: bool) -> dict[str, float]:
    """按阶段计时一次检索（BM25 / 向量 / RRF / 回填 / Reranker）。"""
    candidate_k = max(TOP_K, retriever.rerank_candidates) if reranker_on else TOP_K

    t0 = time.perf_counter()
    bm25 = retriever._bm25_search(query, candidate_k * 2) if retriever._index_built else []
    t_bm25 = time.perf_counter() - t0

    t0 = time.perf_counter()
    vec = await retriever._vector_search(emb, candidate_k * 2, db)
    t_vec = time.perf_counter() - t0

    t0 = time.perf_counter()
    ranked = retriever._rrf_fuse(bm25, vec, top_k=candidate_k)
    t_rrf = time.perf_counter() - t0

    t0 = time.perf_counter()
    results = await retriever._hydrate_results(
        ranked, db, bm25_map=dict(bm25), vector_map=dict(vec)
    )
    t_hydrate = time.perf_counter() - t0

    t_rerank = 0.0
    if reranker_on and len(results) > TOP_K:
        t0 = time.perf_counter()
        await retriever._rerank_results(query, results)
        t_rerank = time.perf_counter() - t0

    return {
        "bm25": t_bm25,
        "vector": t_vec,
        "rrf": t_rrf,
        "hydrate": t_hydrate,
        "rerank": t_rerank,
    }


async def _run_once(retriever, db, query, emb, reranker_on: bool) -> tuple[float, dict]:
    """端到端 + 分阶段一次测量。"""
    t0 = time.perf_counter()
    await retriever.hybrid_search(query, emb, db, top_k=TOP_K, mode="hybrid", enhance="none")
    total = time.perf_counter() - t0
    phases = await _time_phases(retriever, db, query, emb, reranker_on)
    return total, phases


def _fmt_ms(x: float) -> str:
    return f"{x * 1000:.2f}"


async def _index_maintenance_benchmark() -> dict:
    """BM25 索引维护耗时：全量重建 vs 增量增删（385 chunks 基准 + 1 万估算）。"""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.chunk import Chunk
    from app.services.retriever import HybridRetriever

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Chunk.id, Chunk.content))).all()
    chunks = [{"chunk_id": r[0], "content": r[1]} for r in rows]
    n = len(chunks)
    batch = chunks[:49]

    def _min_wall(fn, times=3):
        best = None
        for _ in range(times):
            t0 = time.perf_counter()
            fn()
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        return best

    def _min_duration(fn, times=3):
        """fn 返回自身计时（毫秒级），取最小值。"""
        best = None
        for _ in range(times):
            d = fn()
            best = d if best is None else min(best, d)
        return best

    full = _min_wall(lambda: HybridRetriever(top_k=5).build_bm25_index(chunks))

    def _add_duration():
        r = HybridRetriever(top_k=5)
        r.build_bm25_index(chunks[49:])  # 基础索引，不计时
        t0 = time.perf_counter()
        for c in batch:
            r._add_chunk(c["chunk_id"], r._tokenize(c["content"]))
        return time.perf_counter() - t0

    def _rm_duration():
        r = HybridRetriever(top_k=5)
        r.build_bm25_index(chunks)  # 完整索引，不计时
        t0 = time.perf_counter()
        for c in batch:
            r._remove_chunk(c["chunk_id"])
        return time.perf_counter() - t0

    add = _min_duration(_add_duration)
    rm = _min_duration(_rm_duration)
    return {
        "n": n,
        "full_ms": full * 1000,
        "add_ms": add * 1000,
        "rm_ms": rm * 1000,
        "full_10k_ms": full * (10000 / n) * 1000,
        "add_10k_ms": add * 1000,
    }


async def main() -> int:
    import os
    os.chdir(BACKEND_DIR)

    from app import models  # noqa: F401  确保 ORM 模型注册到 metadata（建表用）
    from app.database import AsyncSessionLocal, ensure_schema

    # Day 9 Task 4: 确保 bm25_index_state 等表存在（脚本独立运行，不走应用 lifespan）
    await ensure_schema()

    from sqlalchemy import select
    from app.models.chunk import Chunk
    from app.services.retriever import HybridRetriever
    from app.services.embedding import embedding_service
    from scripts.eval_data import EVAL_ITEMS

    # 抽样 30 条查询
    step = max(1, len(EVAL_ITEMS) // N_SAMPLES)
    queries = [it["query"] for it in EVAL_ITEMS[::step]][:N_SAMPLES]

    async with AsyncSessionLocal() as db:
        # 预热：加载 embedding / reranker / 建 BM25 索引
        log.info("预热中（加载模型 / 建索引）...")
        for q in queries[:2]:
            emb = await asyncio.to_thread(embedding_service.embed_query, q)
            r_warm = HybridRetriever(reranker_enabled=True)
            await r_warm.hybrid_search(q, emb, db, top_k=TOP_K, mode="hybrid", enhance="none")

        rows = []
        for reranker_on in (False, True):
            retriever = HybridRetriever(reranker_enabled=reranker_on)
            totals, phase_agg = [], {k: [] for k in ("bm25", "vector", "rrf", "hydrate", "rerank")}
            for q in queries:
                emb = await asyncio.to_thread(embedding_service.embed_query, q)
                total, phases = await _run_once(retriever, db, q, emb, reranker_on)
                totals.append(total)
                for k, v in phases.items():
                    phase_agg[k].append(v)
            rows.append({
                "label": "Reranker ON" if reranker_on else "Reranker OFF",
                "total": _summarize(totals),
                "phases": {k: statistics.mean(v) for k, v in phase_agg.items()},
            })

    # 并发吞吐
    throughput = {}
    async with AsyncSessionLocal() as db:
        retriever = HybridRetriever(reranker_enabled=True)
        q = queries[0]
        emb = await asyncio.to_thread(embedding_service.embed_query, q)
        for c in CONCURRENCIES:
            batches, n_batches = [], 5
            for _ in range(n_batches):
                t0 = time.perf_counter()
                await asyncio.gather(*[
                    retriever.hybrid_search(q, emb, db, top_k=TOP_K, mode="hybrid", enhance="none")
                    for _ in range(c)
                ])
                batches.append(c / (time.perf_counter() - t0))
            throughput[c] = statistics.mean(batches)

    # BM25 索引维护耗时
    index_stats = await _index_maintenance_benchmark()

    markdown = _build_markdown(rows, throughput, index_stats, len(queries))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(markdown)
    log.info(f"结果已写入 {OUTPUT_PATH}")
    return 0


def _build_markdown(rows: list[dict], throughput: dict[int, float], index_stats: dict, n_queries: int) -> str:
    lines = []
    lines.append("# 检索性能基准")
    lines.append("")
    lines.append(f"- 采样查询：{n_queries} 条（来自 110 条评测集等距抽样），top-5 检索")
    lines.append("- 环境：CPU 推理（BGE-large-zh-v1.5 + bge-reranker-base），PostgreSQL + pgvector")
    lines.append("")

    lines.append("## 单次检索端到端延迟")
    lines.append("")
    lines.append("| 配置 | P50 | P95 | P99 | 均值 |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        t = r["total"]
        lines.append(f"| {r['label']} | {_fmt_ms(t['p50'])}ms | {_fmt_ms(t['p95'])}ms | "
                     f"{_fmt_ms(t['p99'])}ms | {_fmt_ms(t['mean'])}ms |")
    lines.append("")

    lines.append("## 分阶段耗时（均值，Reranker OFF）")
    lines.append("")
    off = [r for r in rows if r["label"] == "Reranker OFF"][0]["phases"]
    lines.append("| 阶段 | 耗时 | 占比 |")
    lines.append("|---|---|---|")
    off_total = sum(off.values()) or 1.0
    for name, label in (("bm25", "BM25 稀疏检索"), ("vector", "向量检索（pgvector）"),
                        ("rrf", "RRF 融合"), ("hydrate", "chunk 回填"), ("rerank", "Reranker")):
        v = off[name]
        lines.append(f"| {label} | {_fmt_ms(v)}ms | {v / off_total:.1%} |")
    lines.append("")

    lines.append("## Reranker 开 / 关延迟对比")
    lines.append("")
    lines.append("| 配置 | 端到端均值 | Reranker 阶段均值 |")
    lines.append("|---|---|---|")
    for r in rows:
        lines.append(f"| {r['label']} | {_fmt_ms(r['total']['mean'])}ms | {_fmt_ms(r['phases']['rerank'])}ms |")
    lines.append("")

    lines.append("## 并发吞吐（完整管线，Reranker ON）")
    lines.append("")
    lines.append("| 并发度 | 吞吐 |")
    lines.append("|---|---|")
    for c in CONCURRENCIES:
        lines.append(f"| {c} | {throughput[c]:.2f} queries/s |")
    lines.append("")

    lines.append("## BM25 索引维护耗时（全量重建 vs 增量更新）")
    lines.append("")
    lines.append(f"- 基准语料：{index_stats['n']} chunks；增量批次：49 chunks（一个合成文档）")
    lines.append("")
    lines.append(f"| 操作 | 耗时（当前 {index_stats['n']} chunks） | 估算（1 万 chunks） |")
    lines.append("|---|---|---|")
    lines.append(f"| 全量重建 | {index_stats['full_ms']:.2f} ms | {index_stats['full_10k_ms']:.2f} ms |")
    lines.append(f"| 增量新增（49 chunks） | {index_stats['add_ms']:.2f} ms | {index_stats['add_10k_ms']:.2f} ms |")
    lines.append(f"| 增量删除（49 chunks） | {index_stats['rm_ms']:.2f} ms | ~{index_stats['rm_ms']:.2f} ms |")
    lines.append("")
    lines.append("> 增量更新耗时与「新增/删除的 chunk 数量」相关、与语料总量无关，"
                 "故 1 万 chunks 下增量新增仍约数毫秒级，远优于全量重建（线性增长）。")
    lines.append("")

    lines.append("> 结论：单次检索端到端约 "
                 f"{_fmt_ms([r for r in rows if r['label'] == 'Reranker ON'][0]['total']['mean'])}ms"
                 "，瓶颈在 Reranker（CrossEncoder 逐对精排）；关闭 Reranker 后延迟显著下降。")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
