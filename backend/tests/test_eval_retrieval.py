"""检索评测脚本指标函数测试（纯函数，不触发 DB / 模型加载）"""
import math
import pytest

from scripts.eval_retrieval import _hit_at, _first_rank, _ndcg_at


class _FakeResult:
    """eval 脚本只用到 results[i].content 做关键词命中判断"""

    def __init__(self, content: str):
        self.content = content


def _results(contents):
    return [_FakeResult(c) for c in contents]


class TestHitAndRank:
    def test_hit_at_true_when_keyword_in_topk(self):
        results = _results(["aaa", "target phrase here", "bbb"])
        assert _hit_at(results, "target phrase", 2) is True
        assert _hit_at(results, "target phrase", 1) is False

    def test_hit_at_case_insensitive(self):
        assert _hit_at(_results(["TARGET PHRASE"]), "target phrase", 1) is True

    def test_first_rank(self):
        results = _results(["aaa", "bbb target", "target again"])
        assert _first_rank(results, "target") == 2

    def test_first_rank_zero_when_missing(self):
        assert _first_rank(_results(["aaa", "bbb"]), "nope") == 0


class TestNDCG:
    def test_ndcg_one_when_relevant_first(self):
        # 相关结果排第 1：DCG == IDCG == 1
        results = _results(["keyword is here", "other", "other", "other", "other"])
        assert _ndcg_at(results, "keyword") == pytest.approx(1.0)

    def test_ndcg_zero_when_no_relevant(self):
        assert _ndcg_at(_results(["a", "b", "c", "d", "e"]), "missing") == 0.0

    def test_ndcg_partial_when_relevant_second(self):
        # 相关结果排第 2：DCG = 1/log2(3)，IDCG = 1
        results = _results(["distractor", "keyword is here", "x", "y", "z"])
        expected = 1.0 / math.log2(3)
        assert _ndcg_at(results, "keyword") == pytest.approx(expected)

    def test_ndcg_two_relevant_keeps_ideal(self):
        # 两个相关（排第 1、2）：理想排序相同 → nDCG == 1
        results = _results(["kw", "kw", "x", "y", "z"])
        assert _ndcg_at(results, "kw") == pytest.approx(1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
