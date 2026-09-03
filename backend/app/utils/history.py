"""多轮对话历史格式化工具"""
from __future__ import annotations

from typing import Optional


def normalize_history(history) -> list[dict]:
    """把 Pydantic ChatMessage / dict / 任意带 role+content 的对象统一为 [{"role", "content"}]。

    兼容 API 层传下来的 ChatMessage 列表，也兼容图状态里的纯 dict 列表。
    """
    if not history:
        return []

    normalized = []
    for item in history:
        if isinstance(item, dict):
            role = item.get("role", "user")
            content = item.get("content", "")
        else:
            role = getattr(item, "role", "user")
            content = getattr(item, "content", "")
        if role and content:
            normalized.append({"role": role, "content": content})
    return normalized


def format_history(history, max_turns: int = 4) -> str:
    """把历史对话格式化为 prompt 上下文片段（仅取最近 max_turns 轮）。

    Returns:
        空字符串（无历史）或形如「用户: xxx\n助手: yyy」的文本。
    """
    turns = normalize_history(history)
    if not turns:
        return ""

    # 一轮 = 用户提问 + 助手回答，保留最近 max_turns 轮（2 * max_turns 条消息）
    recent = turns[-(max_turns * 2):]

    lines = []
    for item in recent:
        role = item["role"]
        label = {"user": "用户", "assistant": "助手", "system": "系统"}.get(role, role)
        lines.append(f"{label}: {item['content']}")
    return "\n".join(lines)
