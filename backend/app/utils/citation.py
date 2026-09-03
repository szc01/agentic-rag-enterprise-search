"""引用格式化工具"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FormattedCitation:
    """格式化后的引用"""
    index: int  # 引用编号 [1], [2] ...
    inline_mark: str  # 内联标记，如 "[1]"
    display_text: str  # 展示文本，如 "《企业制度手册》第3章"
    source_snippet: str  # 原文片段


def format_citations(citations: list[dict]) -> list[FormattedCitation]:
    """
    将原始引用列表格式化为可展示的引用对象。
    
    Args:
        citations: [{"chunk_id", "document_title", "section", "content_snippet"}, ...]
        
    Returns:
        格式化后的引用列表
    """
    formatted = []
    for i, cit in enumerate(citations, start=1):
        title = cit.get("document_title", "未知来源")
        section = cit.get("section", "")
        snippet = (cit.get("content_snippet") or "")[:150]

        display = f"《{title}》"
        if section:
            display += f" · {section}"

        formatted.append(FormattedCitation(
            index=i,
            inline_mark=f"[{i}]",
            display_text=display,
            source_snippet=snippet,
        ))

    return formatted


def insert_citation_marks(answer: str, citations: list[dict]) -> str:
    """
    确保答案文本中的引用标记格式统一。
    
    如果 LLM 已经输出了 [n] 标记则保留，
    否则在答案末尾追加引用列表。
    
    Args:
        answer: 原始答案文本
        citations: 引用列表
        
    Returns:
        处理后的答案文本
    """
    import re

    # 检查是否已有 [n] 标记
    has_inline_citations = bool(re.search(r"\[\d+\]", answer))

    if has_inline_citations and citations:
        # 已有内联引用，追加引用说明
        ref_section = "\n\n---\n**参考文献：**\n"
        for i, cit in enumerate(citations, 1):
            title = cit.get("document_title", "未知")
            section = cit.get("section", "")
            line = f"[{i}] {title}"
            if section:
                line += f"（{section}）"
            ref_section += f"{line}\n"
        return answer + ref_section
    elif citations:
        # 无内联引用，在末尾追加
        ref_section = "\n\n---\n**参考来源：**\n"
        for i, cit in enumerate(citations, 1):
            title = cit.get("document_title", "未知")
            snippet = (cit.get("content_snippet") or "")[:100]
            ref_section += f"[{i}] {title}: \"{snippet}...\"\n"
        return answer + ref_section

    return answer
