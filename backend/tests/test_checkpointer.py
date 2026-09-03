"""LangGraph checkpointer 会话持久化测试（内存 checkpointer，不依赖 Postgres 包 / DB）"""
import pytest
from unittest.mock import patch

from app.services.agents.types import SubQuery, CriticVerdict, Citation


@pytest.fixture(autouse=True)
def _reset_compiled_graph():
    """每个用例前后重置 graph 单例，避免内存 checkpointer 跨用例串扰。"""
    from app import graph as g
    g._compiled_graph = None
    yield
    g._compiled_graph = None


class TestCheckpointer:
    @pytest.mark.asyncio
    async def test_multi_turn_restores_history_across_requests(self):
        """同一 thread_id 的第二轮不传 history 时，应从 checkpoint 恢复上一轮历史。"""
        from app import graph as G
        from app.services.agents import planner as p, retrieval as r
        from app.services.agents import critic as c, synthesizer as s

        seen_histories: list[tuple[str, list | None]] = []

        async def fake_plan(question, history=None):
            seen_histories.append((question, history))
            return [SubQuery(query="子查询1", rationale="")]

        async def fake_retrieve(state, db):
            idx = state.get("current_query_index", 0)
            return {
                "retrieved_chunks": state.get("retrieved_chunks", []) + [{
                    "chunk_id": idx + 1,
                    "content": "片段内容",
                    "document_title": "测试文档",
                    "metadata": {},
                    "scores": {"final": 0.9},
                }],
                "current_query_index": idx + 1,
            }

        async def fake_critique(state):
            return {"critic_verdict": CriticVerdict(sufficient=True, confidence=0.9)}

        async def fake_synthesize(state):
            return {
                "answer": "这是答案",
                "citations": [Citation(chunk_id=1, document_title="测试文档", content_snippet="片段内容")],
                "confidence_score": 0.9,
            }

        with patch.object(p.planner_agent, "plan", side_effect=fake_plan), \
             patch.object(r.retrieval_agent, "retrieve", side_effect=fake_retrieve), \
             patch.object(c.critic_agent, "critique", side_effect=fake_critique), \
             patch.object(s.synthesizer_agent, "synthesize", side_effect=fake_synthesize):
            thread_id = "checkpointer-test-session"
            db = object()
            # 第一轮（带 thread_id，无历史）
            await G._invoke_graph("第一问", db, thread_id=thread_id)
            # 第二轮（同 thread_id，不传历史）
            await G._invoke_graph("第二问", db, thread_id=thread_id)

        assert len(seen_histories) == 2
        q1, h1 = seen_histories[0]
        q2, h2 = seen_histories[1]
        assert q1 == "第一问"
        assert q2 == "第二问"
        # 第二轮传给 planner 的历史应包含第一轮的 user/assistant 消息
        assert h2 is not None
        assert any(m["role"] == "user" and m["content"] == "第一问" for m in h2)
        assert any(m["role"] == "assistant" and m["content"] == "这是答案" for m in h2)

    @pytest.mark.asyncio
    async def test_explicit_history_is_used_when_provided(self):
        """显式传入 history 时应优先使用，而不是从 checkpoint 覆盖。"""
        from app import graph as G
        from app.services.agents import planner as p, retrieval as r
        from app.services.agents import critic as c, synthesizer as s

        seen: list[list | None] = []

        async def fake_plan(question, history=None):
            seen.append(history)
            return [SubQuery(query="子查询1", rationale="")]

        async def fake_retrieve(state, db):
            return {"retrieved_chunks": [], "current_query_index": 1}

        async def fake_critique(state):
            return {"critic_verdict": CriticVerdict(sufficient=True, confidence=0.9)}

        async def fake_synthesize(state):
            return {"answer": "答", "citations": [], "confidence_score": 0.5}

        explicit = [{"role": "user", "content": "上一轮问题"}]
        with patch.object(p.planner_agent, "plan", side_effect=fake_plan), \
             patch.object(r.retrieval_agent, "retrieve", side_effect=fake_retrieve), \
             patch.object(c.critic_agent, "critique", side_effect=fake_critique), \
             patch.object(s.synthesizer_agent, "synthesize", side_effect=fake_synthesize):
            await G._invoke_graph("本轮问题", object(), history=explicit, thread_id="t-explicit")

        assert seen and seen[0] == explicit


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
