"""查询日志 ORM 模型（用于评测与运营分析）"""
from sqlalchemy import String, Text, DateTime, Integer, Float, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class QueryLog(Base):
    """用户查询记录（含检索过程与结果质量）"""
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False, comment="用户原始问题")
    answer: Mapped[str] = mapped_column(Text, default="", comment="系统生成的答案")
    citations: Mapped[dict] = mapped_column(
        JSON, default=list, comment="引用来源列表"
    )
    confidence_score: Mapped[float] = mapped_column(
        Float, default=0.0, comment="答案置信度 (0-1)"
    )
    # 检索元数据
    retrieval_details: Mapped[dict] = mapped_column(
        JSON, default=dict,
        comment="检索详情: {sub_queries, chunks_per_query, iterations, agent_trace}"
    )
    # 性能指标
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, comment="端到端延迟(ms)")
    llm_tokens_used: Mapped[int] = mapped_column(Integer, default=0, comment="LLM 总 token 消耗")
    # 执行路径与结果
    use_agentic: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否走 Agentic 多步检索"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="success", comment="success/error"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    # 用户反馈
    user_feedback: Mapped[str] = mapped_column(
        String(20), default="", comment="用户反馈: helpful/not_helpful/empty"
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<QueryLog(id={self.id}, q='{self.question[:50]}...', conf={self.confidence_score})>"
