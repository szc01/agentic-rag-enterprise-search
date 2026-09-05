"""混合检索器：BM25（稀疏）+ 向量（稠密）+ Reranker（重排）"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Optional

import jieba

logger = logging.getLogger(__name__)

# jieba 首次分词会打印 "Building prefix dict..." 等 DEBUG 日志，压到 WARNING 减少噪声
jieba.setLogLevel(logging.WARNING)

# RRF 融合常数（经典取值 60）
RRF_K = 60

# 中文停用词表（BM25 分词时过滤高频虚词/代词/标点，保留内容词）
CHINESE_STOPWORDS = frozenset({
    "的", "了", "和", "与", "或", "及", "以及", "并且", "而且", "但是", "然而",
    "在", "是", "有", "为", "被", "把", "对", "向", "从", "到", "于", "由",
    "这", "那", "其", "该", "此", "之", "个", "些", "各", "每", "某", "等",
    "而", "但", "并", "且", "也", "都", "就", "要", "能", "会", "可以", "可",
    "我们", "你们", "他们", "它们", "自己", "什么", "怎么", "如何", "为什么",
    "哪些", "哪个", "这个", "那个", "这些", "那些", "一个", "一种", "一种",
    "进行", "通过", "以及", "中", "上", "下", "内", "外", "时", "后", "前",
    "不", "没", "无", "非", "更", "最", "较", "很", "太", "非常", "还", "又",
    "再", "着", "过", "了", "呢", "吗", "啊", "吧", "么", "哦", "嗯", "呀",
})


@dataclass
class RetrievalResult:
    """单条检索结果（content/document_id 等由 hydrate 从数据库回填）"""
    chunk_id: int
    content: str = ""
    document_id: int = 0
    document_title: str = ""
    metadata: dict = field(default_factory=dict)
    # 分数
    bm25_score: float = 0.0
    vector_score: float = 0.0       # 余弦相似度 (0-1)
    rerank_score: float = 0.0       # Reranker 分数 (0-1)
    final_score: float = 0.0        # 最终融合分数（RRF 归一化到 0-1）


class HybridRetriever:
    """
    混合检索管线：

      1. BM25 稀疏检索 → 关键词精确匹配（处理专有名词/缩写）
      2. 向量稠密检索 → pgvector 余弦距离（走 HNSW 索引）
      3. RRF 融合 → 融合两路排序
      4. （可选）BGE-Reranker 重排 → 对粗排 top-N 候选精排

    BM25 索引为内存倒排结构（term -> {chunk_id: tf} + term -> doc_freq），首次检索时
    从 PostgreSQL 全量加载构建；之后文档入库/删除通过 add_chunks / remove_chunks 增量维护，
    不再全量重建。
    """

    def __init__(
        self,
        bm25_weight: float = 0.3,
        vector_weight: float = 0.4,
        rerank_weight: float = 0.3,
        top_k: int = 10,
        reranker_enabled: bool | None = None,
        rerank_candidates: int = 20,
        rerank_timeout: float | None = None,
        rerank_top_k: int | None = None,
        rerank_fallback_on_timeout: bool | None = None,
    ):
        from app.config import settings

        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.rerank_weight = rerank_weight
        self.top_k = top_k
        # 是否启用 Reranker（None 时读取配置，便于对比实验一键开关）
        self.reranker_enabled = (
            settings.reranker_enabled if reranker_enabled is None else reranker_enabled
        )
        # Reranker 重排的候选集大小（先粗排取 top-N，再精排）
        self.rerank_candidates = rerank_candidates
        # Day 9 Task 5：超时 + 截断 + 降级开关（None 时读 settings）
        self.rerank_timeout = (
            settings.rerank_timeout if rerank_timeout is None else rerank_timeout
        )
        self.rerank_top_k = (
            settings.rerank_top_k if rerank_top_k is None else rerank_top_k
        )
        self.rerank_fallback_on_timeout = (
            settings.rerank_fallback_on_timeout
            if rerank_fallback_on_timeout is None
            else rerank_fallback_on_timeout
        )

        # 查询增强开关（默认读配置；eval 时通过 hybrid_search(enhance=...) 覆盖）
        self.query_rewrite_enabled = settings.query_rewrite_enabled
        self.hyde_enabled = settings.hyde_enabled

        # BM25 倒排索引（自定义内存结构，支持增量增删；见 _add_chunk / _remove_chunk）
        self._postings: dict[str, dict[int, int]] = {}      # term -> {chunk_id: tf}
        self._chunk_freqs: dict[int, dict[str, int]] = {}   # chunk_id -> {term: tf}（删除反查）
        self._doc_lengths: dict[int, int] = {}              # chunk_id -> token 数
        self._doc_freq: dict[str, int] = {}                 # term -> 含该词的 chunk 数
        self._chunk_ids: set[int] = set()
        self._total_tokens: int = 0
        self._idf: dict[str, float] = {}
        self._idf_dirty: bool = False
        self._index_built = False

        # Reranker（lazy load）
        self._reranker = None

    # ── 索引管理 ──────────────────────────────
    # Okapi BM25 参数（与 rank_bm25.BM25Okapi 默认值一致，保证打分公式不变）
    BM25_K1 = 1.5
    BM25_B = 0.75
    BM25_EPSILON = 0.25

    def build_bm25_index(self, chunks: list[dict]):
        """从 chunks 列表全量构建 BM25 倒排索引（首次加载 / 全量重建）。"""
        self._reset_index()
        for ch in chunks:
            self._add_chunk(ch["chunk_id"], self._tokenize(ch["content"]))
        self._index_built = True
        self._idf_dirty = True
        logger.info(f"BM25 索引构建完成，共 {len(self._chunk_ids)} 个分片")

    async def ensure_index(self, db):
        """确保 BM25 索引已构建：优先尝试从 PG 快照加载；否则全量从 PG 重建 + 落盘。

        启动期 cold start 时实测加载 ≈25ms，远快于全量重建 ≈1.8s（402 chunks）。
        快照校验失败（schema 不兼容 / 与 chunks 表脱钩）会自动 fallback 到全量重建。
        """
        if self._index_built:
            return
        # 0. 优先尝试 PG 快照加载（Day 9 Task 4）
        from app.services.bm25_persistence import load_snapshot, apply_snapshot, save_snapshot

        snap = await load_snapshot(db)
        if snap is not None:
            apply_snapshot(self, snap)
            return

        # 1. Fallback：全量从 PG 重建 → 立刻落盘，下次启动走快照路径
        chunks = await self._load_chunks_from_db(db)
        self.build_bm25_index(chunks)
        await save_snapshot(self, db)

    async def add_chunks(self, chunks: list[dict], db) -> None:
        """增量新增 chunks（若索引尚未构建，先全量加载现有 chunk，避免残缺索引）。"""
        await self.ensure_index(db)
        changed = False
        for ch in chunks:
            changed |= self._add_chunk(ch["chunk_id"], self._tokenize(ch["content"]))
        self._index_built = True
        if changed:
            self._idf_dirty = True
            # Day 9 Task 4：增量新增后落盘快照
            from app.services.bm25_persistence import save_snapshot
            await save_snapshot(self, db)

    async def remove_chunks(self, chunk_ids: list[int], db) -> None:
        """增量删除 chunks（幂等：不存在的 chunk_id 直接跳过）。"""
        await self.ensure_index(db)
        changed = False
        for cid in chunk_ids:
            changed |= self._remove_chunk(cid)
        if changed:
            self._idf_dirty = True
            # Day 9 Task 4：增量删除后落盘快照
            from app.services.bm25_persistence import save_snapshot
            await save_snapshot(self, db)

    def _reset_index(self) -> None:
        self._postings = {}
        self._chunk_freqs = {}
        self._doc_lengths = {}
        self._doc_freq = {}
        self._chunk_ids = set()
        self._total_tokens = 0
        self._idf = {}
        self._idf_dirty = True
        self._index_built = False

    def _add_chunk(self, chunk_id: int, tokens: list[str]) -> bool:
        """往倒排索引插入一个 chunk；已存在则跳过（幂等），返回是否发生变化。"""
        if chunk_id in self._chunk_ids:
            return False
        freqs: dict[str, int] = {}
        for t in tokens:
            freqs[t] = freqs.get(t, 0) + 1
        self._chunk_freqs[chunk_id] = freqs
        self._doc_lengths[chunk_id] = len(tokens)
        self._total_tokens += len(tokens)
        self._chunk_ids.add(chunk_id)
        for t, tf in freqs.items():
            self._postings.setdefault(t, {})[chunk_id] = tf
            self._doc_freq[t] = self._doc_freq.get(t, 0) + 1
        return True

    def _remove_chunk(self, chunk_id: int) -> bool:
        """从倒排索引删除一个 chunk；不存在则跳过（幂等），返回是否发生变化。"""
        freqs = self._chunk_freqs.pop(chunk_id, None)
        if freqs is None:
            return False
        self._chunk_ids.discard(chunk_id)
        self._total_tokens -= self._doc_lengths.pop(chunk_id, 0)
        for t, tf in freqs.items():
            post = self._postings.get(t)
            if post is not None:
                post.pop(chunk_id, None)
                if not post:
                    self._postings.pop(t, None)
            new_df = self._doc_freq.get(t, 0) - 1
            if new_df <= 0:
                self._doc_freq.pop(t, None)
            else:
                self._doc_freq[t] = new_df
        return True

    def _ensure_idf(self) -> None:
        """从 doc_freq 重算 idf（增量增删后置 dirty，懒计算）。"""
        if not self._idf_dirty:
            return
        self._idf = {}
        n = len(self._chunk_ids)
        if n == 0:
            self._idf_dirty = False
            return

        idf_sum = 0.0
        negative: list[str] = []
        for t, df in self._doc_freq.items():
            idf = math.log(n - df + 0.5) - math.log(df + 0.5)
            self._idf[t] = idf
            idf_sum += idf
            if idf < 0:
                negative.append(t)
        if self._idf:
            eps = self.BM25_EPSILON * (idf_sum / len(self._idf))
            for t in negative:
                self._idf[t] = eps
        self._idf_dirty = False

    def _bm25_score(self, query_tokens: list[str], chunk_id: int) -> float:
        """Okapi BM25 打分（k1=1.5, b=0.75），与 rank_bm25.BM25Okapi 一致。"""
        dl = self._doc_lengths.get(chunk_id, 0)
        n = len(self._chunk_ids)
        if dl == 0 or n == 0:
            return 0.0
        avgdl = self._total_tokens / n
        if avgdl <= 0:
            return 0.0

        score = 0.0
        for t in query_tokens:
            tf = self._postings.get(t, {}).get(chunk_id, 0)
            if tf == 0:
                continue
            idf = self._idf.get(t, 0.0)
            num = idf * tf * (self.BM25_K1 + 1)
            den = tf + self.BM25_K1 * (1 - self.BM25_B + self.BM25_B * dl / avgdl)
            score += num / den
        return score

    async def _load_chunks_from_db(self, db) -> list[dict]:
        """从数据库加载全部 chunk（id + content）用于构建 BM25。"""
        from sqlalchemy import select
        from app.models.chunk import Chunk

        result = await db.execute(select(Chunk.id, Chunk.content))
        rows = result.all()
        return [{"chunk_id": r.id, "content": r.content} for r in rows]

    def _tokenize(self, text: str) -> list[str]:
        """中文分词（jieba 精确模式 + 停用词过滤）；英文/数字/下划线按词切分。

        相比旧版「字符 + 双字滑动窗口」，jieba 切出语义完整的词并过滤停用词，
        可将 BM25 索引词汇表缩减约 34%；代价是字面命中率略降约 3pt，属
        「以少量精度换取索引/内存精简」的取舍，更适合大规模知识库。
        对比实验见 backend/output/tokenizer_compare.md。
        """
        text = text.lower()

        # 英文 / 数字 / 下划线：按连续字母数字串切分（与旧版保持一致）
        tokens = re.findall(r"[a-z0-9_]+", text)

        # 中文部分：去掉英文/数字后交给 jieba 分词，过滤停用词与纯标点
        chinese_part = re.sub(r"[a-z0-9_]+", " ", text)
        for word in jieba.cut(chinese_part):
            word = word.strip()
            if not word or word in CHINESE_STOPWORDS:
                continue
            # 只保留含中文的词，丢弃标点与纯空白
            if re.search(r"[一-鿿]", word):
                tokens.append(word)
        return tokens

    def _tokenize_char_window(self, text: str) -> list[str]:
        """旧版字符滑动窗口分词（保留用于「jieba vs 字符窗口」对比实验）。"""
        text = text.lower()
        english = re.findall(r"[a-z0-9_]+", text)
        chinese_chars = re.findall(r"[一-鿿]", text)
        chinese_bigrams = [
            text[i:i+2] for i in range(len(text)-1)
            if text[i] in chinese_chars and text[i+1] in chinese_chars
        ]
        return english + chinese_bigrams

    # ── 检索方法 ──────────────────────────────

    async def hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        db,  # AsyncSession
        top_k: int | None = None,
        mode: str = "hybrid",
        enhance: str = "auto",
    ) -> list[RetrievalResult]:
        """
        执行检索，返回排序后的结果列表。

        Args:
            query: 用户查询文本
            query_embedding: 查询向量（由 EmbeddingService 预计算）
            db: 数据库会话
            top_k: 返回数量
            mode: 消融实验用检索模式。
                  "hybrid"（默认）= BM25 + 向量 + RRF；
                  "bm25" = 仅 BM25 稀疏检索；
                  "vector" = 仅向量稠密检索。
            enhance: 查询增强开关。
                  "auto"（默认）= 读 config 的 query_rewrite_enabled / hyde_enabled；
                  "none" = 不增强；"rewrite" = 查询改写；"hyde" = HyDE。

        Returns:
            排序后的 RetrievalResult 列表（已回填 content/document_title/metadata）
        """
        k = top_k or self.top_k

        # 查询增强（rewrite / hyde）：在进入单次检索前按开关分派
        use_rewrite, use_hyde = self._resolve_enhance(enhance)
        if use_rewrite:
            return await self._search_with_rewrite(query, query_embedding, db, k, mode)
        if use_hyde:
            hypo_emb = await self._hyde_embedding(query)
            if hypo_emb:
                query_embedding = hypo_emb  # BM25 一路仍用原始 query 文本

        # 候选集大小：启用 Reranker 时先粗排取更多候选（默认 20）再精排
        candidate_k = max(k, self.rerank_candidates) if self.reranker_enabled else k

        # 0. 确保 BM25 索引就绪（首次/失效后从 PG 重建）
        await self.ensure_index(db)

        # 1. BM25 稀疏检索（mode="vector" 时跳过）
        bm25_results = (
            self._bm25_search(query, candidate_k * 2)
            if self._index_built and mode != "vector" else []
        )

        # 2. 向量稠密检索（mode="bm25" 时跳过；pgvector 余弦距离，走 HNSW 索引）
        vector_results = (
            await self._vector_search(query_embedding, candidate_k * 2, db)
            if mode != "bm25" else []
        )

        # 3. 排序：单路模式直接用单路分数，hybrid 走 RRF 融合
        if mode == "bm25":
            ranked = bm25_results[:candidate_k]
        elif mode == "vector":
            ranked = vector_results[:candidate_k]
        else:
            ranked = self._rrf_fuse(bm25_results, vector_results, top_k=candidate_k)

        # 4. 从 DB 回填 chunk 详情（content / document_title / metadata）
        results = await self._hydrate_results(
            ranked,
            db,
            bm25_map=dict(bm25_results),
            vector_map=dict(vector_results),
        )

        # 5. Reranker 精排（对 top-N 候选重排后截断到 k）
        if self.reranker_enabled and len(results) > k:
            results = await self._safe_rerank(query, results, k)

        return results[:k]

    def _resolve_enhance(self, enhance: str) -> tuple[bool, bool]:
        """把 enhance 参数解析为 (use_rewrite, use_hyde)。"""
        if enhance == "none":
            return False, False
        if enhance == "rewrite":
            return True, False
        if enhance == "hyde":
            return False, True
        # "auto"：读配置开关
        return self.query_rewrite_enabled, self.hyde_enabled

    async def _search_with_rewrite(
        self,
        query: str,
        query_embedding: list[float],
        db,
        k: int,
        mode: str,
    ) -> list[RetrievalResult]:
        """查询改写：原始 query + LLM 改写变体分别召回（无精排），RRF 合并候选后统一精排。

        设计：每个变体先做「BM25+向量+RRF」粗召回取候选（candidate_k），合并去重后
        只对合并候选做一次 Reranker 精排——既避免对每个变体重复精排，又让精排在更大的
        合并候选集上工作（两段式召回→精排）。
        """
        from app.services.query_enhance import query_enhancer
        from app.services.embedding import embedding_service

        variants = await query_enhancer.rewrite(query)
        candidate_k = max(k, self.rerank_candidates) if self.reranker_enabled else k

        result_lists: list[list[RetrievalResult]] = []
        saved = self.reranker_enabled
        self.reranker_enabled = False  # 子查询召回不做精排
        try:
            result_lists.append(await self.hybrid_search(
                query, query_embedding, db, top_k=candidate_k, mode=mode, enhance="none"
            ))
            for q in variants:
                emb = await asyncio.to_thread(embedding_service.embed_query, q)
                result_lists.append(await self.hybrid_search(
                    q, emb, db, top_k=candidate_k, mode=mode, enhance="none"
                ))
        finally:
            self.reranker_enabled = saved

        merged = self._rrf_merge_results(result_lists, candidate_k)
        if self.reranker_enabled and len(merged) > k:
            merged = await self._safe_rerank(query, merged, k)
        return merged[:k]

    def _rrf_merge_results(
        self,
        result_lists: list[list[RetrievalResult]],
        top_k: int,
    ) -> list[RetrievalResult]:
        """对多个查询各自的排序结果做 RRF 合并（按排名倒数加和）。"""
        rrf: dict[int, float] = {}
        best: dict[int, RetrievalResult] = {}
        for results in result_lists:
            for rank, r in enumerate(results):
                rrf[r.chunk_id] = rrf.get(r.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
                best.setdefault(r.chunk_id, r)

        n_lists = sum(1 for r in result_lists if r)
        if not rrf or n_lists == 0:
            return []

        ranked_ids = sorted(rrf, key=lambda cid: rrf[cid], reverse=True)[:top_k]
        max_score = n_lists / (RRF_K + 1)
        merged = []
        for cid in ranked_ids:
            r = best[cid]
            r.final_score = round(rrf[cid] / max_score, 4)
            merged.append(r)
        return merged

    async def _hyde_embedding(self, query: str) -> list[float] | None:
        """HyDE：生成假设回答文档并向量化；失败返回 None（回退原始 query 向量）。"""
        from app.services.query_enhance import query_enhancer
        from app.services.embedding import embedding_service

        hypo = await query_enhancer.hyde(query)
        if not hypo:
            return None
        return await asyncio.to_thread(embedding_service.embed_query, hypo)

    def _bm25_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """BM25 检索：只对含查询词的候选 chunk 打分（倒排索引剪枝）。"""
        if not self._index_built:
            return []
        self._ensure_idf()
        tokens = self._tokenize(query)

        candidates: set[int] = set()
        for t in tokens:
            post = self._postings.get(t)
            if post:
                candidates.update(post.keys())

        scored = [(cid, self._bm25_score(tokens, cid)) for cid in candidates]
        scored = [(cid, s) for cid, s in scored if s > 0]
        scored.sort(key=lambda x: (-x[1], x[0]))  # 分数降序，同分按 chunk_id 升序（与旧实现一致）
        return [(cid, float(s)) for cid, s in scored[:top_k]]

    async def _vector_search(
        self,
        query_embedding: list[float],
        top_k: int,
        db,
    ) -> list[tuple[int, float]]:
        """pgvector 余弦相似度检索（ORDER BY <=> 可命中 HNSW vector_cosine_ops）"""
        from sqlalchemy import select
        from app.models.chunk import Chunk

        distance = Chunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(
                Chunk.id,
                (1 - distance).label("similarity"),
            )
            .where(Chunk.embedding.isnot(None))
            .order_by(distance)
            .limit(top_k)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [(row[0], float(row[1])) for row in rows]

    def _rrf_fuse(
        self,
        bm25_results: list[tuple[int, float]],
        vector_results: list[tuple[int, float]],
        top_k: int,
        k: int = RRF_K,
    ) -> list[tuple[int, float]]:
        """
        Reciprocal Rank Fusion：按各路的排名倒数加和。

        返回 [(chunk_id, fused_score)]，分数归一化到 0-1：
        同时出现在两路第一名时 = 1.0。
        """
        rrf: dict[int, float] = {}
        for rank, (chunk_id, _score) in enumerate(bm25_results):
            rrf[chunk_id] = rrf.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
        for rank, (chunk_id, _score) in enumerate(vector_results):
            rrf[chunk_id] = rrf.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)

        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]

        n_rankers = (1 if bm25_results else 0) + (1 if vector_results else 0)
        max_score = n_rankers / (k + 1)
        if max_score > 0:
            return [(cid, round(s / max_score, 4)) for cid, s in ranked]
        return ranked

    async def _hydrate_results(
        self,
        ranked: list[tuple[int, float]],
        db,
        bm25_map: dict[int, float],
        vector_map: dict[int, float],
    ) -> list[RetrievalResult]:
        """根据 chunk_id 列表回填 content / document_title / metadata。"""
        if not ranked:
            return []

        from sqlalchemy import select
        from app.models.chunk import Chunk
        from app.models.document import Document

        ids = [cid for cid, _s in ranked]
        stmt = (
            select(Chunk, Document.title, Document.filename)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id.in_(ids))
        )
        rows = (await db.execute(stmt)).all()
        row_map = {chunk.id: (chunk, title, filename) for chunk, title, filename in rows}

        results = []
        for chunk_id, fused_score in ranked:
            item = row_map.get(chunk_id)
            if item is None:
                continue
            chunk, title, filename = item
            results.append(RetrievalResult(
                chunk_id=chunk_id,
                content=chunk.content,
                document_id=chunk.document_id,
                document_title=title or filename,
                metadata=chunk.metadata_ or {},
                bm25_score=bm25_map.get(chunk_id, 0.0),
                vector_score=vector_map.get(chunk_id, 0.0),
                final_score=fused_score,
            ))

        return results

    # ── Reranker ─────────────────────────────────────────────

    async def _safe_rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        k: int,
    ) -> list[RetrievalResult]:
        """Reranker 调用入口：先按 rerank_top_k 截断，再用 wait_for 包超时，超时按开关降级。

        设计动机：CPU 版 bge-reranker-base 在候选集 30、单条 ~250 字时 P50 ≈ 1.36s；
        偶发长尾会拖到 2-3s，体感等待差。设置硬超时 + 截断 + 降级，让精排失败
        时无缝回落到粗排（RRF 归一化分数），保证 P95 总在 2s 内。

        Args:
            query: 用户查询
            candidates: 粗排候选
            k: 最终返回条数

        Returns:
            精排后结果；若 Reranker 超时降级则返回按 final_score 排序的粗排候选前 k 条。
        """
        if not candidates:
            return candidates

        # 1. 截断送精排的候选数（rerank_top_k），避免长尾拖慢精排本身
        rerank_in = candidates[: max(k, self.rerank_top_k)]

        # 2. 超时硬护栏：超时后按 rerank_fallback_on_timeout 决定降级还是抛错
        try:
            reranked = await asyncio.wait_for(
                self._rerank_results(query, rerank_in),
                timeout=self.rerank_timeout,
            )
            return reranked[:k]
        except asyncio.TimeoutError:
            logger.warning(
                f"Reranker 超时（>{self.rerank_timeout:.2f}s，候选 {len(rerank_in)} 条），"
                f"降级到粗排 top{k}"
            )
            if self.rerank_fallback_on_timeout:
                # 回退：按粗排 final_score 取 top-k（不标注 rerank_score=0，便于排查超时）
                for r in candidates:
                    r.rerank_score = 0.0
                return sorted(candidates, key=lambda x: x.final_score, reverse=True)[:k]
            raise
        except Exception as e:
            logger.error(f"Reranker 异常：{e!r}，降级到粗排 top{k}")
            if self.rerank_fallback_on_timeout:
                for r in candidates:
                    r.rerank_score = 0.0
                return sorted(candidates, key=lambda x: x.final_score, reverse=True)[:k]
            raise

    @staticmethod
    def _sigmoid(x: float) -> float:
        """把 CrossEncoder 原始 logits 归一化到 (0, 1)。"""
        return 1.0 / (1.0 + math.exp(-x))

    async def _rerank_results(
        self,
        query: str,
        candidates: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """BGE-Reranker 精排：对粗排候选重打分并融合。

        注意：本机 sentence-transformers 版本的 CrossEncoder 没有
        compute_score 方法（只有 predict）；且 predict 对单标签模型默认
        已应用 sigmoid，返回值即 (0, 1) 概率，可直接与 RRF 融合分加权，
        无需再归一化。
        """
        if not self._reranker:
            # 模型下载/加载是阻塞操作，丢线程池避免卡住事件循环
            await asyncio.to_thread(self._load_reranker)

        pairs = [[query, c.content] for c in candidates]
        # CrossEncoder 推理是 CPU/GPU 阻塞，丢线程池
        scores = await asyncio.to_thread(self._reranker.predict, pairs)

        for r, s in zip(candidates, scores):
            s = float(s)
            # 防御性截断：确保融合分处于 (0, 1)，避免个别版本返回原始 logits
            if s < 0.0 or s > 1.0:
                s = self._sigmoid(s)
            r.rerank_score = s
            r.final_score = (
                r.final_score * (1 - self.rerank_weight) +
                r.rerank_score * self.rerank_weight
            )

        return sorted(candidates, key=lambda x: x.final_score, reverse=True)

    def _load_reranker(self):
        """Lazy load Reranker 模型"""
        from sentence_transformers import CrossEncoder
        from app.config import settings

        logger.info("正在加载 Reranker 模型...")
        self._reranker = CrossEncoder(settings.reranker_model, device=settings.embedding_device)
        logger.info("Reranker 模型加载完成")


# 全局单例
retriever = HybridRetriever()
