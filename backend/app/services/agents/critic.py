"""Critic Agent：验证检索结果的信息充分性，决定是否补充检索"""
from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.services.agents.types import GraphState, CriticVerdict

logger = logging.getLogger(__name__)

# ── Prompt 模板 ────────────────────────────────
CRITIC_SYSTEM_PROMPT = """你是一个严格的信息完整性审查员。你的任务是判断当前检索到的信息是否足以回答用户的原始问题。

判断标准：
1. 事实类问题：关键事实（定义、数据、时间、人物）是否都有？
2. 对比类问题：对比各方是否都覆盖？对比维度是否完整？
3. 分析类问题：原因、影响、趋势等角度是否都有材料支撑？
4. 如果缺少某个重要方面，必须指出具体缺什么。

输出格式要求：严格的 JSON。"""

CRITIC_USER_TEMPLATE = """用户原始问题：
{question}

已检索到的信息摘要（共 {chunk_count} 条片段）：
{chunks_summary}

请判断这些信息是否足够回答用户问题。

以 JSON 格式输出：
{{
    "sufficient": true/false,
    "confidence": 0.0-1.0,
    "missing_aspects": ["缺失的方面1", "缺失的方面2"],
    "suggested_queries": ["建议补充检索的问题1", "建议补充检索的问题2"],
    "reasoning": "判断理由"
}}

只输出 JSON，不要其他文字："""


class CriticAgent:
    """
    自我验证 Agent（Critic）。
    
    输入：原始问题 + 已检索到的所有片段
    输出：CriticVerdict（是否充分 / 缺什么 / 建议补查什么）
    
    这是 Agentic RAG 的核心差异化点：
      - 单轮 RAG 检索一次就生成答案
      - Agentic RAG 通过 Critic 判断是否需要"再查一轮"
    
    安全机制：
      - max_iterations 上限防止死循环
      - confidence 阈值控制回退策略
    """

    def __init__(self, confidence_threshold: float = 0.7):
        self.llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=0.0,  # 审查要稳定、一致
            max_tokens=1024,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
        )
        self.confidence_threshold = confidence_threshold

    async def critique(self, state: GraphState) -> dict:
        """
        审视当前检索结果是否充分。
        
        Args:
            state: 当前图状态
            
        Returns:
            更新 critic_verdict 字段
        """
        question = state.get("question", "")
        chunks = state.get("retrieved_chunks", [])
        iterations = state.get("iterations", 0)

        # 构建检索结果摘要（避免把全部内容塞进 prompt）
        chunks_summary = self._summarize_chunks(chunks)

        messages = [
            SystemMessage(content=CRITIC_SYSTEM_PROMPT),
            HumanMessage(content=CRITIC_USER_TEMPLATE.format(
                question=question,
                chunk_count=len(chunks),
                chunks_summary=chunks_summary,
            )),
        ]

        response = await self.llm.ainvoke(messages)
        raw_text = response.content.strip()

        # 解析 JSON
        verdict = self._parse_verdict(raw_text)
        
        # 安全兜底：达到最大迭代次数时强制标记为 sufficient
        max_iterations = state.get("max_iterations", 3)
        if iterations >= max_iterations:
            logger.warning(f"Critic: 达到最大迭代次数 {max_iterations}，强制终止")
            verdict.sufficient = True
            verdict.reasoning += f" [强制终止：已达 {max_iterations} 轮]"

        logger.info(
            f"Critic: sufficient={verdict.sufficient}, "
            f"conf={verdict.confidence:.2f}, "
            f"missing={verdict.missing_aspects}"
        )

        return {"critic_verdict": verdict}

    def _summarize_chunks(self, chunks: list[dict]) -> str:
        """将检索结果压缩为摘要（控制 token 消耗）"""
        if not chunks:
            return "（暂无检索结果）"

        summaries = []
        for i, ch in enumerate(chunks[:15]):  # 最多展示前 15 条
            content = ch.get("content", "")[:200]
            source = ch.get("document_title", "未知文档")
            score = ch.get("scores", {}).get("final", 0)
            sub_q = ch.get("sub_query", "")
            summaries.append(
                f"[{i+1}] 来源:{source} | 相关度:{score:.2f} | 子查询:'{sub_q}'\n"
                f"    内容:{content}..."
            )

        if len(chunks) > 15:
            summaries.append(f"\n... 还有 {len(chunks) - 15} 条未展示")

        return "\n\n".join(summaries)

    def _parse_verdict(self, raw_text: str) -> CriticVerdict:
        """解析 LLM 输出的 CriticVerdict JSON"""
        try:
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            
            data = json.loads(raw_text)
            return CriticVerdict(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Critic JSON 解析失败: {e}，默认为不充分")
            return CriticVerdict(
                sufficient=False,
                confidence=0.3,
                missing_aspects=["解析失败，无法确认"],
                reasoning=f"JSON 解析异常: {e}",
            )


# 全局单例
critic_agent = CriticAgent()
