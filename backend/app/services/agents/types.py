"""Agent 间共享的类型定义"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from typing_extensions import TypedDict


@dataclass
class SubQuery:
    """Planner 分解出的子查询"""
    query: str
    rationale: str = ""


@dataclass
class CriticVerdict:
    """Critic Agent 的判断结果"""
    sufficient: bool = False
    confidence: float = 0.0
    missing_aspects: list[str] = field(default_factory=list)
    suggested_queries: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class Citation:
    """引用来源"""
    chunk_id: int
    document_title: str
    section: str = ""
    content_snippet: str = ""


# ── LangGraph State 定义 ────────────────────────

class GraphState(TypedDict):
    """
    多步检索 Agentic 图的全局状态。
    
    每个 Node 读取/写入 State 的不同字段，
    通过条件边控制流转方向。
    """
    # === 输入 ===
    question: str                          # 用户原始问题
    history: Optional[list[dict]]          # 多轮对话历史 [{"role", "content"}]，用于指代消解

    # === Planner 输出 ===
    plan: list[SubQuery]                  # 子查询列表

    # === 执行状态 ===
    current_query_index: int               # 当前执行到第几个子查询（从 0 开始）
    retrieved_chunks: list[dict]           # 已检索到的所有片段 [{chunk_id, content, ...}]

    # === Critic 输出 ===
    critic_verdict: Optional[CriticVerdict]

    # === Synthesizer 输出 ===
    answer: str                           # 最终答案
    citations: list[Citation]             # 引用来源列表
    confidence_score: float               # 答案置信度 (0-1)

    # === 控制字段 ===
    iterations: int                       # 迭代计数（防死循环，上限 3-5）
    max_iterations: int                   # 迭代上限（报告 depth 控制，问答默认 3）
    report_mode: bool                     # True 时 Synthesizer 走报告模式
