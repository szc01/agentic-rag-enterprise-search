"""文档入库服务：解析 → 分片 → 向量化 → 写入 pgvector

Day 1 全链路核心：把上传的原始文档变成 chunks 表里可检索的向量分片。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.chunk import Chunk
from app.services.parser import parser
from app.services.chunker import chunker
from app.services.embedding import embedding_service
from app.services.retriever import retriever

logger = logging.getLogger(__name__)


class IngestionService:
    """文档入库管线。

    流程：解析文件 → 标题/段落/长度多策略分片 → BGE 批量向量化 → 写入 chunks 表。
    解析与向量化都是 CPU/IO 阻塞操作，通过 asyncio.to_thread 放进线程池，
    避免阻塞 FastAPI 事件循环。
    """

    def __init__(self):
        self.parser = parser
        self.chunker = chunker
        self.embedding = embedding_service

    async def ingest_document(self, db: AsyncSession, document_id: int) -> Document:
        """对一个已入库的 Document 记录执行完整入库管线。

        Args:
            db: 异步数据库会话
            document_id: documents 表主键

        Returns:
            更新后的 Document（total_chunks / status 已刷新）

        Raises:
            Exception: 解析/向量化失败时向上抛出（Document.status 会被置为 error）
        """
        doc = await db.get(Document, document_id)
        if doc is None:
            raise ValueError(f"文档 {document_id} 不存在")

        # 标记开始处理
        doc.status = "parsing"
        await db.commit()

        try:
            # 1. 解析 + 分片（同步阻塞，丢线程池）
            blocks, chunks = await asyncio.to_thread(
                self._parse_and_chunk, doc.file_path, doc.id
            )

            if not chunks:
                logger.warning(f"文档 {doc.id} 未解析出任何可分片内容")
                doc.status = "ready"
                doc.total_chunks = 0
                doc.title = doc.title or Path(doc.filename).stem
                await db.commit()
                return doc

            # 2. 向量化（BGE lazy load，首次调用会下载模型）
            texts = [c.content for c in chunks]
            embeddings = await asyncio.to_thread(self.embedding.embed_texts, texts)

            # 3. 写入 chunks 表（含 pgvector 向量）
            orm_chunks = []
            for chunk, vec in zip(chunks, embeddings):
                orm = Chunk(
                    document_id=doc.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=vec,
                    metadata_=chunk.metadata,
                    token_count=chunk.token_count,
                )
                db.add(orm)
                orm_chunks.append(orm)

            # 4. 回写文档状态
            doc.total_chunks = len(chunks)
            doc.title = doc.title or Path(doc.filename).stem
            doc.status = "ready"
            await db.commit()

            # 5. 增量更新 BM25 索引（首次会先全量加载现有 chunks）
            await retriever.add_chunks(
                [{"chunk_id": c.id, "content": c.content} for c in orm_chunks],
                db,
            )
            logger.info(f"文档 {doc.id} 入库完成，共 {len(chunks)} 个分片")
            return doc

        except Exception:
            # 记录失败状态后继续抛出，由调用方决定如何响应
            logger.exception(f"文档 {doc.id} 入库失败")
            try:
                doc.status = "error"
                await db.commit()
            except Exception:
                logger.exception("回写 error 状态失败")
            raise

    def _parse_and_chunk(self, file_path: str, document_id: int):
        """同步执行：解析文件 + 分片。返回 (blocks, chunks)。"""
        blocks = [
            {"content": b.content, "metadata": b.metadata}
            for b in self.parser.parse(file_path)
        ]
        chunks = self.chunker.chunk_blocks(blocks, document_id=document_id)
        return blocks, chunks


# 全局单例
ingestion_service = IngestionService()
