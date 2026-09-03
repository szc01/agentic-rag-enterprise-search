"""文档分片 ORM 模型（含 pgvector 向量字段）"""
from sqlalchemy import String, Text, DateTime, Integer, Float, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.database import Base
from app.config import settings


class Chunk(Base):
    """文档分片（知识库最小检索单元）"""
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="在文档中的序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="分片文本内容")
    # pgvector 字段：BGE-large-zh-v1.5 维度 1024
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimension), nullable=True, comment="向量嵌入"
    )
    metadata_: Mapped[dict] = mapped_column(
        JSON, default=dict, name="metadata", comment="元数据: {page_num, section, table_flag}"
    )
    token_count: Mapped[int] = mapped_column(Integer, default=0, comment="估算 token 数")

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    # 关联
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<Chunk(id={self.id}, doc_id={self.document_id}, idx={self.chunk_index}, tokens={self.token_count})>"
