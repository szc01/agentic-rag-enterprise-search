"""Reranker 超时降级 + top_k 截断 + 异常降级 测试（Day 9 Task 5）

覆盖：
1. _safe_rerank 正常路径：等效于 _rerank_results + 截 k
2. 截断：候选数 > rerank_top_k 时只送 top_k 给 _rerank_results
3. 超时降级：asyncio.TimeoutError 时回退到粗排 final_score 排序
4. 异常降级：_rerank_results 抛通用异常时仍能回退
5. rerank_fallback_on_timeout=False 时超时/异常会上抛
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.retriever import HybridRetriever, RetrievalResult


def _make_candidates(n: int) -> list[RetrievalResult]:
    """构造 n 个候选，final_score 从 1.0 递减。"""
    return [
        RetrievalResult(chunk_id=i, content=f"c{i}", final_score=1.0 - i * 0.05)
        for i in range(n)
    ]


class TestSafeRerankNormalPath:
    """正常路径：_safe_rerank 转发给 _rerank_results + 截断"""

    @pytest.mark.asyncio
    async def test_safe_rerank_forwards_and_truncates(self):
        r = HybridRetriever(
            top_k=3,
            reranker_enabled=True,
            rerank_timeout=1.5,
            rerank_top_k=10,
        )
        candidates = _make_candidates(8)
        reranked = sorted(candidates, key=lambda x: x.final_score, reverse=True)
        with patch.object(r, "_rerank_results", AsyncMock(return_value=reranked)) as m:
            out = await r._safe_rerank("q", candidates, k=3)

        m.assert_awaited_once()
        # 候选数 8 < rerank_top_k=10，全部送入
        args, _ = m.call_args
        assert len(args[1]) == 8
        assert len(out) == 3

    @pytest.mark.asyncio
    async def test_safe_rerank_truncates_to_rerank_top_k(self):
        """rerank_top_k > k 且候选 > rerank_top_k 时按 max(k, rerank_top_k) 截断（防止过载）。"""
        r = HybridRetriever(
            top_k=3,
            reranker_enabled=True,
            rerank_timeout=1.5,
            rerank_top_k=8,  # > k=3
        )
        candidates = _make_candidates(20)  # 候选数 > rerank_top_k
        reranked = sorted(candidates[:8], key=lambda x: x.final_score, reverse=True)
        with patch.object(r, "_rerank_results", AsyncMock(return_value=reranked)) as m:
            await r._safe_rerank("q", candidates, k=3)

        args, _ = m.call_args
        assert len(args[1]) == 8  # max(3, 8) = 8，不送全部 20

    @pytest.mark.asyncio
    async def test_safe_rerank_uses_max_of_k_and_topk(self):
        """rerank_top_k < k 时按 k 算（保证至少能返 k 条精排结果）。"""
        r = HybridRetriever(
            top_k=8,
            reranker_enabled=True,
            rerank_timeout=1.5,
            rerank_top_k=3,  # 比 k 小
        )
        candidates = _make_candidates(20)
        reranked = sorted(candidates[: max(8, 3)], key=lambda x: x.final_score, reverse=True)
        with patch.object(r, "_rerank_results", AsyncMock(return_value=reranked)) as m:
            await r._safe_rerank("q", candidates, k=8)

        args, _ = m.call_args
        assert len(args[1]) == 8  # max(k, rerank_top_k) = max(8,3) = 8


class TestSafeRerankTimeoutFallback:
    """超时场景：mock _rerank_results 睡眠超过 rerank_timeout"""

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_coarse_rank(self):
        r = HybridRetriever(
            top_k=3,
            reranker_enabled=True,
            rerank_timeout=0.05,
            rerank_top_k=10,
            rerank_fallback_on_timeout=True,
        )

        async def slow_rerank(*args, **kwargs):
            await asyncio.sleep(0.5)  # 超过 0.05s
            return args[1]

        candidates = _make_candidates(10)
        # expected: 按 final_score 排序的前 3 条
        expected = sorted(candidates, key=lambda x: x.final_score, reverse=True)[:3]

        with patch.object(r, "_rerank_results", side_effect=slow_rerank):
            out = await r._safe_rerank("q", candidates, k=3)

        assert len(out) == 3
        # 超时降级：rerank_score 全部置 0
        assert all(x.rerank_score == 0.0 for x in out)
        # 顺序应按原始 final_score 排序
        for a, b in zip(out, expected):
            assert a.chunk_id == b.chunk_id

    @pytest.mark.asyncio
    async def test_timeout_raises_when_fallback_disabled(self):
        r = HybridRetriever(
            top_k=3,
            reranker_enabled=True,
            rerank_timeout=0.05,
            rerank_top_k=10,
            rerank_fallback_on_timeout=False,
        )

        async def slow_rerank(*args, **kwargs):
            await asyncio.sleep(0.5)
            return args[1]

        candidates = _make_candidates(10)
        with patch.object(r, "_rerank_results", side_effect=slow_rerank):
            with pytest.raises(asyncio.TimeoutError):
                await r._safe_rerank("q", candidates, k=3)


class TestSafeRerankExceptionFallback:
    """异常场景：_rerank_results 抛通用异常"""

    @pytest.mark.asyncio
    async def test_exception_falls_back_to_coarse_rank(self):
        r = HybridRetriever(
            top_k=4,
            reranker_enabled=True,
            rerank_timeout=1.5,
            rerank_top_k=10,
            rerank_fallback_on_timeout=True,
        )

        async def broken_rerank(*args, **kwargs):
            raise RuntimeError("model OOM")

        candidates = _make_candidates(12)
        expected = sorted(candidates, key=lambda x: x.final_score, reverse=True)[:4]

        with patch.object(r, "_rerank_results", side_effect=broken_rerank):
            out = await r._safe_rerank("q", candidates, k=4)

        assert len(out) == 4
        assert all(x.rerank_score == 0.0 for x in out)
        for a, b in zip(out, expected):
            assert a.chunk_id == b.chunk_id

    @pytest.mark.asyncio
    async def test_exception_raises_when_fallback_disabled(self):
        r = HybridRetriever(
            top_k=4,
            reranker_enabled=True,
            rerank_timeout=1.5,
            rerank_top_k=10,
            rerank_fallback_on_timeout=False,
        )

        async def broken_rerank(*args, **kwargs):
            raise RuntimeError("model OOM")

        candidates = _make_candidates(12)
        with patch.object(r, "_rerank_results", side_effect=broken_rerank):
            with pytest.raises(RuntimeError, match="OOM"):
                await r._safe_rerank("q", candidates, k=4)


class TestSafeRerankEdgeCases:
    """边界场景"""

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        r = HybridRetriever(reranker_enabled=True)
        out = await r._safe_rerank("q", [], k=3)
        assert out == []

    @pytest.mark.asyncio
    async def test_config_defaults_applied_when_omitted(self):
        """不传 rerank_timeout / rerank_top_k / rerank_fallback_on_timeout 时读 settings"""
        from app.config import settings

        r = HybridRetriever(reranker_enabled=True)
        assert r.rerank_timeout == settings.rerank_timeout
        assert r.rerank_top_k == settings.rerank_top_k
        assert r.rerank_fallback_on_timeout == settings.rerank_fallback_on_timeout
        # settings 默认值
        assert r.rerank_timeout == 1.5
        assert r.rerank_top_k == 30
        assert r.rerank_fallback_on_timeout is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
