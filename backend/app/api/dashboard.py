"""运营看板 API：统计数据 / 热点问题 / 低置信队列"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta

from app.database import get_db
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.query_log import QueryLog

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    """知识库总览统计"""
    doc_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    chunk_count = (await db.execute(select(func.count(Chunk.id)))).scalar() or 0
    query_total = (await db.execute(select(func.count(QueryLog.id)))).scalar() or 0

    # 近 7 天查询量
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_queries = (
        await db.execute(
            select(func.count(QueryLog.id)).where(QueryLog.created_at >= seven_days_ago)
        )
    ).scalar() or 0

    # 平均置信度
    avg_confidence = (
        await db.execute(
            select(func.avg(QueryLog.confidence_score)).where(QueryLog.confidence_score > 0)
        )
    ).scalar() or 0

    return {
        "document_count": doc_count,
        "chunk_count": chunk_count,
        "total_queries": query_total,
        "recent_7d_queries": recent_queries,
        "avg_confidence": round(float(avg_confidence), 3),
    }


@router.get("/hot-queries")
async def hot_queries(
    limit: int = 20,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """Top N 热点问题（按查询频次排序）"""
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(
            QueryLog.question,
            func.count(QueryLog.id).label("count"),
            func.avg(QueryLog.confidence_score).label("avg_conf"),
        )
        .where(QueryLog.created_at >= since)
        .group_by(QueryLog.question)
        .order_by(func.count(QueryLog.id).desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        {"question": r[0], "query_count": r[1], "avg_confidence": round(float(r[2] or 0), 3)}
        for r in rows
    ]


@router.get("/low-confidence")
async def low_confidence_queue(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """低置信度回答列表（人工审核队列）"""
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.confidence_score < 0.6)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "question": log.question,
            "answer": log.answer[:200] + "..." if len(log.answer) > 200 else log.answer,
            "confidence_score": log.confidence_score,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/metrics")
async def retrieval_metrics(days: int = 7, db: AsyncSession = Depends(get_db)):
    """检索性能指标（延迟分布、命中率趋势等）"""
    since = datetime.utcnow() - timedelta(days=days)

    # 平均延迟
    avg_latency = (
        await db.execute(
            select(func.avg(QueryLog.latency_ms)).where(
                QueryLog.created_at >= since, QueryLog.latency_ms > 0
            )
        )
    ).scalar() or 0

    # P95 延迟（简化：取排序后 95% 位置）
    all_latencies = (
        await db.execute(
            select(QueryLog.latency_ms)
            .where(QueryLog.created_at >= since, QueryLog.latency_ms > 0)
            .order_by(QueryLog.latency_ms)
        )
    ).scalars().all()
    p95_latency = all_latencies[int(len(all_latencies) * 0.95)] if all_latencies else 0

    return {
        "period_days": days,
        "avg_latency_ms": round(float(avg_latency), 1),
        "p95_latency_ms": int(p95_latency),
        "total_queries_in_period": len(all_latencies),
    }
