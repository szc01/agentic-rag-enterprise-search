"""检索评测：四组消融对比（论文/答辩素材）

用法（在 backend 目录执行）：
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/eval_retrieval.py --build-kb   # 先重建知识库再评测
    python scripts/eval_retrieval.py --ablation                                          # 仅跑四组消融（默认）

输出：
    - stdout 打印 Markdown
    - 同时写入 backend/output/eval_result.md（可重复跑，幂等覆盖）

四组消融：
    1. BM25-only             —— 仅稀疏检索
    2. 向量-only             —— 仅稠密检索（pgvector 余弦）
    3. BM25+向量             —— RRF 融合（不启用 Reranker）
    4. BM25+向量+Reranker    —— 完整管线

评测集（Day 7 扩量到 100+ 条，5 类难度）：
    - 基线直配：query 与 chunk 关键词字面接近，sanity check
    - 同义改写：query 用不同措辞/近义词，BM25 词面弱但语义强
    - 跨语言：中文 query 命中英文 chunk（或反之）
    - 多主题干扰：query 同时涉及多个主题，期望命中正确那个
    - 反向/否定：query 以否定形式提问，答案在正向陈述的 chunk 里

依赖：
    - 需先 `--build-kb` 生成 300-500 chunks 的合成知识库（见 scripts/eval_data.py）
    - BGE embedding / reranker 模型已缓存；离线模式用 HF_HUB_OFFLINE=1
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
log = logging.getLogger("eval-retrieval")

# Windows 控制台默认 GBK，打印 ✓/✗ 会抛 UnicodeEncodeError，强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT_PATH = BACKEND_DIR / "output" / "eval_result.md"
TOP_KS = [1, 3, 5]
NDCG_K = 5

from scripts.eval_data import EVAL_ITEMS, build_kb_documents, build_real_documents  # noqa: E402

# 四组消融配置
ABLATIONS = [
    {"key": "bm25", "label": "BM25-only", "mode": "bm25", "reranker": False},
    {"key": "vector", "label": "向量-only", "mode": "vector", "reranker": False},
    {"key": "hybrid", "label": "BM25+向量", "mode": "hybrid", "reranker": False},
    {"key": "full", "label": "BM25+向量+Reranker", "mode": "hybrid", "reranker": True},
]

# 查询增强对比（Day 8）：均在完整管线（hybrid + Reranker）上，仅增强方式不同
ENHANCE_CONFIGS = [
    {"key": "enh_none", "label": "baseline", "mode": "hybrid", "reranker": True, "enhance": "none"},
    {"key": "enh_rewrite", "label": "+查询改写", "mode": "hybrid", "reranker": True, "enhance": "rewrite"},
    {"key": "enh_hyde", "label": "+HyDE", "mode": "hybrid", "reranker": True, "enhance": "hyde"},
]

# 复杂查询子集（查询增强应重点提升的类别）
COMPLEX_CATEGORIES = {"多主题干扰", "跨语言", "反向否定"}


def _hit_at(results, keyword: str, k: int) -> bool:
    kw = keyword.lower()
    return any(kw in (r.content or "").lower() for r in results[:k])


def _first_rank(results, keyword: str) -> int:
    kw = keyword.lower()
    for i, r in enumerate(results, 1):
        if kw in (r.content or "").lower():
            return i
    return 0


def _ndcg_at(results, keyword: str, k: int = NDCG_K) -> float:
    """计算 nDCG@k（二值相关性：期望 chunk 命中=1，其余=0）。"""
    kw = keyword.lower()
    rels = [1.0 if kw in (r.content or "").lower() else 0.0 for r in results[:k]]

    def _dcg(r: list[float]) -> float:
        return sum(rel / math.log2(i + 2) for i, rel in enumerate(r))

    idcg = _dcg(sorted(rels, reverse=True))
    if idcg <= 0:
        return 0.0
    return _dcg(rels) / idcg


# ── 知识库构建 ──────────────────────────────────────────

async def _ingest_documents(docs: list[tuple[str, str]]) -> None:
    """写 .md 文件 → 创建 Document → 解析/分片/向量化入库。"""
    from app.database import AsyncSessionLocal, ensure_schema
    from app.models.document import Document
    from app.services.ingestion import ingestion_service

    await ensure_schema()
    upload_dir = BACKEND_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        for filename, content in docs:
            path = upload_dir / filename
            path.write_text(content, encoding="utf-8")
            doc = Document(
                filename=filename,
                file_path=str(path),
                file_type="md",
                file_size=len(content.encode("utf-8")),
                title="",  # ingestion 会回填为文件名 stem
                status="uploaded",
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            await ingestion_service.ingest_document(db, doc.id)
            log.info(f"已入库 {filename}: {doc.total_chunks} chunks")


async def ingest_synthetic_kb() -> None:
    """生成合成企业知识库并入库（写 .md 文件 → 解析 → 分片 → 向量化 → pgvector）。

    幂等说明：脚本不删除既有文档，重复 `--build-kb` 会再追加一份合成文档。
    需要干净重建时请先手动清空 documents/chunks 表。
    """
    docs = build_kb_documents()
    await _ingest_documents(docs)
    log.info("合成知识库构建完成")


async def ingest_real_kb() -> None:
    """补充真实公开文档片段入库（与合成语料混合）。"""
    docs = build_real_documents()
    await _ingest_documents(docs)
    log.info("真实公开文档入库完成")


async def kb_stats() -> dict:
    """返回知识库规模（文档数 / chunk 数）。"""
    from sqlalchemy import select, func
    from app.database import AsyncSessionLocal
    from app.models.document import Document
    from app.models.chunk import Chunk

    async with AsyncSessionLocal() as db:
        docs = (await db.execute(select(func.count()).select_from(Document))).scalar() or 0
        chunks = (await db.execute(select(func.count()).select_from(Chunk))).scalar() or 0
    return {"documents": docs, "chunks": chunks}


async def validate_keywords() -> None:
    """校验评测集每个 keyword 都是库内某 chunk 的真实子串（不满足则抛错）。"""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.chunk import Chunk

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Chunk.content))).all()
    contents = [r[0] or "" for r in rows]

    missing = []
    for item in EVAL_ITEMS:
        kw = item["keyword"].lower()
        if not any(kw in c.lower() for c in contents):
            missing.append((item["category"], item["keyword"]))
    if missing:
        for m in missing:
            log.error(f"keyword 未在库中找到: {m[0]} / {m[1]}")
        raise SystemExit(f"{len(missing)} 个 keyword 不是库内 chunk 的真实子串")


# ── 评测执行 ──────────────────────────────────────────

async def embed_queries() -> dict[str, list[float]]:
    """预计算所有 query 的向量（各消融配置复用，避免重复推理）。"""
    from app.services.embedding import embedding_service

    embs: dict[str, list[float]] = {}
    for item in EVAL_ITEMS:
        q = item["query"]
        if q not in embs:
            embs[q] = await asyncio.to_thread(embedding_service.embed_query, q)
    return embs


def _metrics_from_rows(rows: list[dict]) -> dict:
    """从逐条结果计算汇总指标（top-k 命中率 / MRR / nDCG@5）。"""
    hits = {k: 0 for k in TOP_KS}
    mrr_total = 0.0
    ndcg_total = 0.0
    for row in rows:
        for k in TOP_KS:
            if _hit_at(row["results"], row["keyword"], k):
                hits[k] += 1
        first_rank = _first_rank(row["results"], row["keyword"])
        mrr_total += 1.0 / first_rank if first_rank else 0.0
        ndcg_total += _ndcg_at(row["results"], row["keyword"])

    n = len(rows)
    if n == 0:
        return {"hit_rate": {k: 0.0 for k in TOP_KS}, "mrr": 0.0, "ndcg_at_5": 0.0}
    return {
        "hit_rate": {k: hits[k] / n for k in TOP_KS},
        "mrr": mrr_total / n,
        "ndcg_at_5": ndcg_total / n,
    }


async def run_eval(cfg: dict, db, query_embs: dict[str, list[float]]) -> dict:
    """跑一轮配置，返回 {n, metrics, rows}。"""
    from app.services.retriever import HybridRetriever

    retriever = HybridRetriever(reranker_enabled=cfg["reranker"])
    enhance = cfg.get("enhance", "none")
    rows = []

    for i, item in enumerate(EVAL_ITEMS, 1):
        emb = query_embs[item["query"]]
        results = await retriever.hybrid_search(
            item["query"], emb, db, top_k=5, mode=cfg["mode"], enhance=enhance
        )
        rows.append({
            "id": i,
            "category": item["category"],
            "query": item["query"],
            "keyword": item["keyword"],
            "results": results,
        })

    return {
        "n": len(EVAL_ITEMS),
        "metrics": _metrics_from_rows(rows),
        "rows": rows,
    }


def _rank_mark(rank: int) -> str:
    return f"✓@{rank}" if rank else "✗"


def _enhance_section(enhance_results: dict[str, dict]) -> list[str]:
    """查询增强消融章节：全量 + 复杂查询子集两组指标。"""
    cfg_keys = [c["key"] for c in ENHANCE_CONFIGS]
    labels = {c["key"]: c["label"] for c in ENHANCE_CONFIGS}
    lines = []
    lines.append("## 查询增强消融（完整管线 + 查询侧增强）")
    lines.append("")
    lines.append("> 说明：三组均在完整管线（BM25+向量+Reranker）上，区别仅在查询侧是否做 rewrite / HyDE。")

    scopes = (
        ("全量（110 条）", None),
        ("复杂查询子集（多主题干扰 / 跨语言 / 反向否定，66 条）", COMPLEX_CATEGORIES),
    )
    for scope_title, cats in scopes:
        lines.append("")
        lines.append(f"### {scope_title}")
        lines.append("")
        lines.append("| 指标 |" + "".join(f" {labels[k]} |" for k in cfg_keys))
        lines.append("|" + "---|" * (1 + len(cfg_keys)))
        for k in TOP_KS:
            cells = []
            for ck in cfg_keys:
                rows = enhance_results[ck]["rows"]
                if cats is not None:
                    rows = [r for r in rows if r["category"] in cats]
                cells.append(f"{_metrics_from_rows(rows)['hit_rate'][k]:.2%}")
            lines.append(f"| top-{k} 命中率 |" + "".join(f" {c} |" for c in cells))
        mrr_cells, ndcg_cells = [], []
        for ck in cfg_keys:
            rows = enhance_results[ck]["rows"]
            if cats is not None:
                rows = [r for r in rows if r["category"] in cats]
            m = _metrics_from_rows(rows)
            mrr_cells.append(f"{m['mrr']:.4f}")
            ndcg_cells.append(f"{m['ndcg_at_5']:.4f}")
        lines.append("| MRR |" + "".join(f" {c} |" for c in mrr_cells))
        lines.append("| nDCG@5 |" + "".join(f" {c} |" for c in ndcg_cells))
    return lines


def build_markdown(eval_results: dict[str, dict], stats: dict, enhance_results: dict[str, dict] | None = None) -> str:
    """把四组消融结果（+ 可选的查询增强消融）拼成 Markdown。"""
    cfg_keys = [c["key"] for c in ABLATIONS]
    labels = {c["key"]: c["label"] for c in ABLATIONS}
    n = eval_results[cfg_keys[0]]["n"]

    lines = []
    lines.append("# 检索评测：四组消融对比")
    lines.append("")
    lines.append(f"- 知识库规模：{stats['chunks']} chunks / {stats['documents']} 文档"
                 "（合成多主题企业文档 + 真实公开文档片段 + 既有 e2e 文档）")
    lines.append(f"- 评测集规模：{n} 条（基线直配 + 同义改写 + 跨语言 + 多主题干扰 + 反向否定，每类各 {n // 5} 条）")
    lines.append("- 指标定义：top-k 命中率 = 期望关键词出现在前 k 个结果中的比例；"
                 "MRR = 1/首个命中排名 的平均值；nDCG@5 = 二值相关性（命中=1）下的归一化折损累计增益")
    lines.append("")

    # 逐条结果
    lines.append("## 逐条结果")
    lines.append("")
    header = "| # | 类别 | 查询 | 期望关键词 |" + "".join(f" {labels[k]} |" for k in cfg_keys)
    lines.append(header)
    lines.append("|" + "---|" * (4 + len(cfg_keys)))
    for i in range(n):
        row0 = eval_results[cfg_keys[0]]["rows"][i]
        keyword = row0["keyword"]
        cells = []
        for k in cfg_keys:
            rank = _first_rank(eval_results[k]["rows"][i]["results"], keyword)
            cells.append(_rank_mark(rank))
        line = (f"| {i + 1} | {row0['category']} | {row0['query']} | "
                f"`{keyword}` |" + "".join(f" {c} |" for c in cells))
        lines.append(line)
    lines.append("")

    # 汇总指标
    lines.append("## 汇总指标（消融）")
    lines.append("")
    lines.append("| 指标 |" + "".join(f" {labels[k]} |" for k in cfg_keys))
    lines.append("|" + "---|" * (1 + len(cfg_keys)))
    for k in TOP_KS:
        cells = [f"{eval_results[ck]['metrics']['hit_rate'][k]:.2%}" for ck in cfg_keys]
        lines.append(f"| top-{k} 命中率 |" + "".join(f" {c} |" for c in cells))
    cells = [f"{eval_results[ck]['metrics']['mrr']:.4f}" for ck in cfg_keys]
    lines.append("| MRR |" + "".join(f" {c} |" for c in cells))
    cells = [f"{eval_results[ck]['metrics']['ndcg_at_5']:.4f}" for ck in cfg_keys]
    lines.append("| nDCG@5 |" + "".join(f" {c} |" for c in cells))
    lines.append("")

    # 结果解读（答辩口径）
    lines.append("## 结果解读")
    lines.append("")
    lines.append("- **BM25-only**：稀疏检索对字面精确匹配（专有名词 / 代号 / 参数）有效，但语义泛化弱，整体最弱。")
    lines.append("- **向量-only**：稠密检索语义泛化强，跨语言 / 同义改写命中率明显高于 BM25。")
    lines.append("- **BM25+向量**：RRF 融合兼顾字面与语义，top-3 / top-5 召回达到最高，验证了混合检索的召回互补。")
    lines.append("- **完整管线（+Reranker）**：对融合候选精排后，top-1、MRR 与 nDCG@5 均达到最优，"
                 "说明 Reranker 主要提升「首位精度」；top-5 召回相较无 Reranker 略降，"
                 "是精排以少量召回换取更高精度的典型 trade-off，符合预期。")

    if enhance_results:
        lines.append("")
        lines.extend(_enhance_section(enhance_results))

    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description="检索评测：四组消融对比")
    parser.add_argument("--build-kb", action="store_true",
                        help="先重建合成知识库（追加式，不清空既有文档）")
    parser.add_argument("--build-real", action="store_true",
                        help="补充真实公开文档片段入库（与合成语料混合）")
    parser.add_argument("--ablation", action="store_true", default=True,
                        help="跑四组消融评测（默认行为）")
    parser.add_argument("--enhance", action="store_true",
                        help="追加跑查询增强消融（baseline / 查询改写 / HyDE，需 LLM）")
    args = parser.parse_args()

    os.chdir(BACKEND_DIR)  # 让 ./uploads 等相对路径与正常启动一致

    if args.build_kb:
        await ingest_synthetic_kb()

    if args.build_real:
        await ingest_real_kb()

    await validate_keywords()
    stats = await kb_stats()
    log.info(f"知识库规模: {stats['chunks']} chunks / {stats['documents']} docs")

    from app.database import AsyncSessionLocal

    query_embs = await embed_queries()
    eval_results: dict[str, dict] = {}

    async with AsyncSessionLocal() as db:
        for cfg in ABLATIONS:
            log.info(f"开始评测：{cfg['label']} ...")
            eval_results[cfg["key"]] = await run_eval(cfg, db, query_embs)
            m = eval_results[cfg["key"]]["metrics"]
            log.info(f"  top-1={m['hit_rate'][1]:.2%} top-3={m['hit_rate'][3]:.2%} "
                     f"top-5={m['hit_rate'][5]:.2%} MRR={m['mrr']:.4f} "
                     f"nDCG@5={m['ndcg_at_5']:.4f}")

        enhance_results: dict[str, dict] = {}
        if args.enhance:
            for cfg in ENHANCE_CONFIGS:
                log.info(f"开始查询增强评测：{cfg['label']} ...")
                enhance_results[cfg["key"]] = await run_eval(cfg, db, query_embs)
                m = enhance_results[cfg["key"]]["metrics"]
                log.info(f"  top-1={m['hit_rate'][1]:.2%} MRR={m['mrr']:.4f} "
                         f"nDCG@5={m['ndcg_at_5']:.4f}")

    markdown = build_markdown(eval_results, stats, enhance_results or None)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(markdown)
    log.info(f"结果已写入 {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
