"""文档 ORM 模型"""
from sqlalchemy import String, Text, DateTime, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.database import Base


class Document(Base):
    """上传的原始文档（PDF / Word / Markdown 等）"""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, comment="存储路径")
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="文件类型: pdf/docx/md/txt")
    file_size: Mapped[int] = mapped_column(Integer, default=0, comment="文件大小(bytes)")
    title: Mapped[str] = mapped_column(String(500), default="", comment="文档标题（从内容提取）")
    summary: Mapped[str] = mapped_column(Text, default="", comment="文档摘要")
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, comment="分片总数")
    status: Mapped[str] = mapped_column(
        String(20),
        default="uploaded",
        comment="状态: uploaded/parsed/embedded/ready/error",
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联
    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"
