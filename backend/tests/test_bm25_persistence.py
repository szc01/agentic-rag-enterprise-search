"""BM25 索引持久化单元 + 集成测试（Day 9 Task 4）

覆盖：
- load_snapshot: 表为空 / schema 不兼容 / 反序列化字段缺失 / 一致性校验失败
- save_snapshot: mock session 的 UPSERT 行为 + 失败回滚
- apply_snapshot: 数据结构还原正确性
- retriever 集成: ensure_index 优先走 snapshot / fallback 全量重建 + 落盘
                  add_chunks / remove_chunks 触发 save_snapshot
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.bm25_persistence import (
    BM25Snapshot,
    SCHEMA_VERSION,
    load_snapshot,
    save_snapshot,
    apply_snapshot,
)
from app.services.retriever import HybridRetriever


# ── 1. apply_snapshot 单元测试（纯内存）───────────────────────────


class TestApplySnapshot:
    def test_apply_restores_in_memory_structures(self):
        r = HybridRetriever()
        snap = BM25Snapshot(
            postings={
                "深度学习": {1: 2, 37: 1},
                "向量": {2: 1, 37: 1},
            },
            chunk_freqs={
                1: {"深度学习": 2},
                2: {"向量": 1},
                37: {"深度学习": 1, "向量": 1},
            },
            doc_lengths={1: 100, 2: 50, 37: 80},
            doc_freq={"深度学习": 2, "向量": 2},
            chunk_ids=[1, 2, 37],
            total_tokens=230,
        )
        apply_snapshot(r, snap)

        assert r._index_built is True
        assert r._idf_dirty is True
        assert r._chunk_ids == {1, 2, 37}
        assert r._total_tokens == 230
        assert r._postings == snap.postings
        assert r._chunk_freqs == snap.chunk_freqs
        assert r._doc_lengths == snap.doc_lengths
        assert r._doc_freq == snap.doc_freq

    def test_apply_resets_idf(self):
        r = HybridRetriever()
        r._idf = {"stale": 9.9}  # 模拟残留状态
        snap = BM25Snapshot(
            postings={"x": {1: 1}},
            chunk_freqs={1: {"x": 1}},
            doc_lengths={1: 10},
            doc_freq={"x": 1},
            chunk_ids=[1],
            total_tokens=10,
        )
        apply_snapshot(r, snap)
        assert r._idf == {}
        assert r._idf_dirty is True  # 触发懒计算


# ── 2. load_snapshot 单元测试（mock DB session）─────────────────────


class TestLoadSnapshot:
    @staticmethod
    def _make_db(row=None, count=None, raise_on_select=False):
        """构造一个 mock AsyncSession，模拟两种 select 路径"""
        db = AsyncMock()
        call_count = {"n": 0}

        async def execute(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # 第一次是 BM25IndexState 查询
                if raise_on_select:
                    raise RuntimeError("simulated PG outage")
                r = MagicMock()
                r.scalar_one_or_none.return_value = row
                return r
            # 第二次是 chunks 表 count(*)
            r = MagicMock()
            r.scalar_one.return_value = count
            return r

        db.execute = execute
        return db

    @pytest.mark.asyncio
    async def test_returns_none_when_table_empty(self):
        db = self._make_db(row=None, count=42)
        snap = await load_snapshot(db)
        assert snap is None

    @pytest.mark.asyncio
    async def test_returns_none_when_state_dict_empty(self):
        empty_row = MagicMock()
        empty_row.state = {}
        empty_row.chunk_count = 0
        db = self._make_db(row=empty_row, count=0)
        snap = await load_snapshot(db)
        assert snap is None

    @pytest.mark.asyncio
    async def test_returns_none_on_schema_version_mismatch(self):
        bad_row = MagicMock()
        bad_row.state = {"version": 999, "postings": {}, "chunk_freqs": {},
                         "doc_lengths": {}, "doc_freq": {}, "chunk_ids": [],
                         "total_tokens": 0}
        bad_row.chunk_count = 0
        db = self._make_db(row=bad_row, count=0)
        snap = await load_snapshot(db)
        assert snap is None

    @pytest.mark.asyncio
    async def test_returns_none_on_chunk_count_mismatch(self):
        row = MagicMock()
        row.state = {"version": SCHEMA_VERSION, "postings": {}, "chunk_freqs": {},
                     "doc_lengths": {}, "doc_freq": {}, "chunk_ids": [1, 2, 3],
                     "total_tokens": 0}
        row.chunk_count = 3
        db = self._make_db(row=row, count=99)  # 实际 99 vs 快照 3
        snap = await load_snapshot(db)
        assert snap is None

    @pytest.mark.asyncio
    async def test_returns_none_on_corrupted_field(self):
        row = MagicMock()
        row.state = {"version": SCHEMA_VERSION, "postings": "not_a_dict"}  # 类型错
        row.chunk_count = 0
        db = self._make_db(row=row, count=0)
        snap = await load_snapshot(db)
        assert snap is None

    @pytest.mark.asyncio
    async def test_returns_none_on_select_exception(self):
        db = self._make_db(raise_on_select=True)
        snap = await load_snapshot(db)
        assert snap is None

    @pytest.mark.asyncio
    async def test_loads_valid_snapshot(self):
        row = MagicMock()
        row.state = {
            "version": SCHEMA_VERSION,
            "postings": {"深度学习": {"1": 2}, "向量": {"2": 1}},
            "chunk_freqs": {"1": {"深度学习": 2}, "2": {"向量": 1}},
            "doc_lengths": {"1": 100, "2": 50},
            "doc_freq": {"深度学习": 1, "向量": 1},
            "chunk_ids": [1, 2],
            "total_tokens": 150,
        }
        row.chunk_count = 2
        db = self._make_db(row=row, count=2)

        snap = await load_snapshot(db)
        assert snap is not None
        assert snap.chunk_ids == [1, 2]
        assert snap.postings == {"深度学习": {1: 2}, "向量": {2: 1}}
        assert snap.total_tokens == 150
        # int keys 正确转换
        assert snap.doc_lengths[1] == 100


# ── 3. save_snapshot 单元测试 ────────────────────────────────


class TestSaveSnapshot:
    @pytest.mark.asyncio
    async def test_skipped_when_index_not_built(self):
        r = HybridRetriever()
        # 默认 _index_built=False
        assert r._index_built is False
        ok = await save_snapshot(r, AsyncMock())
        assert ok is False

    @pytest.mark.asyncio
    async def test_upsert_existing_row(self):
        r = HybridRetriever()
        r._index_built = True
        r._postings = {"深度学习": {1: 2}}
        r._chunk_freqs = {1: {"深度学习": 2}}
        r._doc_lengths = {1: 100}
        r._doc_freq = {"深度学习": 1}
        r._chunk_ids = {1}
        r._total_tokens = 100

        # mock session：第一次 SELECT 返回已存在的 row
        existing = MagicMock()
        session = AsyncMock()

        async def execute(stmt):
            r = MagicMock()
            r.scalar_one_or_none.return_value = existing
            return r
        session.execute = execute
        session.commit = AsyncMock()

        ok = await save_snapshot(r, session)
        assert ok is True
        assert existing.state["version"] == SCHEMA_VERSION
        assert existing.state["chunk_count"] == 1
        assert existing.chunk_count == 1
        assert existing.total_tokens == 100
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_new_row_when_missing(self):
        r = HybridRetriever()
        r._index_built = True
        r._postings = {"x": {1: 1}}
        r._chunk_freqs = {1: {"x": 1}}
        r._doc_lengths = {1: 5}
        r._doc_freq = {"x": 1}
        r._chunk_ids = {1}
        r._total_tokens = 5

        session = AsyncMock()
        added = []

        async def execute(stmt):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None  # 没找到行
            return r
        session.execute = execute

        real_db_add = MagicMock(side_effect=lambda obj: added.append(obj))
        session.add = real_db_add
        session.commit = AsyncMock()

        ok = await save_snapshot(r, session)
        assert ok is True
        assert len(added) == 1  # 新建一行
        assert added[0].singleton_id == "singleton"

    @pytest.mark.asyncio
    async def test_rollback_on_commit_failure(self):
        r = HybridRetriever()
        r._index_built = True
        r._postings = {"x": {1: 1}}
        r._chunk_freqs = {1: {"x": 1}}
        r._doc_lengths = {1: 5}
        r._doc_freq = {"x": 1}
        r._chunk_ids = {1}
        r._total_tokens = 5

        session = AsyncMock()

        async def execute(stmt):
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r
        session.execute = execute
        session.add = MagicMock()
        session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
        session.rollback = AsyncMock()

        ok = await save_snapshot(r, session)
        assert ok is False
        session.rollback.assert_awaited_once()


# ── 4. retriever 集成测试（mock bm25_persistence 子模块）───────────


class TestRetrieverPersistenceIntegration:
    """验证 ensure_index / add_chunks / remove_chunks 与持久化的协作"""

    @pytest.mark.asyncio
    async def test_ensure_index_uses_snapshot_when_available(self):
        r = HybridRetriever()
        snap = BM25Snapshot(
            postings={"深度学习": {1: 2}},
            chunk_freqs={1: {"深度学习": 2}},
            doc_lengths={1: 100},
            doc_freq={"深度学习": 1},
            chunk_ids=[1],
            total_tokens=100,
        )

        with patch("app.services.bm25_persistence.load_snapshot",
                    AsyncMock(return_value=snap)) as m_load, \
             patch("app.services.bm25_persistence.save_snapshot",
                    AsyncMock(return_value=True)) as m_save, \
             patch.object(r, "_load_chunks_from_db",
                          AsyncMock(side_effect=AssertionError(
                              "should not be called when snapshot is valid"))):
            await r.ensure_index(AsyncMock())

        m_load.assert_awaited_once()
        m_save.assert_not_called()  # snapshot 命中 → 不落盘
        # 内存索引被 snapshot 灌入
        assert r._index_built is True
        assert r._chunk_ids == {1}
        assert r._postings == {"深度学习": {1: 2}}

    @pytest.mark.asyncio
    async def test_ensure_index_falls_back_to_full_rebuild(self):
        r = HybridRetriever()

        chunks = [{"chunk_id": 1, "content": "深度学习"}, {"chunk_id": 2, "content": "向量检索"}]
        with patch("app.services.bm25_persistence.load_snapshot",
                    AsyncMock(return_value=None)), \
             patch("app.services.bm25_persistence.save_snapshot",
                    AsyncMock(return_value=True)) as m_save, \
             patch.object(r, "_load_chunks_from_db",
                          AsyncMock(return_value=chunks)):
            await r.ensure_index(AsyncMock())

        # 全量重建触发 + 之后立刻 save
        m_save.assert_awaited_once()
        assert r._index_built is True
        assert len(r._chunk_ids) == 2

    @pytest.mark.asyncio
    async def test_add_chunks_calls_save_after_increment(self):
        r = HybridRetriever()
        r._index_built = True  # 跳过 ensure_index
        r._postings = {}
        r._chunk_freqs = {}
        r._doc_lengths = {}
        r._doc_freq = {}
        r._chunk_ids = set()
        r._total_tokens = 0
        r._idf = {}

        new_chunks = [{"chunk_id": 99, "content": "测试新增"}]
        with patch.object(r, "ensure_index", AsyncMock()), \
             patch("app.services.bm25_persistence.save_snapshot",
                    AsyncMock(return_value=True)) as m_save:
            await r.add_chunks(new_chunks, AsyncMock())

        m_save.assert_awaited_once()
        assert 99 in r._chunk_ids
        assert r._index_built is True

    @pytest.mark.asyncio
    async def test_remove_chunks_calls_save_after_decrement(self):
        r = HybridRetriever()
        r._index_built = True
        r._postings = {"x": {1: 1}}
        r._chunk_freqs = {1: {"x": 1}}
        r._doc_lengths = {1: 5}
        r._doc_freq = {"x": 1}
        r._chunk_ids = {1}
        r._total_tokens = 5
        r._idf = {}

        with patch.object(r, "ensure_index", AsyncMock()), \
             patch("app.services.bm25_persistence.save_snapshot",
                    AsyncMock(return_value=True)) as m_save:
            await r.remove_chunks([1], AsyncMock())

        m_save.assert_awaited_once()
        assert 1 not in r._chunk_ids

    @pytest.mark.asyncio
    async def test_remove_unknown_chunk_id_does_not_save(self):
        """删除不存在的 chunk_id 时不触发 save（无变化）。"""
        r = HybridRetriever()
        r._index_built = True
        r._postings = {}
        r._chunk_freqs = {}
        r._doc_lengths = {}
        r._doc_freq = {}
        r._chunk_ids = set()
        r._total_tokens = 0
        r._idf = {}

        with patch.object(r, "ensure_index", AsyncMock()), \
             patch("app.services.bm25_persistence.save_snapshot",
                    AsyncMock(return_value=True)) as m_save:
            await r.remove_chunks([99999], AsyncMock())

        m_save.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
