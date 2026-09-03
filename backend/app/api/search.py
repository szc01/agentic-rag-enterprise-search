"""搜索/问答 API：普通搜索 + Agentic 多步检索 + SSE 流式"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models.query_log import QueryLog
from app.schemas.query import SearchRequest, SearchResponse, QueryFeedbackRequest
from app.graph import run_agentic_query, run_agentic_query_stream
from app.services.retriever import retriever
from app.services.embedding import embedding_service
from app.utils.history import normalize_history

logger = logging.getLogger(__name__)

router = APIRouter()


async def _single_round_search(q: str, top_k: int, db: AsyncSession) -> dict:
    """单轮混合检索（不走 Agent 编排），结果转成与 agentic 一致的字典结构。"""
    query_embedding = await asyncio.to_thread(embedding_service.embed_query, q)
    results = await retriever.hybrid_search(q, query_embedding, db, top_k=top_k)

    citations = [
        {
            "chunk_id": r.chunk_id,
            "document_title": r.document_title,
            "section": r.metadata.get("section", ""),
            "content_snippet": (r.content or "")[:100],
        }
        for r in results
    ]
    # 简版答案：直接拼接 top 片段，标注来源（非 LLM 生成）
    answer_parts = []
    for r in results[:3]:
        answer_parts.append(f"《{r.document_title}》: {r.content[:300]}")
    answer = "\n\n".join(answer_parts) if answer_parts else "（未检索到相关内容）"

    confidence = max((r.final_score for r in results), default=0.0)

    return {
        "answer": answer,
        "citations": citations,
        "confidence_score": confidence,
        "trace": {
            "iterations": 0,
            "sub_queries": [q],
            "chunks_retrieved": len(results),
            "critic_verdict": None,
        },
    }


async def _do_search(
    q: str,
    top_k: int,
    use_agentic: bool,
    db: AsyncSession,
    history: list[dict] | None = None,
    thread_id: str | None = None,
) -> dict:
    """执行检索（agentic 或单轮），返回统一结构字典。"""
    if use_agentic:
        return await run_agentic_query(q, db, history=history, thread_id=thread_id)
    return await _single_round_search(q, top_k, db)


async def _write_query_log(
    db: AsyncSession,
    *,
    question: str,
    answer: str,
    citations: list,
    confidence_score: float,
    retrieval_details: dict,
    latency_ms: int,
    use_agentic: bool,
    status: str = "success",
    error: str | None = None,
) -> int | None:
    """写一条 QueryLog（失败只记日志、不抛，避免影响主流程）。

    Returns:
        query_log_id（写库失败返回 None）
    """
    from app.models.query_log import QueryLog
    from sqlalchemy.exc import SQLAlchemyError

    try:
        log = QueryLog(
            question=question,
            answer=(answer or "")[:500],  # 存摘要，避免全文撑爆日志表
            citations=citations or [],
            confidence_score=confidence_score,
            retrieval_details=retrieval_details or {},
            latency_ms=latency_ms,
            use_agentic=use_agentic,
            status=status,
            error=error,
        )
        db.add(log)
        await db.commit()
        return log.id
    except SQLAlchemyError:
        logger.exception("写入 query_log 失败")
        await db.rollback()
        return None


async def _search_and_log(
    q: str,
    top_k: int,
    use_agentic: bool,
    db: AsyncSession,
    history: list[dict] | None = None,
    thread_id: str | None = None,
) -> dict:
    """执行检索 + 落库 QueryLog，返回统一结构字典（含 query_log_id）。

    失败时也会记一条 status=error 的日志，再向上抛出原始异常。
    """
    start = time.time()
    try:
        result = await _do_search(q, top_k, use_agentic, db, history=history, thread_id=thread_id)
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        await _write_query_log(
            db,
            question=q,
            answer="",
            citations=[],
            confidence_score=0.0,
            retrieval_details={},
            latency_ms=elapsed,
            use_agentic=use_agentic,
            status="error",
            error=f"{type(e).__name__}: {e}",
        )
        raise

    elapsed = int((time.time() - start) * 1000)
    result["latency_ms"] = result.get("latency_ms") or elapsed

    trace = result.get("trace") or {}
    result["query_log_id"] = await _write_query_log(
        db,
        question=q,
        answer=result.get("answer", ""),
        citations=result.get("citations", []),
        confidence_score=result.get("confidence_score", 0.0),
        retrieval_details={
            "sub_queries": trace.get("sub_queries", []),
            "iterations": trace.get("iterations", 0),
            "chunks_retrieved": trace.get("chunks_retrieved", 0),
        },
        latency_ms=result["latency_ms"],
        use_agentic=use_agentic,
    )
    return result


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=2000, description="搜索关键词"),
    top_k: int = Query(default=5, ge=1, le=20),
    use_agentic: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """同步搜索接口：默认走 Agentic 多步检索，use_agentic=False 走单轮混合检索"""
    result = await _search_and_log(q, top_k, use_agentic, db)
    return SearchResponse(
        answer=result["answer"],
        confidence_score=result["confidence_score"],
        citations=result["citations"],
        retrieval_details=result["trace"],
        latency_ms=result.get("latency_ms", 0),
        query_log_id=result.get("query_log_id"),
    )


@router.post("/chat", response_model=SearchResponse)
async def chat(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    """POST 方式的问答接口"""
    result = await _search_and_log(
        request.question,
        request.top_k,
        request.use_agentic,
        db,
        history=normalize_history(request.history),
        thread_id=request.thread_id,
    )
    return SearchResponse(
        answer=result["answer"],
        confidence_score=result["confidence_score"],
        citations=result["citations"],
        retrieval_details=result["trace"],
        latency_ms=result.get("latency_ms", 0),
        query_log_id=result.get("query_log_id"),
    )


@router.post("/feedback")
async def submit_feedback(
    request: QueryFeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """用户反馈：更新 QueryLog.user_feedback 字段。"""
    log = await db.get(QueryLog, request.query_log_id)
    if log is None:
        raise HTTPException(status_code=404, detail=f"查询日志 {request.query_log_id} 不存在")

    log.user_feedback = request.feedback
    await db.commit()
    return {"query_log_id": request.query_log_id, "feedback": request.feedback}


async def _stream_search(
    question: str,
    top_k: int,
    use_agentic: bool,
    db: AsyncSession,
    history: list[dict] | None = None,
    thread_id: str | None = None,
):
    """流式检索：yield (event, data_json) 元组，供 SSE 端点与测试复用。

    事件序列：
        retrieval   —— 编排进度（子查询/迭代）
        token       —— 逐 token 文本
        citations   —— 引用列表
        done        —— 含 confidence / query_log_id / latency / trace
        error       —— 异常时的错误信息（其后仍会跟 done）
    """
    start = time.time()

    try:
        result = None
        answer_parts: list[str] = []

        if use_agentic:
            async for evt in run_agentic_query_stream(question, db, history=history, thread_id=thread_id):
                if evt["type"] == "status":
                    yield ("retrieval", json.dumps(evt, ensure_ascii=False))
                elif evt["type"] == "token":
                    answer_parts.append(evt["content"])
                    yield ("token", json.dumps(evt["content"], ensure_ascii=False))
                elif evt["type"] == "result":
                    result = evt
        else:
            yield ("retrieval", json.dumps(
                {"stage": "retrieval", "mode": "single_round"}, ensure_ascii=False
            ))
            result = await _single_round_search(question, top_k, db)
            answer_parts.append(result["answer"])
            yield ("token", json.dumps(result["answer"], ensure_ascii=False))

        latency_ms = result.get("latency_ms") or int((time.time() - start) * 1000)
        answer = result.get("answer") or "".join(answer_parts)
        trace = result.get("trace") or {}

        # 流式结束后统一落库
        query_log_id = await _write_query_log(
            db,
            question=question,
            answer=answer,
            citations=result.get("citations", []),
            confidence_score=result.get("confidence_score", 0.0),
            retrieval_details={
                "sub_queries": trace.get("sub_queries", []),
                "iterations": trace.get("iterations", 0),
                "chunks_retrieved": trace.get("chunks_retrieved", 0),
            },
            latency_ms=latency_ms,
            use_agentic=use_agentic,
        )

        yield ("citations", json.dumps(result.get("citations", []), ensure_ascii=False))
        yield ("done", json.dumps({
            "confidence_score": result.get("confidence_score", 0.0),
            "query_log_id": query_log_id,
            "latency_ms": latency_ms,
            "trace": trace,
        }, ensure_ascii=False))
    except Exception as e:
        logger.exception("流式检索失败")
        latency_ms = int((time.time() - start) * 1000)
        await _write_query_log(
            db,
            question=question,
            answer="",
            citations=[],
            confidence_score=0.0,
            retrieval_details={},
            latency_ms=latency_ms,
            use_agentic=use_agentic,
            status="error",
            error=f"{type(e).__name__}: {e}",
        )
        yield ("error", json.dumps({"message": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        yield ("done", json.dumps({
            "confidence_score": 0.0,
            "query_log_id": None,
            "latency_ms": latency_ms,
            "trace": {},
        }, ensure_ascii=False))


@router.post("/chat/stream")
async def chat_stream(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    """SSE 流式问答：先推 retrieval 进度 → 逐 token → 最后 citations / done"""
    history = normalize_history(request.history)

    async def event_generator():
        async for event, data in _stream_search(
            request.question, request.top_k, request.use_agentic, db,
            history=history, thread_id=request.thread_id,
        ):
            yield {"event": event, "data": data}

    return EventSourceResponse(event_generator())
