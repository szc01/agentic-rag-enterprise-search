"""运维 / 调试 API：BM25 索引状态查询与重建。

设计动机：
  答辩演示 / 答辩老师提问「重启后 BM25 是怎么处理的」时，直接展示这个接口的返回。
  字段：当前 chunks 数、词汇表大小、内存 footprint、快照版本与落盘时间。
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.retriever import retriever
from app.services.bm25_persistence import load_snapshot, save_snapshot, SCHEMA_VERSION

router = APIRouter()


@router.get("/bm25_status")
async def bm25_status(db: AsyncSession = Depends(get_db)):
    """当前 BM25 倒排索引在内存 / PG 快照中的状态摘要。

    Returns:
        200 OK + JSON：{
          in_memory: {
            built: bool,
            chunk_count: int,
            vocab_size: int,
            total_tokens: int,
            memory_estimate_kb: float,
            index_built: bool,
          },
          pg_snapshot: {
            exists: bool,
            chunk_count: int,
            schema_version: int,
            saved_at: ISO-8601 str | None,
          },
          consistency: {
            in_memory_chunks == pg_snapshot_chunks: bool,
            chunks_table_count: int (从 SELECT count(*) Chunk 查的实时值)
          }
        }
    """
    # 1. 内存状态
    in_mem_built = getattr(retriever, "_index_built", False)
    in_mem = {
        "built": in_mem_built,
        "chunk_count": len(getattr(retriever, "_chunk_ids", set())),
        "vocab_size": len(getattr(retriever, "_postings", {})),
        "total_tokens": getattr(retriever, "_total_tokens", 0),
        # 粗略内存估算（每条 posting 算 60 字节：term 平均 12B + dict overhead）
        "memory_estimate_kb": round(
            sum(
                len(tdict) * 60 for tdict in getattr(retriever, "_postings", {}).values()
            ) / 1024,
            1,
        ),
    }

    # 2. PG 快照状态
    snap = await load_snapshot(db)
    pg_snapshot = {
        "exists": snap is not None,
        "chunk_count": (len(snap.chunk_ids) if snap else 0),
        "schema_version": SCHEMA_VERSION,
        "saved_at": None,  # 下方从 BM25IndexState 行读真实 saved_at
    }
    # 真正从 BM25IndexState 里读 saved_at（更准）
    from sqlalchemy import select
    from app.models.bm25_index_state import BM25IndexState

    row = (await db.execute(
        select(BM25IndexState).where(BM25IndexState.singleton_id == "singleton")
    )).scalar_one_or_none()
    if row is not None:
        pg_snapshot["saved_at"] = row.saved_at.isoformat() if row.saved_at else None
        pg_snapshot["chunk_count"] = row.chunk_count

    # 3. chunks 表实时值
    from sqlalchemy import func
    from app.models.chunk import Chunk

    actual_chunks = (await db.execute(
        select(func.count(Chunk.id))
    )).scalar_one()

    consistency = {
        "in_memory_matches_pg_snapshot": (
            in_mem["chunk_count"] == pg_snapshot["chunk_count"]
            if pg_snapshot["exists"] else None
        ),
        "pg_snapshot_matches_chunks_table": (
            pg_snapshot["chunk_count"] == actual_chunks
            if pg_snapshot["exists"] else None
        ),
        "chunks_table_count": actual_chunks,
    }

    return {
        "in_memory": in_mem,
        "pg_snapshot": pg_snapshot,
        "consistency": consistency,
    }


@router.post("/bm25_rebuild")
async def bm25_rebuild(db: AsyncSession = Depends(get_db)):
    """强制丢弃 PG 快照，从 chunks 表全量重建 BM25 索引并立刻落盘。

    用途：
      - 排查索引异常时一键重建
      - 上传文档后想立刻校验索引完整性
    """
    # 1. 强制重置内存索引
    retriever._reset_index()
    # 2. 全量重建
    from sqlalchemy import select
    from app.models.chunk import Chunk

    result = await db.execute(select(Chunk.id, Chunk.content))
    rows = result.all()
    chunks = [{"chunk_id": r.id, "content": r.content} for r in rows]
    retriever.build_bm25_index(chunks)
    # 3. 落盘
    ok = await save_snapshot(retriever, db)
    if not ok:
        raise HTTPException(
            status_code=500,
            detail="BM25 重建后落盘失败（详细见服务端日志）",
        )
    return {
        "status": "rebuilt",
        "chunk_count": len(chunks),
        "vocab_size": len(retriever._postings),
    }
