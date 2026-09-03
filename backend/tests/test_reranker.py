"""Reranker 接线测试：sigmoid 归一化 + 融合 + 开关调用链（mock CrossEncoder）"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.retriever import HybridRetriever, RetrievalResult


class TestReranker:
    """Reranker 归一化与调用链"""

    def test_sigmoid_normalizes_logits(self):
        r = HybridRetriever(reranker_enabled=True)
        assert abs(r._sigmoid(0.0) - 0.5) < 1e-9
        assert 0.5 < r._sigmoid(5.0) < 1.0
        assert 0.0 < r._sigmoid(-5.0) < 0.5

    @pytest.mark.asyncio
    async def test_rerank_results_logit_defense(self):
        """CrossEncoder.predict 返回原始 logits（超 0-1 范围）时应 sigmoid 归一化再融合"""
        r = HybridRetriever(reranker_enabled=True, rerank_weight=0.3)
        fake = MagicMock()
        fake.predict = MagicMock(return_value=[3.0, -3.0])  # 原始 logits
        r._reranker = fake

        candidates = [
            RetrievalResult(chunk_id=1, content="a", final_score=1.0),
            RetrievalResult(chunk_id=2, content="b", final_score=0.5),
        ]
        out = await r._rerank_results("query", candidates)

        # sigmoid(3)=0.9526 → 1.0*0.7 + 0.9526*0.3 = 0.9858
        # sigmoid(-3)=0.0474 → 0.5*0.7 + 0.0474*0.3 = 0.3642
        assert out[0].chunk_id == 1
        assert abs(out[0].final_score - 0.9858) < 1e-3
        assert abs(out[1].final_score - 0.3642) < 1e-3
        assert 0.0 < out[0].rerank_score < 1.0  # 归一化到 0-1

    @pytest.mark.asyncio
    async def test_rerank_results_probability_passthrough(self):
        """CrossEncoder.predict 已返回 sigmoid 概率（0-1）时应直接使用，不二次压缩"""
        r = HybridRetriever(reranker_enabled=True, rerank_weight=0.3)
        fake = MagicMock()
        fake.predict = MagicMock(return_value=[0.9, 0.1])  # 已是概率
        r._reranker = fake

        candidates = [
            RetrievalResult(chunk_id=1, content="a", final_score=1.0),
            RetrievalResult(chunk_id=2, content="b", final_score=0.5),
        ]
        out = await r._rerank_results("query", candidates)

        # 1.0*0.7 + 0.9*0.3 = 0.97（若错误地二次 sigmoid：sigmoid(0.9)=0.71 → 0.913 ≠ 0.97）
        assert abs(out[0].final_score - 0.97) < 1e-6
        assert abs(out[1].final_score - (0.5 * 0.7 + 0.1 * 0.3)) < 1e-6
        assert abs(out[0].rerank_score - 0.9) < 1e-9

    @pytest.mark.asyncio
    async def test_hybrid_search_reranks_when_enabled(self):
        r = HybridRetriever(top_k=3, reranker_enabled=True, rerank_candidates=5)
        r._index_built = True
        hydrated = [
            RetrievalResult(chunk_id=i, content=f"c{i}", final_score=1.0 - i * 0.1)
            for i in range(5)
        ]
        reranked = sorted(hydrated, key=lambda x: x.final_score, reverse=True)

        with patch.object(r, "ensure_index", AsyncMock()), \
             patch.object(r, "_bm25_search", return_value=[(1, 2.0)]), \
             patch.object(r, "_vector_search", AsyncMock(return_value=[(1, 0.9)])), \
             patch.object(r, "_hydrate_results", AsyncMock(return_value=hydrated)), \
             patch.object(r, "_rerank_results", AsyncMock(return_value=reranked)) as m_rerank:
            res = await r.hybrid_search("q", [0.1] * 1024, AsyncMock(), top_k=3)

        m_rerank.assert_awaited_once()
        assert len(res) == 3

    @pytest.mark.asyncio
    async def test_hybrid_search_skips_reranker_when_disabled(self):
        r = HybridRetriever(top_k=3, reranker_enabled=False)
        r._index_built = True
        hydrated = [
            RetrievalResult(chunk_id=i, content=f"c{i}", final_score=1.0 - i * 0.1)
            for i in range(5)
        ]

        with patch.object(r, "ensure_index", AsyncMock()), \
             patch.object(r, "_bm25_search", return_value=[(1, 2.0)]), \
             patch.object(r, "_vector_search", AsyncMock(return_value=[(1, 0.9)])), \
             patch.object(r, "_hydrate_results", AsyncMock(return_value=hydrated)), \
             patch.object(r, "_rerank_results", AsyncMock()) as m_rerank:
            res = await r.hybrid_search("q", [0.1] * 1024, AsyncMock(), top_k=3)

        m_rerank.assert_not_called()
        assert len(res) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
