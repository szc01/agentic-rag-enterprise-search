"""LangGraph 编排测试：Mock 各 Agent，验证流转与自循环上限"""
import pytest
from unittest.mock import patch

from app.services.agents.types import SubQuery, CriticVerdict, Citation


class TestAgenticGraph:
    """多步检索图流转测试（不依赖真实 LLM / DB）"""

    @pytest.mark.asyncio
    async def test_graph_completes_with_self_loop(self):
        """Critic 首轮不充分 → 追加子查询自循环一次 → 最终出答案"""
        from app.graph import build_graph
        from app.services.agents import planner as p, retrieval as r
        from app.services.agents import critic as c, synthesizer as s

        async def fake_plan(question, history=None):
            return [SubQuery(query="子查询1", rationale=""), SubQuery(query="子查询2", rationale="")]

        async def fake_retrieve(state, db):
            idx = state.get("current_query_index", 0)
            return {
                "retrieved_chunks": state.get("retrieved_chunks", []) + [{
                    "chunk_id": idx + 1,
                    "content": f"片段{idx + 1}",
                    "document_title": "测试文档",
                    "scores": {"final": 0.9},
                }],
                "current_query_index": idx + 1,
            }

        async def fake_critique(state):
            # 第一轮不充分（建议补充），之后充分 → 触发一次自循环
            sufficient = state.get("iterations", 0) >= 1
            return {
                "critic_verdict": CriticVerdict(
                    sufficient=sufficient,
                    confidence=0.8,
                    suggested_queries=[] if sufficient else ["补充查询"],
                    reasoning="test",
                )
            }

        async def fake_synthesize(state):
            return {
                "answer": "这是答案",
                "citations": [Citation(chunk_id=1, document_title="测试文档", content_snippet="片段1")],
                "confidence_score": 0.85,
            }

        with patch.object(p.planner_agent, "plan", side_effect=fake_plan), \
             patch.object(r.retrieval_agent, "retrieve", side_effect=fake_retrieve), \
             patch.object(c.critic_agent, "critique", side_effect=fake_critique), \
             patch.object(s.synthesizer_agent, "synthesize", side_effect=fake_synthesize):
            graph = build_graph().compile()
            final = await graph.ainvoke(
                {"question": "测试问题"},
                config={"configurable": {"db": object()}},
            )

        assert final["answer"] == "这是答案"
        assert final["iterations"] <= 3
        # 2 个原始子查询 + 1 个补充子查询 = 3 次检索
        assert len(final["retrieved_chunks"]) == 3

    @pytest.mark.asyncio
    async def test_graph_caps_iterations_at_max(self):
        """Critic 一直不充分时，最多 3 轮自循环后强制去 Synthesizer"""
        from app.graph import build_graph
        from app.services.agents import planner as p, retrieval as r
        from app.services.agents import critic as c, synthesizer as s

        async def fake_plan(question, history=None):
            return [SubQuery(query="子查询1", rationale="")]

        async def fake_retrieve(state, db):
            idx = state.get("current_query_index", 0)
            return {"current_query_index": idx + 1}

        async def fake_critique(state):
            return {
                "critic_verdict": CriticVerdict(
                    sufficient=False,
                    confidence=0.4,
                    suggested_queries=["继续补充查询"],
                    reasoning="永远不充分",
                )
            }

        async def fake_synthesize(state):
            return {"answer": "有限信息下的答案", "citations": [], "confidence_score": 0.4}

        with patch.object(p.planner_agent, "plan", side_effect=fake_plan), \
             patch.object(r.retrieval_agent, "retrieve", side_effect=fake_retrieve), \
             patch.object(c.critic_agent, "critique", side_effect=fake_critique), \
             patch.object(s.synthesizer_agent, "synthesize", side_effect=fake_synthesize):
            graph = build_graph().compile()
            final = await graph.ainvoke(
                {"question": "测试问题"},
                config={"configurable": {"db": object()}},
            )

        assert final["iterations"] == 3  # 达到上限强制终止
        assert final["answer"] == "有限信息下的答案"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
