"""Planner Agent：将复杂问题分解为子查询列表"""
from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.services.agents.types import SubQuery, GraphState

logger = logging.getLogger(__name__)

# ── Prompt 模板（独立抽出，方便调优）───────────────
PLANNER_SYSTEM_PROMPT = """你是一个专业的问题分解专家。你的任务是将用户的复杂问题拆解为若干个可独立检索的子查询。

规则：
1. 简单事实性问题（单个实体/概念）直接返回 1 个子查询，原样返回即可。
2. 对比分析类问题拆为"各方分别是什么" + "对比维度"。
3. 综合推理类问题按"背景→现状→原因→影响→趋势"拆分。
4. 每个子查询应该是能在知识库中找到对应文档片段的独立问题。
5. 子查询数量控制在 2-5 个之间，不要过度拆分。
6. 必须输出合法 JSON 格式。"""

PLANNER_USER_TEMPLATE = """请将以下用户问题分解为子查询列表：

{history_context}用户问题：{question}

请以 JSON 数组格式输出，每个元素包含：
- query: str（子查询文本）
- rationale: str（为什么要查这个子问题）

示例输出：
[{{"query": "什么是 RAG？", "rationale": "需要先了解基本定义"}}, {{"query": "RAG 的主要技术路线有哪些？", "rationale": "了解技术分类"}}]

只输出 JSON，不要其他文字："""


class PlannerAgent:
    """
    问题规划 Agent。
    
    输入：用户原始问题
    输出：SubQuery 列表（2-5 个可独立检索的子问题）
    
    使用 LLM 做语义级分解（不是简单的关键词提取），
    确保每个子查询都能在知识库中找到对应的文档片段。
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=0.0,  # 分解要稳定、确定
            max_tokens=1024,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
        )

    async def plan(
        self,
        question: str,
        history: Optional[list[dict]] = None,
    ) -> list[SubQuery]:
        """
        将用户问题分解为子查询列表。

        Args:
            question: 用户原始问题
            history: 多轮对话历史 [{"role", "content"}]，用于指代消解

        Returns:
            SubQuery 列表
        """
        from app.utils.history import format_history

        history_context = ""
        history_text = format_history(history)
        if history_text:
            history_context = (
                "历史对话（用户当前问题可能用「它 / 这个 / 第二个方案」等指代历史内容，"
                "请结合历史把子查询补全为可独立检索的完整问题）：\n"
                f"{history_text}\n\n"
            )

        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=PLANNER_USER_TEMPLATE.format(
                question=question,
                history_context=history_context,
            )),
        ]

        response = await self.llm.ainvoke(messages)
        raw_text = response.content.strip()

        # 解析 JSON（处理可能的 markdown 代码块包裹）
        try:
            # 去掉可能的外层 ```json ... ```
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            
            data = json.loads(raw_text)
            sub_queries = [SubQuery(**item) for item in data]
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Planner JSON 解析失败: {e}，回退为单查询")
            sub_queries = [SubQuery(query=question, rationale="原始问题（解析失败回退）")]

        if not sub_queries:
            sub_queries = [SubQuery(query=question, rationale="空结果回退")]

        logger.info(f"Planner 将问题分解为 {len(sub_queries)} 个子查询")
        for sq in sub_queries:
            logger.info(f"  - [{sq.rationale}] {sq.query}")

        return sub_queries


# 全局单例
planner_agent = PlannerAgent()
