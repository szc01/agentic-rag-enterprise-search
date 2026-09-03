"""QueryLog 落库测试：写入字段正确性 + 失败回滚（不依赖真实 DB / LLM）"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.query_log import QueryLog


class TestQueryLogWriting:
    """search 路径 QueryLog 落库单元测试"""

    @pytest.mark.asyncio
    async def test_write_query_log_success(self):
        from app.api.search import _write_query_log

        db = MagicMock()
        db.commit = AsyncMock()

        answer = "RAG 是检索增强生成技术。" * 100  # 超长答案
        await _write_query_log(
            db,
            question="什么是 RAG",
            answer=answer,
            citations=[{"chunk_id": 1, "document_title": "技术文档", "section": "", "content_snippet": "..."}],
            confidence_score=0.8,
            retrieval_details={"sub_queries": ["q"], "iterations": 1, "chunks_retrieved": 3},
            latency_ms=123,
            use_agentic=True,
        )

        db.add.assert_called_once()
        log = db.add.call_args[0][0]
        assert isinstance(log, QueryLog)
        assert log.question == "什么是 RAG"
        assert log.answer == answer[:500]  # 存摘要，截断到 500 字
        assert log.confidence_score == 0.8
        assert log.latency_ms == 123
        assert log.use_agentic is True
        assert log.status == "success"
        assert log.error is None
        assert log.retrieval_details["iterations"] == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_query_log_error_status_and_rollback(self):
        from app.api.search import _write_query_log
        from sqlalchemy.exc import SQLAlchemyError

        db = MagicMock()
        db.commit = AsyncMock(side_effect=SQLAlchemyError("connection lost"))
        db.rollback = AsyncMock()

        qid = await _write_query_log(
            db,
            question="坏查询",
            answer="",
            citations=[],
            confidence_score=0.0,
            retrieval_details={},
            latency_ms=0,
            use_agentic=False,
            status="error",
            error="ValueError: boom",
        )

        assert qid is None  # 写库失败不抛，返回 None
        log = db.add.call_args[0][0]
        assert log.status == "error"
        assert log.error == "ValueError: boom"
        assert log.use_agentic is False
        db.rollback.assert_awaited_once()


class TestFeedbackEndpoint:
    """用户反馈 API 单元测试"""

    @pytest.mark.asyncio
    async def test_submit_feedback_updates_query_log(self):
        from app.api.search import submit_feedback
        from app.schemas.query import QueryFeedbackRequest

        db = MagicMock()
        db.commit = AsyncMock()
        log = QueryLog(question="什么是 RAG")
        db.get = AsyncMock(return_value=log)

        resp = await submit_feedback(
            QueryFeedbackRequest(query_log_id=1, feedback="helpful"), db
        )
        assert resp == {"query_log_id": 1, "feedback": "helpful"}
        assert log.user_feedback == "helpful"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_feedback_missing_log_404(self):
        from app.api.search import submit_feedback
        from app.schemas.query import QueryFeedbackRequest
        from fastapi import HTTPException

        db = MagicMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await submit_feedback(
                QueryFeedbackRequest(query_log_id=999, feedback="not_helpful"), db
            )
        assert exc.value.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
