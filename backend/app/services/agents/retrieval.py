"""Retrieval Agent：执行单次子查询的混合检索"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.services.embedding import embedding_service
from app.services.retriever import HybridRetriever, RetrievalResult, retriever
from app.services.agents.types import GraphState, SubQuery

logger = logging.getLogger(__name__)


class RetrievalAgent:
    """
    检索执行 Agent。

    输入：当前子查询（来自 State.current_query_index 对应的 plan 项）
    动作：调用 HybridRetriever.hybrid_search() 执行检索
    输出：追加到 State.retrieved_chunks

    注意：这个 Agent 不做判断，只负责"拿到结果"。
    """

    def __init__(self):
        self.retriever: Optional[HybridRetriever] = retriever

    def set_retriever(self, retriever: HybridRetriever):
        """注入 Retriever 实例（由外部初始化后传入，测试用）"""
        self.retriever = retriever

    async def retrieve(
        self,
        state: GraphState,
        db,  # AsyncSession
    ) -> dict:
        """
        执行当前子查询的检索，将结果追加到 state。

        Args:
            state: 当前图状态（读取 plan / current_query_index）
            db: 数据库会话

        Returns:
            需要更新的 state 字段字典
        """
        plan: list[SubQuery] = state.get("plan", [])
        idx = state.get("current_query_index", 0)

        if idx >= len(plan):
            logger.warning(f"Retrieval: 子查询索引 {idx} 超出范围（共 {len(plan)} 个）")
            return {}

        sub_query = plan[idx]
        logger.info(f"Retrieval [{idx+1}/{len(plan)}]: {sub_query.query}")

        # 1. 向量化查询（模型推理是 CPU 阻塞，丢线程池）
        query_embedding = await asyncio.to_thread(
            embedding_service.embed_query, sub_query.query
        )

        # 2. 混合检索
        results: list[RetrievalResult] = []
        if self.retriever:
            results = await self.retriever.hybrid_search(
                query=sub_query.query,
                query_embedding=query_embedding,
                db=db,
                top_k=5,
            )

        # 3. 转为 dict 追加到 state
        chunk_dicts = [
            {
                "chunk_id": r.chunk_id,
                "content": r.content,
                "document_id": r.document_id,
                "document_title": r.document_title,
                "metadata": r.metadata,
                "scores": {
                    "bm25": round(r.bm25_score, 4),
                    "vector": round(r.vector_score, 4),
                    "rerank": round(r.rerank_score, 4),
                    "final": round(r.final_score, 4),
                },
                "sub_query_index": idx,
                "sub_query": sub_query.query,
            }
            for r in results
        ]

        existing = state.get("retrieved_chunks", [])
        updated_chunks = existing + chunk_dicts

        logger.info(f"  → 检索到 {len(chunk_dicts)} 条片段（累计 {len(updated_chunks)} 条）")

        return {
            "retrieved_chunks": updated_chunks,
            "current_query_index": idx + 1,  # 推进到下一个子查询
        }


# 全局单例
retrieval_agent = RetrievalAgent()
