"""Synthesizer Agent：基于检索结果生成带引用的最终答案"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.services.agents.types import GraphState, Citation, CriticVerdict

logger = logging.getLogger(__name__)

# ── Prompt 模板 ────────────────────────────────
SYNTHESIZER_SYSTEM_PROMPT = """你是一个专业的知识问答助手。你的任务是基于检索到的文档片段，生成准确、有引用来源的回答。

核心要求：
1. **必须基于检索到的材料回答**，不要编造信息。如果材料不足以回答，明确说明。
2. **每个关键论点必须标注引用**，格式为 [doc_title: section]。
3. 回答结构清晰：先给结论，再展开细节。
4. 如果不同材料有矛盾，指出矛盾并给出各方观点。
5. 估算答案的可信度（0-1），并在末尾输出置信度评分。

输出格式：
- 先输出正文（带引用标记）
- 然后输出 JSON 格式的元数据（置信度 + 引用列表）"""

SYNTHESIZER_USER_TEMPLATE = """用户问题：{question}

{history_context}检索到的相关资料（共 {chunk_count} 条）：
{chunks_context}

请基于以上资料生成完整、准确的回答。

要求：
1. 每个事实性陈述用 [编号] 标注引用，如"根据研究[1]，RAG技术..."
2. 在文末以 JSON 格式输出元数据：
```json
{{
    "confidence": 0.0-1.0,
    "citations": [
        {{"id": 1, "document_title": "...", "section": "...", "snippet": "引用原文片段（前100字）"}}
    ]
}}
```

回答："""

# ── 报告模式 Prompt ─────────────────────────────
REPORT_SYSTEM_PROMPT = """你是一名资深行业分析师。基于检索到的资料，撰写一份结构化的深度调研报告。

核心要求：
1. **只依据检索到的材料**，不要编造信息；材料不足时明确说明局限。
2. 报告必须包含以下二级标题章节，且顺序固定：
   - ## 背景
   - ## 现状
   - ## 技术方案
   - ## 案例
   - ## 趋势
3. 每个事实性陈述用 [编号] 标注引用，如"研究[1]指出……"。
4. 文末必须附「## 参考文献」列表，逐条列出 [编号]、来源文档与章节。
5. 输出完整 Markdown，正文充实、结构化，避免只罗列要点。"""

REPORT_USER_TEMPLATE = """调研主题：{topic}

检索到的相关资料（共 {chunk_count} 条）：
{chunks_context}

请基于以上资料撰写结构化调研报告，严格遵守章节结构与引用标注要求。"""

# ── 流式问答 Prompt（不要求 JSON 元数据，便于逐 token 直出）────
SYNTHESIZER_STREAM_SYSTEM_PROMPT = """你是一个专业的知识问答助手。基于检索到的资料，直接、准确地回答用户问题。

要求：
1. **只依据检索到的材料**，不要编造信息；材料不足时明确说明。
2. 每个事实性陈述用 [编号] 标注引用，如"根据研究[1]，……"。
3. 结构清晰：先给结论，再展开细节。
4. 直接输出正文即可——不要输出 JSON、不要输出置信度评分、不要输出代码块。"""

SYNTHESIZER_STREAM_USER_TEMPLATE = """用户问题：{question}

{history_context}检索到的相关资料（共 {chunk_count} 条）：
{chunks_context}

请基于以上资料直接回答，并用 [编号] 标注引用。"""


class SynthesizerAgent:
    """
    答案综合 Agent。
    
    输入：原始问题 + 所有检索到的片段 + Critic 判定
    输出：带引用的最终答案 + 置信度评分 + 引用列表
    
    这是整个管道的出口，质量直接影响用户体验。
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=0.2,  # 综合时允许少量创造性但要可控
            max_tokens=4096,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
        )

    async def synthesize(self, state: GraphState) -> dict:
        """
        基于检索结果生成最终答案。
        
        Args:
            state: 当前图状态
            
        Returns:
            更新 answer / citations / confidence_score 字段
        """
        question = state.get("question", "")
        chunks = state.get("retrieved_chunks", [])
        history = state.get("history", [])
        critic_verdict: Optional[CriticVerdict] = state.get("critic_verdict")

        # 构建上下文（包含完整的检索内容）
        context = self._build_context(chunks)

        # 如果 Critic 标记了不充分，在 prompt 中提醒
        critic_note = ""
        if critic_verdict and not critic_verdict.sufficient:
            critic_note = (
                f"\n\n⚠️ 注意：审查员认为当前信息可能不够充分"
                f"(缺失方面: {', '.join(critic_verdict.missing_aspects) or '未指定'})。"
                f"请在已有材料范围内尽量回答，并说明局限性。"
            )

        messages = [
            SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
            HumanMessage(content=SYNTHESIZER_USER_TEMPLATE.format(
                question=question,
                history_context=self._format_history_context(history),
                chunk_count=len(chunks),
                chunks_context=context + critic_note,
            )),
        ]

        response = await self.llm.ainvoke(messages)
        raw_answer = response.content.strip()

        # 解析答案和引用元数据
        answer, citations, confidence = self._parse_response(raw_answer, chunks)

        logger.info(
            f"Synthesizer: 答案生成完成, "
            f"conf={confidence:.2f}, citations={len(citations)}"
        )

        return {
            "answer": answer,
            "citations": citations,
            "confidence_score": confidence,
        }

    async def synthesize_report(self, state: GraphState) -> dict:
        """
        报告模式：基于检索结果撰写结构化调研报告。

        与问答模式的区别：
          - 输出长文 Markdown，章节固定为「背景/现状/技术方案/案例/趋势」
          - 引用用 [n] 内联标注，文末附参考文献列表
          - 置信度优先取 Critic 判定（否则用 LLM 尾部 JSON，再否则默认值）

        Returns:
            更新 answer（报告全文）/ citations / confidence_score 字段
        """
        topic = state.get("question", "")
        chunks = state.get("retrieved_chunks", [])
        critic_verdict: Optional[CriticVerdict] = state.get("critic_verdict")

        context = self._build_context(chunks)

        critic_note = ""
        if critic_verdict and not critic_verdict.sufficient:
            critic_note = (
                f"\n\n⚠️ 注意：审查员认为当前信息可能不够充分"
                f"(缺失方面: {', '.join(critic_verdict.missing_aspects) or '未指定'})。"
                f"请在已有材料范围内撰写，并说明局限性。"
            )

        messages = [
            SystemMessage(content=REPORT_SYSTEM_PROMPT),
            HumanMessage(content=REPORT_USER_TEMPLATE.format(
                topic=topic,
                chunk_count=len(chunks),
                chunks_context=context + critic_note,
            )),
        ]

        response = await self.llm.ainvoke(messages)
        raw_report = response.content.strip()

        # 从 [n] 内联标记提取引用（与 _build_context 的编号一致）
        citations = self._extract_inline_citations(raw_report, chunks)

        # 置信度：优先取 Critic 信息充分性判定，否则默认 0.7
        confidence = critic_verdict.confidence if critic_verdict else 0.7

        # 若 LLM 遗漏参考文献章节则程序化补齐
        report = self._ensure_reference_section(raw_report, citations)

        logger.info(
            f"Synthesizer(report): 报告生成完成, "
            f"conf={confidence:.2f}, citations={len(citations)}"
        )

        return {
            "answer": report,
            "citations": citations,
            "confidence_score": confidence,
        }

    async def synthesize_stream(self, state: GraphState):
        """
        流式综合（问答模式）：逐 token 产出，最后给出解析后的结果。

        与 synthesize() 的区别：
          - 用 llm.astream 逐 token 生成，不要求 LLM 输出 JSON 元数据
          - 引用从 [n] 内联标记提取；置信度取 Critic 判定（否则默认 0.7）

        Yields:
            ("token", str) —— 逐 token 文本
            ("result", dict) —— 末尾一次，含 answer / citations / confidence_score
        """
        question = state.get("question", "")
        chunks = state.get("retrieved_chunks", [])
        history = state.get("history", [])
        critic_verdict: Optional[CriticVerdict] = state.get("critic_verdict")

        context = self._build_context(chunks)
        messages = [
            SystemMessage(content=SYNTHESIZER_STREAM_SYSTEM_PROMPT),
            HumanMessage(content=SYNTHESIZER_STREAM_USER_TEMPLATE.format(
                question=question,
                history_context=self._format_history_context(history),
                chunk_count=len(chunks),
                chunks_context=context,
            )),
        ]

        parts: list[str] = []
        async for chunk in self.llm.astream(messages):
            token = self._chunk_to_text(chunk)
            if token:
                parts.append(token)
                yield ("token", token)

        raw_answer = "".join(parts).strip()
        citations = self._extract_inline_citations(raw_answer, chunks)
        confidence = critic_verdict.confidence if critic_verdict else 0.7

        logger.info(
            f"Synthesizer(stream): 完成, conf={confidence:.2f}, "
            f"citations={len(citations)}, tokens={len(''.join(parts))}"
        )

        yield ("result", {
            "answer": raw_answer,
            "citations": citations,
            "confidence_score": confidence,
        })

    @staticmethod
    def _chunk_to_text(chunk) -> str:
        """把 LLM 流式 chunk 转成文本（兼容 str 内容与 content blocks）。"""
        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                (p.get("text", "") if isinstance(p, dict) else str(p))
                for p in content
            )
        return ""

    @staticmethod
    def _format_history_context(history) -> str:
        """把多轮历史格式化为 prompt 片段（无历史时返回空串）。"""
        from app.utils.history import format_history

        text = format_history(history)
        if not text:
            return ""
        return (
            "历史对话（用户当前问题可能用「它 / 这个 / 第二个方案」等指代历史内容，"
            "请结合历史理解指代并作答）：\n"
            f"{text}\n\n"
        )

    def _build_context(self, chunks: list[dict]) -> str:
        """将检索片段组装为带编号的上下文"""
        if not chunks:
            return "（暂无检索到相关资料）"

        sections = []
        for i, ch in enumerate(chunks):
            content = ch.get("content", "")
            source = ch.get("document_title", "未知")
            section = ch.get("metadata", {}).get("section", "")
            score = ch.get("scores", {}).get("final", 0)
            
            header = f"[{i+1}] 来源：《{source}》"
            if section:
                header += f" · {section}"
            header += f" (相关度: {score:.2f})"
            
            sections.append(f"{header}\n{content}")

        return "\n\n---\n\n".join(sections)

    def _parse_response(
        self,
        raw_text: str,
        chunks: list[dict],
    ) -> tuple[str, list[Citation], float]:
        """
        解析 LLM 输出，分离正文和 JSON 元数据。
        
        Returns:
            (answer_text, citations_list, confidence_score)
        """
        confidence = 0.7  # 默认值
        citations: list[Citation] = []

        # 尝试提取尾部 JSON 块
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{[\s\S]*?"confidence"[\s\S]*?\}', raw_text)

        answer_text = raw_text
        if json_match:
            try:
                meta = json.loads(json_match.group(1))
                confidence = meta.get("confidence", confidence)
                
                for cit in meta.get("citations", []):
                    citations.append(Citation(
                        chunk_id=cit.get("id", 0),
                        document_title=cit.get("document_title", ""),
                        section=cit.get("section", ""),
                        content_snippet=cit.get("snippet", ""),
                    ))

                # 从正文中去掉 JSON 部分
                answer_text = raw_text[:json_match.start()].strip()
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"解析引用 JSON 失败: {e}")
                # 尝试从 [n] 引用标记中提取
                citations = self._extract_inline_citations(raw_text, chunks)

        if not citations:
            citations = self._extract_inline_citations(answer_text, chunks)

        return answer_text, citations, confidence

    def _extract_inline_citations(
        self,
        text: str,
        chunks: list[dict],
    ) -> list[Citation]:
        """从 [n] 引用标记中提取 Citation 对象"""
        citations = []
        # 按编号升序去重，保证引用列表顺序与正文标注一致
        ref_numbers = sorted(set(map(int, re.findall(r"\[(\d+)\]", text))))

        for num in ref_numbers:
            idx = num - 1  # 编号从 1 开始
            if 0 <= idx < len(chunks):
                ch = chunks[idx]
                citations.append(Citation(
                    chunk_id=ch.get("chunk_id", 0),
                    document_title=ch.get("document_title", ""),
                    section=ch.get("metadata", {}).get("section", ""),
                    content_snippet=(ch.get("content", "") or "")[:100],
                ))
        return citations

    def _ensure_reference_section(
        self,
        report: str,
        citations: list[Citation],
    ) -> str:
        """若报告缺参考文献章节则补齐（保证引用可溯源）。"""
        if "## 参考文献" in report or "## References" in report:
            return report
        if not citations:
            return report

        lines = ["", "## 参考文献", ""]
        for i, c in enumerate(citations, 1):
            title = c.document_title or "未知来源"
            section = f"（{c.section}）" if c.section else ""
            lines.append(f"[{i}] 《{title}》{section}")
            if c.content_snippet:
                lines.append(f"    > {c.content_snippet[:120]}")
        return report.rstrip() + "\n" + "\n".join(lines)


# 全局单例
synthesizer_agent = SynthesizerAgent()
