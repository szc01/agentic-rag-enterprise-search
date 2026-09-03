"""Agent 编排集成测试（Mock LLM，无需真实 API Key）"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_llm(response_content: str):
    """构造一个可直接替换 agent.llm 的 Mock 对象。

    注意：不能对 ChatOpenAI 实例做 patch.object(llm, "ainvoke")——
    ChatOpenAI 是 pydantic 模型，恢复属性时会触发字段校验直接报错。
    正确做法是把 agent 上的 llm 属性整体替换成 Mock。
    """
    mock_response = MagicMock()
    mock_response.content = response_content
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    return mock_llm


class TestPlannerAgent:
    """Planner Agent 测试"""

    @pytest.mark.asyncio
    async def test_simple_question(self):
        """简单问题应返回单条子查询"""
        from app.services.agents.planner import planner_agent

        mock_llm = _make_mock_llm(
            '[{"query": "什么是 RAG？", "rationale": "简单事实查询"}]'
        )
        with patch.object(planner_agent, "llm", mock_llm):
            result = await planner_agent.plan("什么是 RAG？")
            assert len(result) == 1
            assert "RAG" in result[0].query

    @pytest.mark.asyncio
    async def test_fallback_on_bad_json(self):
        """LLM 输出非法 JSON 时应回退为单查询"""
        from app.services.agents.planner import planner_agent

        mock_llm = _make_mock_llm("这不是 JSON 格式的输出")
        with patch.object(planner_agent, "llm", mock_llm):
            result = await planner_agent.plan("复杂的多部分问题？")
            assert len(result) == 1
            assert result[0].query == "复杂的多部分问题？"


class TestCriticAgent:
    """Critic Agent 测试"""

    @pytest.mark.asyncio
    async def test_sufficient_judgment(self):
        """测试信息充分判定"""
        from app.services.agents.critic import critic_agent

        mock_llm = _make_mock_llm(
            '{"sufficient": true, "confidence": 0.9, "missing_aspects": [], '
            '"suggested_queries": [], "reasoning": "信息完整"}'
        )
        with patch.object(critic_agent, "llm", mock_llm):
            state = {
                "question": "RAG 是什么",
                "retrieved_chunks": [
                    {"content": "RAG 是检索增强生成技术", "document_title": "技术文档"},
                ],
                "iterations": 0,
            }

            result = await critic_agent.critique(state)
            assert result["critic_verdict"].sufficient is True

    @pytest.mark.asyncio
    async def test_max_iterations_force_stop(self):
        """达到最大迭代次数时应强制判定为充分（防死循环）"""
        from app.services.agents.critic import critic_agent

        mock_llm = _make_mock_llm(
            '{"sufficient": false, "confidence": 0.4, "missing_aspects": ["细节"], '
            '"suggested_queries": ["再查一次"], "reasoning": "信息不足"}'
        )
        with patch.object(critic_agent, "llm", mock_llm):
            state = {
                "question": "RAG 是什么",
                "retrieved_chunks": [{"content": "RAG 是检索增强生成", "document_title": "d"}],
                "iterations": 3,  # 达到上限
            }

            result = await critic_agent.critique(state)
            assert result["critic_verdict"].sufficient is True  # 强制终止
            assert "强制终止" in result["critic_verdict"].reasoning


class TestSynthesizerAgent:
    """Synthesizer Agent 测试"""

    @pytest.mark.asyncio
    async def test_answer_with_citations(self):
        """测试带引用的答案生成"""
        from app.services.agents.synthesizer import synthesizer_agent

        mock_llm = _make_mock_llm(
            "RAG 是检索增强生成技术[1]。\n\n```json\n"
            '{"confidence": 0.85, "citations": [{"id": 1, "document_title": "技术文档", '
            '"section": "", "snippet": "RAG 是检索增强生成"}]}\n```'
        )
        with patch.object(synthesizer_agent, "llm", mock_llm):
            state = {
                "question": "RAG 是什么？",
                "retrieved_chunks": [
                    {"content": "RAG 是检索增强生成技术，由 Lewis 等人在 2020 年提出。",
                     "document_title": "技术文档", "scores": {"final": 0.92}},
                ],
                "critic_verdict": None,
            }

            result = await synthesizer_agent.synthesize(state)
            assert "RAG" in result["answer"]
            assert result["confidence_score"] > 0
            assert len(result["citations"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
