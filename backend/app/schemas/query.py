"""搜索/问答相关 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional


class CitationItem(BaseModel):
    """引用来源"""
    chunk_id: int
    document_title: str
    section: str = ""
    content_snippet: str  # 引用的原文片段（前100字）


class ChatMessage(BaseModel):
    """对话消息（SSE 流式 & 多轮历史用）"""
    role: str  # user / assistant / system
    content: str
    citations: list[CitationItem] = []
    confidence_score: float = 0.0


class SearchRequest(BaseModel):
    """搜索请求"""
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数量")
    use_agentic: bool = Field(default=True, description="是否使用多步 Agentic 检索")
    stream: bool = Field(default=False, description="是否 SSE 流式返回")
    history: list[ChatMessage] | None = Field(
        default=None, description="多轮对话历史（最近的 user/assistant 消息，用于指代消解）"
    )
    thread_id: Optional[str] = Field(
        default=None, description="会话 ID（非空时启用 checkpointer 跨请求恢复历史）"
    )


class SearchResponse(BaseModel):
    """搜索/问答响应"""
    answer: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    citations: list[CitationItem] = []
    retrieval_details: dict = {}  # 检索过程详情（用于调试）
    latency_ms: int = 0
    query_log_id: Optional[int] = None  # 本次查询日志 ID（用于提交用户反馈）


class QueryFeedbackRequest(BaseModel):
    """用户反馈请求"""
    query_log_id: int
    feedback: str = Field(..., pattern="^(helpful|not_helpful)$")
