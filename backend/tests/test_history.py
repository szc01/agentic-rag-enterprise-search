"""多轮对话历史测试：schema / 格式化 / planner & synthesizer 把历史注入 prompt"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_llm(response_content: str):
    mock_response = MagicMock()
    mock_response.content = response_content
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    return mock_llm


class TestHistoryUtils:
    def test_normalize_history_accepts_dicts_and_objects(self):
        from app.utils.history import normalize_history

        assert normalize_history(None) == []
        assert normalize_history([]) == []

        assert normalize_history([{"role": "user", "content": "hi"}]) == [
            {"role": "user", "content": "hi"}
        ]

        class _Msg:
            role = "assistant"
            content = "hello"

        assert normalize_history([_Msg()]) == [{"role": "assistant", "content": "hello"}]

    def test_format_history_keeps_last_n_turns(self):
        from app.utils.history import format_history

        history = []
        for i in range(5):
            history.append({"role": "user", "content": f"q{i}"})
            history.append({"role": "assistant", "content": f"a{i}"})

        out = format_history(history, max_turns=2)
        assert "q4" in out and "a4" in out
        assert "q3" in out and "a3" in out
        assert "q0" not in out  # 过早的历史被截掉

    def test_format_history_empty(self):
        from app.utils.history import format_history
        assert format_history([]) == ""
        assert format_history(None) == ""


class TestSearchRequestHistory:
    def test_search_request_accepts_history(self):
        from app.schemas.query import SearchRequest

        req = SearchRequest(
            question="它和向量维度有什么关系",
            history=[{"role": "user", "content": "介绍 RAG 的 chunking 策略"}],
        )
        assert req.history[0].role == "user"
        assert req.history[0].content == "介绍 RAG 的 chunking 策略"

    def test_search_request_history_defaults_to_none(self):
        from app.schemas.query import SearchRequest
        assert SearchRequest(question="q").history is None


class TestPlannerHistory:
    @pytest.mark.asyncio
    async def test_plan_injects_history_into_prompt(self):
        from app.services.agents.planner import planner_agent

        mock_llm = _make_mock_llm(
            '[{"query": "RAG chunking 与向量维度的关系", "rationale": ""}]'
        )
        with patch.object(planner_agent, "llm", mock_llm):
            await planner_agent.plan(
                "它和向量维度有什么关系",
                history=[
                    {"role": "user", "content": "介绍 RAG 的 chunking 策略"},
                    {"role": "assistant", "content": "chunking 按标题/段落边界切分文档。"},
                ],
            )

        human_content = mock_llm.ainvoke.call_args[0][0][-1].content
        assert "介绍 RAG 的 chunking 策略" in human_content
        assert "chunking 按标题/段落边界切分文档" in human_content


class TestSynthesizerHistory:
    @pytest.mark.asyncio
    async def test_synthesize_injects_history_into_prompt(self):
        from app.services.agents.synthesizer import synthesizer_agent

        mock_llm = _make_mock_llm(
            "chunk 越大向量维度要求越高[1]。\n\n```json\n"
            '{"confidence": 0.8, "citations": [{"id": 1, "document_title": "d", '
            '"section": "", "snippet": "x"}]}\n```'
        )
        with patch.object(synthesizer_agent, "llm", mock_llm):
            await synthesizer_agent.synthesize({
                "question": "它和向量维度有什么关系",
                "history": [{"role": "user", "content": "介绍 RAG 的 chunking 策略"}],
                "retrieved_chunks": [{
                    "chunk_id": 1,
                    "content": "chunk 内容",
                    "document_title": "d",
                    "metadata": {},
                    "scores": {"final": 0.9},
                }],
                "critic_verdict": None,
            })

        human_content = mock_llm.ainvoke.call_args[0][0][-1].content
        assert "介绍 RAG 的 chunking 策略" in human_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
