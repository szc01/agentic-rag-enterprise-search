"""查询侧增强：查询改写（rewrite）与 HyDE（假设文档向量）

Day 8 增量（对应报告 8.3 第一条展望）：
  - rewrite：用 LLM 把原始 query 改写/扩展为若干语义变体，分别检索后做 RRF 合并，
    提升「同义改写 / 多主题干扰 / 反向否定」等复杂查询的召回。
  - HyDE：用 LLM 生成一段「假设回答文档」，用该文档的向量替代原始 query 向量做
    向量检索（BM25 一路仍用原始 query 文本），缓解 query-文档语义鸿沟。

开关：config.py 的 query_rewrite_enabled / hyde_enabled（默认关，不影响既有行为）。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """你是检索查询改写专家。把用户查询改写/扩展为 2-3 个语义等价或更完整的查询变体，用于提升检索召回。

规则：
1. 变体可做同义改写、上下文补全或歧义消解。
2. 每个变体应是能在知识库中独立检索的完整问题。
3. 只输出 JSON 数组，不要其他文字。"""

REWRITE_USER_TEMPLATE = """原始查询：{query}

请输出 JSON 数组，包含 2-3 个改写后的查询变体，例如：
["变体1", "变体2"]

只输出 JSON："""

HYDE_SYSTEM_PROMPT = """你是企业知识库检索助手。给定用户问题，写一段「假设回答文档」：
一段与问题高度相关的陈述性文字，模拟知识库中可能包含答案的文档片段。即使不确定答案，
也要写出风格、术语与问题匹配的连贯段落。只输出该段落，不要标题、不要解释。"""

HYDE_USER_TEMPLATE = """问题：{query}

请写一段 100-200 字的假设回答文档："""


def _extract_json_array(raw: str) -> Optional[list[str]]:
    """从 LLM 输出里稳健地提取 JSON 字符串数组（容忍 markdown 代码块）。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    # 截取第一个 [ ... ] 片段
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return [str(x).strip() for x in data if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        return None


class QueryEnhancer:
    """查询改写 + HyDE 的统一入口。"""

    def __init__(self, llm: Optional[ChatOpenAI] = None):
        self.llm = llm or ChatOpenAI(
            model=settings.llm_model,
            temperature=0.0,
            max_tokens=512,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
        )

    async def rewrite(self, query: str) -> list[str]:
        """把 query 改写为 2-3 个变体（不含原始 query）。

        解析失败 / LLM 不可用时返回空列表（调用方回退为只用原始 query）。
        """
        try:
            resp = await self.llm.ainvoke([
                SystemMessage(content=REWRITE_SYSTEM_PROMPT),
                HumanMessage(content=REWRITE_USER_TEMPLATE.format(query=query)),
            ])
            variants = _extract_json_array(resp.content or "")
            if variants:
                # 去重并保留原始 query 之外的变体，最多 3 个
                seen = {query}
                out = []
                for v in variants:
                    if v not in seen:
                        seen.add(v)
                        out.append(v)
                    if len(out) >= 3:
                        break
                return out
        except Exception as e:
            logger.warning(f"查询改写失败，回退原始 query: {e}")
        return []

    async def hyde(self, query: str) -> str:
        """生成假设回答文档（HyDE）；失败返回空串。"""
        try:
            resp = await self.llm.ainvoke([
                SystemMessage(content=HYDE_SYSTEM_PROMPT),
                HumanMessage(content=HYDE_USER_TEMPLATE.format(query=query)),
            ])
            return (resp.content or "").strip()
        except Exception as e:
            logger.warning(f"HyDE 生成失败: {e}")
            return ""


# 全局单例
query_enhancer = QueryEnhancer()
