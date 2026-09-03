"""SSE 真流式测试：mock LLM 流式输出，断言 token / 事件序列 / query_log 落库"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agents.types import SubQuery, CriticVerdict
from app.models.query_log import QueryLog


class _Chunk:
    """模拟 ChatOpenAI.astream 产出的 chunk"""
    def __init__(self, content):
        self.content = content


async def _fake_astream(messages):
    for token in ["RAG", " 是检索增强生成[1]。"]:
        yield _Chunk(token)


class TestSynthesizerStream:
    """Synthesizer 流式生成单元测试"""

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_tokens_then_result(self):
        from app.services.agents.synthesizer import synthesizer_agent

        mock_llm = MagicMock()
        mock_llm.astream = _fake_astream

        state = {
            "question": "什么是 RAG",
            "retrieved_chunks": [{
                "chunk_id": 1,
                "content": "RAG 是检索增强生成技术",
                "document_title": "技术文档",
                "metadata": {},
                "scores": {"final": 0.9},
            }],
            "critic_verdict": CriticVerdict(sufficient=True, confidence=0.88),
        }

        with patch.object(synthesizer_agent, "llm", mock_llm):
            tokens = []
            result = None
            async for kind, payload in synthesizer_agent.synthesize_stream(state):
                if kind == "token":
                    tokens.append(payload)
                else:
                    result = payload

        assert "".join(tokens) == "RAG 是检索增强生成[1]。"
        assert result["confidence_score"] == 0.88  # 取自 Critic
        assert len(result["citations"]) == 1
        assert result["citations"][0].document_title == "技术文档"


class TestStreamSearch:
    """/chat/stream 事件序列 + query_log 落库测试"""

    @pytest.mark.asyncio
    async def test_stream_search_event_sequence(self):
        from app.api.search import _stream_search
        from app.services.agents import planner as p, retrieval as r
        from app.services.agents import critic as c, synthesizer as s

        async def fake_plan(q, history=None):
            return [SubQuery(query="子查询1", rationale="")]

        async def fake_retrieve(state, db):
            idx = state.get("current_query_index", 0)
            return {
                "retrieved_chunks": [{
                    "chunk_id": 1, "content": "RAG 检索增强", "document_title": "技术文档",
                    "metadata": {}, "scores": {"final": 0.9},
                }],
                "current_query_index": idx + 1,
            }

        async def fake_critique(state):
            return {"critic_verdict": CriticVerdict(sufficient=True, confidence=0.9)}

        mock_llm = MagicMock()
        mock_llm.astream = _fake_astream

        db = MagicMock()
        db.commit = AsyncMock()

        with patch.object(p.planner_agent, "plan", side_effect=fake_plan), \
             patch.object(r.retrieval_agent, "retrieve", side_effect=fake_retrieve), \
             patch.object(c.critic_agent, "critique", side_effect=fake_critique), \
             patch.object(s.synthesizer_agent, "llm", mock_llm):
            events = []
            async for event, data in _stream_search("什么是 RAG", 5, True, db):
                events.append((event, data))

        kinds = [e for e, _ in events]
        # 首事件是检索进度，末两个是 citations / done
        assert kinds[0] == "retrieval"
        assert "token" in kinds
        assert kinds[-2] == "citations"
        assert kinds[-1] == "done"

        # token 拼接成完整答案
        tokens = [json.loads(d) for e, d in events if e == "token"]
        assert "".join(tokens) == "RAG 是检索增强生成[1]。"

        done = json.loads(events[-1][1])
        assert done["confidence_score"] == 0.9
        assert done["trace"]["iterations"] == 1

        # query_log 已落库（流式结束后写）
        db.add.assert_called_once()
        log = db.add.call_args[0][0]
        assert isinstance(log, QueryLog)
        assert log.use_agentic is True
        assert log.status == "success"
        assert log.answer == "RAG 是检索增强生成[1]。"
        db.commit.assert_awaited()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
