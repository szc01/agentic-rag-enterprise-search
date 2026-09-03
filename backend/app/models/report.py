"""调研报告 ORM 模型"""
from sqlalchemy import String, Text, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Report(Base):
    """自动调研报告（后台生成，前端轮询 status 直到 ready）"""
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False, comment="调研主题")
    status: Mapped[str] = mapped_column(
        String(20),
        default="generating",
        comment="状态: generating/ready/failed",
    )
    depth: Mapped[int] = mapped_column(Integer, default=2, comment="检索深度（迭代轮数）")
    content: Mapped[str] = mapped_column(Text, default="", comment="Markdown 报告全文")
    citations: Mapped[dict] = mapped_column(
        JSON, default=list, comment="引用来源列表"
    )
    stats: Mapped[dict] = mapped_column(
        JSON, default=dict,
        comment="统计: {sub_queries, chunks_used, iterations, confidence}",
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[DateTime | None] = mapped_column(
        DateTime, nullable=True, comment="生成完成时间"
    )

    def __repr__(self):
        return f"<Report(id={self.id}, topic='{self.topic[:40]}...', status='{self.status}')>"
