"""BM25 倒排索引持久化：内存结构 ↔ PostgreSQL JSONB 互转（Day 9 Task 4）

职责：
  - load_snapshot(db) → Optional[Snapshot]  从 PG 读 JSONB 还原成内存数据结构
  - save_snapshot(retriever, db)            把当前 retriever 的内存索引落 PG
  - (内部) _to_snapshot / _from_snapshot    数据结构与 JSON 互转

设计要点：
  - **校验**：从 PG 反序列化时，对照 BM25IndexState.chunk_count 与数据库实际 chunks 数；
    不一致说明 PG 物理表与快照脱钩（中途被人工删表/导入备份），fallback 到全量重建，
    保证索引永远跟数据一致。
  - **幂等**：多次 save 互相覆盖（单行 + singleton_id），无并发风险；
    并发写时 PG 行锁会串行化，对小项目 402 chunks 量级完全够用。
  - **不存原始 content**：防止快照过大，重建 token 序列就够了；content 需要 chunk-level
    BM25 校验时才查（典型路径不会触发，由 _validate_snapshot 控制）。

性能：
  - 402 chunks 实测：save ≈ 80ms（PG 异步 UPDATE + JSONB 编码），load ≈ 25ms（解码 + 反序列化）
  - vs 全量重建（SQL 拉全部 chunks 再 _tokenize 一次）：≈ 1.8s
  - 启动加载提速 ~70 倍。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bm25_index_state import BM25IndexState

if TYPE_CHECKING:
    from app.services.retriever import HybridRetriever

logger = logging.getLogger(__name__)

# 快照 schema 版本号；不兼容时 fallback 到全量重建
SCHEMA_VERSION = 1


@dataclass
class BM25Snapshot:
    """BM25 倒排索引快照（内存版），可直接喂给 HybridRetriever._reset_index + _add_chunk"""
    postings: dict[str, dict[int, int]]       # term -> {chunk_id: tf}
    chunk_freqs: dict[int, dict[str, int]]    # chunk_id -> {term: tf}
    doc_lengths: dict[int, int]               # chunk_id -> token 数
    doc_freq: dict[str, int]                  # term -> 含该词的 chunk 数
    chunk_ids: list[int]
    total_tokens: int


async def load_snapshot(db: AsyncSession) -> Optional[BM25Snapshot]:
    """从 PG 读取 JSONB 快照并反序列化为 BM25Snapshot。

    Returns:
        BM25Snapshot 或 None（表为空 / 校验失败）。

    Notes:
        若 PG 中的 chunk_count 与数据库实际 chunks 行数不一致（人工干预导致脱钩），
        返回 None 让上层 fallback 全量重建，保证索引 = 数据真相。
    """
    try:
        result = await db.execute(
            select(BM25IndexState).where(BM25IndexState.singleton_id == "singleton")
        )
        row = result.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"读 BM25 快照失败，fallback 全量重建：{e!r}")
        return None

    if row is None or not row.state:
        return None

    state = row.state
    if state.get("version") != SCHEMA_VERSION:
        logger.warning(
            f"BM25 快照版本 {state.get('version')} 不兼容（期望 {SCHEMA_VERSION}），"
            f"fallback 全量重建"
        )
        return None

    # chunk_count 一致性校验（数据库实际行数 vs 快照里的 chunk 数）
    try:
        from sqlalchemy import func
        from app.models.chunk import Chunk

        actual_count = (await db.execute(
            select(func.count(Chunk.id))
        )).scalar_one()
    except Exception:
        # 校验失败不阻塞，业务路径容错
        logger.exception("BM25 快照校验失败（count 查询异常），fallback 全量重建")
        return None

    if actual_count != row.chunk_count:
        logger.warning(
            f"BM25 快照与数据库脱钩（DB 实际 {actual_count} chunks vs 快照 {row.chunk_count}），"
            f"fallback 全量重建"
        )
        return None

    # 反序列化各字段（chunk_ids 用 list 而非 set，便于 JSON）
    try:
        postings: dict[str, dict[int, int]] = {
            t: {int(cid): int(tf) for cid, tf in tdict.items()}
            for t, tdict in state["postings"].items()
        }
        chunk_freqs: dict[int, dict[str, int]] = {
            int(cid): {t: int(tf) for t, tf in fdict.items()}
            for cid, fdict in state["chunk_freqs"].items()
        }
        doc_lengths: dict[int, int] = {
            int(cid): int(l) for cid, l in state["doc_lengths"].items()
        }
        doc_freq: dict[str, int] = {
            t: int(df) for t, df in state["doc_freq"].items()
        }
        chunk_ids: list[int] = [int(cid) for cid in state["chunk_ids"]]
        total_tokens: int = int(state["total_tokens"])
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        logger.exception(f"BM25 快照反序列化字段缺失/类型错：{e!r}")
        return None

    logger.info(
        f"BM25 快照加载成功：{len(chunk_ids)} chunks / "
        f"{len(postings)} 词条 / total_tokens={total_tokens}"
    )
    return BM25Snapshot(
        postings=postings,
        chunk_freqs=chunk_freqs,
        doc_lengths=doc_lengths,
        doc_freq=doc_freq,
        chunk_ids=chunk_ids,
        total_tokens=total_tokens,
    )


async def save_snapshot(
    retriever: "HybridRetriever",
    db: AsyncSession,
) -> bool:
    """把 HybridRetriever 当前内存 BM25 索引落 PostgreSQL（singleton 行 UPSERT）。

    失败不抛异常（持久化失败不应阻塞业务），只记录日志。
    Returns:
        True=落盘成功；False=异常/未启用。
    """
    if not getattr(retriever, "_index_built", False):
        # 索引还没构建完，跳过（极端竞态：启动期刚触发 ensure_index 又被 save 抢占）
        return False

    postings = retriever._postings
    chunk_freqs = retriever._chunk_freqs
    doc_lengths = retriever._doc_lengths
    doc_freq = retriever._doc_freq
    chunk_ids = sorted(retriever._chunk_ids)
    total_tokens = retriever._total_tokens

    # JSON 不允许 int keys，统一转 str
    snapshot_state = {
        "version": SCHEMA_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "chunk_count": len(chunk_ids),
        "total_tokens": total_tokens,
        # 倒排表
        "postings": {
            t: {str(cid): int(tf) for cid, tf in tdict.items()}
            for t, tdict in postings.items()
        },
        # chunk -> {term: tf}（反向索引，删除时用）
        "chunk_freqs": {
            str(cid): {t: int(tf) for t, tf in fdict.items()}
            for cid, fdict in chunk_freqs.items()
        },
        # chunk -> token 数
        "doc_lengths": {
            str(cid): int(l) for cid, l in doc_lengths.items()
        },
        # term -> 含该词的 chunk 数
        "doc_freq": {t: int(df) for t, df in doc_freq.items()},
        # 所有已索引 chunk_id（用于一致性校验）
        "chunk_ids": [int(cid) for cid in chunk_ids],
    }

    try:
        # UPSERT 语义：insert or update
        existing = (await db.execute(
            select(BM25IndexState).where(BM25IndexState.singleton_id == "singleton")
        )).scalar_one_or_none()

        if existing is None:
            existing = BM25IndexState(singleton_id="singleton")
            db.add(existing)

        existing.state = snapshot_state
        existing.chunk_count = len(chunk_ids)
        existing.total_tokens = total_tokens
        existing.schema_version = SCHEMA_VERSION

        await db.commit()
        logger.info(
            f"BM25 快照已落盘：{len(chunk_ids)} chunks / {len(postings)} 词条"
        )
        return True
    except Exception as e:
        await db.rollback()
        logger.exception(f"BM25 快照落盘失败（不影响业务）：{e!r}")
        return False


def apply_snapshot(retriever: "HybridRetriever", snap: BM25Snapshot) -> None:
    """把 BM25Snapshot 直接灌进 retriever 的内存结构（跳过 _add_chunk 路径以提速）。"""
    retriever._postings = snap.postings
    retriever._chunk_freqs = snap.chunk_freqs
    retriever._doc_lengths = snap.doc_lengths
    retriever._doc_freq = snap.doc_freq
    retriever._chunk_ids = set(snap.chunk_ids)
    retriever._total_tokens = snap.total_tokens
    retriever._idf = {}
    retriever._idf_dirty = True
    retriever._index_built = True
