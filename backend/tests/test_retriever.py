"""混合检索器测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.retriever import HybridRetriever, RetrievalResult


class TestHybridRetriever:
    """混合检索器单元测试"""

    def setup_method(self):
        self.retriever = HybridRetriever(top_k=5)

    def test_build_bm25_index(self):
        """测试 BM25 索引构建"""
        chunks = [
            {"chunk_id": 1, "content": "RAG 是检索增强生成技术"},
            {"chunk_id": 2, "content": "LangChain 是 LLM 应用开发框架"},
            {"chunk_id": 3, "content": "向量数据库存储嵌入向量"},
        ]
        self.retriever.build_bm25_index(chunks)
        assert self.retriever._index_built is True

    def test_rrf_fusion_ranks_chunk_in_both_lists_first(self):
        """RRF 融合：同时出现在两路的结果应排最前"""
        bm25 = [(1, 2.0), (2, 1.0)]
        vector = [(2, 0.9), (3, 0.8)]
        fused = self.retriever._rrf_fuse(bm25, vector, top_k=3)

        ids = [cid for cid, _ in fused]
        assert ids[0] == 2          # chunk 2 在两路都出现
        assert len(ids) == 3
        assert all(0.0 <= s <= 1.0 for _, s in fused)  # 归一化到 0-1

    @pytest.mark.asyncio
    async def test_ensure_index_builds_from_db(self):
        """首次检索时应从 DB 全量加载 chunks 构建 BM25"""
        with patch.object(self.retriever, "_load_chunks_from_db", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = [
                {"chunk_id": 1, "content": "RAG 检索增强"},
                {"chunk_id": 2, "content": "向量数据库"},
            ]
            await self.retriever.ensure_index(AsyncMock())
            assert self.retriever._index_built is True
            assert len(self.retriever._chunk_ids) == 2

    @pytest.mark.asyncio
    async def test_add_remove_chunks_matches_full_rebuild(self):
        """增量增删后 BM25 检索结果应与「全量重建」一致"""
        chunks = [
            {"chunk_id": 1, "content": "RAG 是检索增强生成技术"},
            {"chunk_id": 2, "content": "向量数据库存储嵌入向量"},
            {"chunk_id": 3, "content": "LangChain 是 LLM 应用开发框架"},
        ]
        # 增量路径：先建 2 个 → 增 1 个 → 删 1 个
        inc = HybridRetriever(top_k=5)
        inc.build_bm25_index(chunks[:2])
        await inc.add_chunks([chunks[2]], db=None)
        await inc.remove_chunks([1], db=None)

        # 全量重建等价的最终索引 = {chunk 2, chunk 3}
        full = HybridRetriever(top_k=5)
        full.build_bm25_index([chunks[1], chunks[2]])

        for query in ("RAG 检索", "向量 数据库", "LangChain 框架"):
            assert inc._bm25_search(query, 10) == full._bm25_search(query, 10)

    @pytest.mark.asyncio
    async def test_add_remove_chunks_idempotent(self):
        """重复增删（幂等）不应破坏索引"""
        chunks = [
            {"chunk_id": 1, "content": "RAG 是检索增强生成技术"},
            {"chunk_id": 2, "content": "向量数据库存储嵌入向量"},
            {"chunk_id": 3, "content": "LangChain 是 LLM 应用开发框架"},
        ]
        self.retriever.build_bm25_index(chunks)
        await self.retriever.add_chunks([chunks[0]], db=None)  # 已存在，跳过
        await self.retriever.remove_chunks([999], db=None)      # 不存在，跳过
        assert len(self.retriever._chunk_ids) == 3
        # "LangChain" 只在 chunk 3 出现，应命中 chunk 3
        assert self.retriever._bm25_search("LangChain", 10)[0][0] == 3

    @pytest.mark.asyncio
    async def test_hybrid_search_flow(self):
        """hybrid_search 应依次执行：ensure_index → BM25 → 向量 → RRF → 回填"""
        expected = [RetrievalResult(chunk_id=1, content="x", final_score=1.0)]
        self.retriever._index_built = True  # 模拟已建索引，使 BM25 分支生效
        with patch.object(self.retriever, "ensure_index", new_callable=AsyncMock) as m_ensure, \
             patch.object(self.retriever, "_bm25_search", return_value=[(1, 2.0)]) as m_bm25, \
             patch.object(self.retriever, "_vector_search", new_callable=AsyncMock, return_value=[(1, 0.85)]) as m_vec, \
             patch.object(self.retriever, "_hydrate_results", new_callable=AsyncMock, return_value=expected) as m_hydrate:
            results = await self.retriever.hybrid_search(
                query="什么是 RAG",
                query_embedding=[0.1] * 1024,
                db=AsyncMock(),
                top_k=3,
            )

            assert results == expected
            m_ensure.assert_awaited_once()
            m_bm25.assert_called_once()
            m_vec.assert_awaited_once()
            m_hydrate.assert_awaited_once()
            # RRF 融合结果应作为回填输入
            ranked = m_hydrate.await_args.args[0]
            assert ranked[0][0] == 1

    def test_tokenize_chinese(self):
        """测试中文分词"""
        tokens = self.retriever._tokenize("RAG技术是什么")
        # 应包含英文 token 和中文词
        assert "rag" in tokens or any("rag" in t for t in tokens)
        assert len(tokens) > 0

    def test_tokenize_jieba_chinese_words(self):
        """jieba 分词应产出语义完整的中文词"""
        tokens = self.retriever._tokenize("如何分块更有利于检索质量")
        assert "分块" in tokens
        assert "检索" in tokens
        assert "质量" in tokens

    def test_tokenize_filters_stopwords(self):
        """停用词（如何/更/的/是/什么）应被过滤"""
        tokens = self.retriever._tokenize("如何分块更有利于检索质量")
        assert "如何" not in tokens
        assert "更" not in tokens
        assert "是" not in tokens

    def test_tokenize_keeps_english_tokens(self):
        """英文 / 数字 / 下划线按连续字母数字串切分保持不变"""
        tokens = self.retriever._tokenize("PGVector 支持 HNSW_index_2024 索引")
        assert "pgvector" in tokens
        assert "hnsw_index_2024" in tokens

    def test_tokenize_char_window_kept_for_comparison(self):
        """旧版字符滑动窗口逻辑应保留，产出双字 bigram"""
        tokens = self.retriever._tokenize_char_window("检索增强")
        assert "检索" in tokens
        assert "索增" in tokens

    def test_resolve_enhance(self):
        """enhance 参数解析：none/rewrite/hyde/auto"""
        assert self.retriever._resolve_enhance("none") == (False, False)
        assert self.retriever._resolve_enhance("rewrite") == (True, False)
        assert self.retriever._resolve_enhance("hyde") == (False, True)
        # auto 读配置（默认关闭）
        assert self.retriever._resolve_enhance("auto") == (False, False)

    def test_rrf_merge_results_ranks_chunk_in_multiple_lists_first(self):
        """多查询 RRF 合并：同时出现在多个列表的结果应排最前，分数归一化到 0-1"""
        r1 = RetrievalResult(chunk_id=1, content="a")
        r2 = RetrievalResult(chunk_id=2, content="b")
        r3 = RetrievalResult(chunk_id=3, content="c")
        merged = self.retriever._rrf_merge_results([[r2, r3], [r1, r2]], top_k=3)
        ids = [r.chunk_id for r in merged]
        assert ids[0] == 2
        assert len(ids) == 3
        assert all(0.0 <= r.final_score <= 1.0 for r in merged)

    @pytest.mark.asyncio
    async def test_hybrid_search_mode_bm25_skips_vector(self):
        """mode="bm25" 应只走 BM25，不调用向量检索"""
        expected = [RetrievalResult(chunk_id=1, content="x", final_score=2.0)]
        self.retriever._index_built = True
        with patch.object(self.retriever, "ensure_index", new_callable=AsyncMock) as m_ensure, \
             patch.object(self.retriever, "_bm25_search", return_value=[(1, 2.0)]) as m_bm25, \
             patch.object(self.retriever, "_vector_search", new_callable=AsyncMock) as m_vec, \
             patch.object(self.retriever, "_hydrate_results", new_callable=AsyncMock, return_value=expected) as m_hydrate:
            results = await self.retriever.hybrid_search(
                query="什么是 RAG",
                query_embedding=[0.1] * 1024,
                db=AsyncMock(),
                top_k=3,
                mode="bm25",
            )
            assert results == expected
            m_bm25.assert_called_once()
            m_vec.assert_not_awaited()
            m_hydrate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hybrid_search_mode_vector_skips_bm25(self):
        """mode="vector" 应只走向量检索，不调用 BM25"""
        expected = [RetrievalResult(chunk_id=1, content="x", final_score=0.9)]
        self.retriever._index_built = True
        with patch.object(self.retriever, "ensure_index", new_callable=AsyncMock) as m_ensure, \
             patch.object(self.retriever, "_bm25_search", return_value=[(1, 2.0)]) as m_bm25, \
             patch.object(self.retriever, "_vector_search", new_callable=AsyncMock, return_value=[(1, 0.85)]) as m_vec, \
             patch.object(self.retriever, "_hydrate_results", new_callable=AsyncMock, return_value=expected) as m_hydrate:
            results = await self.retriever.hybrid_search(
                query="什么是 RAG",
                query_embedding=[0.1] * 1024,
                db=AsyncMock(),
                top_k=3,
                mode="vector",
            )
            assert results == expected
            m_vec.assert_awaited_once()
            m_bm25.assert_not_called()
            m_hydrate.assert_awaited_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
