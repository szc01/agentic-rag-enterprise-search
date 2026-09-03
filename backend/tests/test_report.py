"""调研报告功能测试：报告模式 Synthesizer + 图编排路由（Mock LLM，无需真实 Key）"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agents.types import SubQuery, CriticVerdict, Citation


def _make_mock_llm(response_content: str):
    """构造替换 agent.llm 的 Mock（返回指定文本）。"""
    mock_response = MagicMock()
    mock_response.content = response_content
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    return mock_llm


REPORT_BODY = (
    "## 背景\n检索增强生成（RAG）通过外部知识库增强生成质量[1]。\n\n"
    "## 现状\n企业知识管理平台广泛采用 RAG[1]。\n\n"
    "## 技术方案\n混合检索结合 BM25 与向量检索[1]。\n\n"
    "## 案例\n某平台用 RAG 提升问答准确率[1]。\n\n"
    "## 趋势\nRAG 与 Agentic 编排深度融合[1]。"
)


class TestSynthesizerReportMode:
    """Synthesizer 报告模式单元测试"""

    @pytest.mark.asyncio
    async def test_report_with_fixed_sections_and_citations(self):
        from app.services.agents.synthesizer import synthesizer_agent

        mock_llm = _make_mock_llm(REPORT_BODY + "\n\n## 参考文献\n[1] 《技术文档》")
        with patch.object(synthesizer_agent, "llm", mock_llm):
            state = {
                "question": "RAG chunking best practices",
                "retrieved_chunks": [{
                    "chunk_id": 1,
                    "content": "RAG 是检索增强生成技术",
                    "document_title": "技术文档",
                    "metadata": {},
                    "scores": {"final": 0.9},
                }],
                "critic_verdict": CriticVerdict(sufficient=True, confidence=0.85),
            }
            result = await synthesizer_agent.synthesize_report(state)

        assert "## 背景" in result["answer"]
        assert "## 现状" in result["answer"]
        assert "## 技术方案" in result["answer"]
        assert "## 案例" in result["answer"]
        assert "## 趋势" in result["answer"]
        assert len(result["citations"]) == 1
        assert result["citations"][0].document_title == "技术文档"
        assert result["confidence_score"] == 0.85  # 取自 Critic 判定

    @pytest.mark.asyncio
    async def test_report_appends_reference_section_when_missing(self):
        from app.services.agents.synthesizer import synthesizer_agent

        # 正文有 [1] 引用但缺参考文献章节
        mock_llm = _make_mock_llm(REPORT_BODY)
        with patch.object(synthesizer_agent, "llm", mock_llm):
            state = {
                "question": "RAG",
                "retrieved_chunks": [{
                    "chunk_id": 7,
                    "content": "RAG 检索增强",
                    "document_title": "文档A",
                    "metadata": {"section": "背景"},
                    "scores": {"final": 0.8},
                }],
                "critic_verdict": None,
            }
            result = await synthesizer_agent.synthesize_report(state)

        assert "## 参考文献" in result["answer"]
        assert "[1]" in result["answer"]
        assert result["citations"][0].chunk_id == 7
        assert result["confidence_score"] == 0.7  # 无 Critic 时默认值


class TestReportGraphRouting:
    """图编排在报告模式下的路由与深度上限"""

    @pytest.mark.asyncio
    async def test_graph_routes_to_report_synthesizer(self):
        from app.graph import build_graph
        from app.services.agents import planner as p, retrieval as r
        from app.services.agents import critic as c, synthesizer as s

        async def fake_plan(question, history=None):
            return [SubQuery(query="子查询1", rationale="")]

        async def fake_retrieve(state, db):
            idx = state.get("current_query_index", 0)
            return {
                "retrieved_chunks": [{
                    "chunk_id": 1, "content": "片段", "document_title": "d",
                    "scores": {"final": 0.9},
                }],
                "current_query_index": idx + 1,
            }

        async def fake_critique(state):
            return {
                "critic_verdict": CriticVerdict(sufficient=True, confidence=0.8, reasoning="ok")
            }

        async def fake_synthesize_report(state):
            assert state.get("report_mode") is True
            return {
                "answer": "## 背景\n报告内容",
                "citations": [Citation(chunk_id=1, document_title="d", content_snippet="片段")],
                "confidence_score": 0.8,
            }

        with patch.object(p.planner_agent, "plan", side_effect=fake_plan), \
             patch.object(r.retrieval_agent, "retrieve", side_effect=fake_retrieve), \
             patch.object(c.critic_agent, "critique", side_effect=fake_critique), \
             patch.object(s.synthesizer_agent, "synthesize_report", side_effect=fake_synthesize_report):
            graph = build_graph().compile()
            final = await graph.ainvoke(
                {"question": "主题", "report_mode": True, "max_iterations": 2},
                config={"configurable": {"db": object()}},
            )

        assert "报告内容" in final["answer"]
        assert final["report_mode"] is True

    @pytest.mark.asyncio
    async def test_depth_caps_report_iterations(self):
        """depth=1（max_iterations=1）时即使 Critic 不充分也只迭代一轮"""
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
                    suggested_queries=["继续补充"],
                    reasoning="永远不充分",
                )
            }

        async def fake_synthesize_report(state):
            return {"answer": "报告", "citations": [], "confidence_score": 0.4}

        with patch.object(p.planner_agent, "plan", side_effect=fake_plan), \
             patch.object(r.retrieval_agent, "retrieve", side_effect=fake_retrieve), \
             patch.object(c.critic_agent, "critique", side_effect=fake_critique), \
             patch.object(s.synthesizer_agent, "synthesize_report", side_effect=fake_synthesize_report):
            graph = build_graph().compile()
            final = await graph.ainvoke(
                {"question": "主题", "report_mode": True, "max_iterations": 1},
                config={"configurable": {"db": object()}},
            )

        assert final["iterations"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
