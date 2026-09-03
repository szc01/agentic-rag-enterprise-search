"""智能分片器：将解析出的文本块切分为适合检索的 Chunk"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# 默认分片参数
DEFAULT_CHUNK_SIZE = 500       # 每片目标字符数（中文约 250-300 字）
DEFAULT_CHUNK_OVERLAP = 50     # 相邻分片重叠字符数
MIN_CHUNK_SIZE = 50           # 最小分片大小（低于此丢弃）


@dataclass
class Chunk:
    """一个分片"""
    content: str
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)
    token_count: int = 0


@dataclass
class SubQuery:
    """Planner 分解出的子查询"""
    query: str
    rationale: str = ""        # 为什么需要查这个子问题


class DocumentChunker:
    """
    多策略混合分片器。
    
    策略优先级：
      1. 标题/章节边界分割（保留语义完整性）
      2. 段落边界分割（自然段落）
      3. 固定长度截断 + 重叠（兜底）
    
    特殊处理：
      - 表格不拆（保持完整）
      - 代码块不拆
      - 中文按句子/子句断句（避免在词语中间切断）
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
        min_chunk_size: int = MIN_CHUNK_SIZE,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def chunk_blocks(
        self,
        blocks: list[dict],  # [{"content": ..., "metadata": ...}, ...]
        document_id: int = 0,
    ) -> list[Chunk]:
        """
        将 Parser 输出的文本块列表切分为 Chunk 列表。
        
        Args:
            blocks: 解析器输出的文本块列表
            document_id: 所属文档 ID
            
        Returns:
            list[Chunk]: 分片列表
        """
        chunks: list[Chunk] = []
        global_idx = 0

        for block in blocks:
            content = block["content"]
            meta = block.get("metadata", {})

            # 表格和代码不拆，直接作为一个 Chunk
            if meta.get("is_table") or meta.get("is_code"):
                if len(content) >= self.min_chunk_size:
                    chunks.append(Chunk(
                        content=content,
                        chunk_index=global_idx,
                        metadata={**meta, "document_id": document_id},
                        token_count=self._estimate_tokens(content),
                    ))
                    global_idx += 1
                continue

            # 标题/章节级别：尝试按标题分割
            if meta.get("is_heading"):
                sub_chunks = self._split_by_structure(content, meta, document_id)
                for sc in sub_chunks:
                    sc.chunk_index = global_idx
                    global_idx += 1
                chunks.extend(sub_chunks)
                continue

            # 正文：先按段落分割，再按长度截断
            paragraphs = self._split_paragraphs(content)
            current_buffer = ""

            for para in paragraphs:
                if len(current_buffer) + len(para) <= self.chunk_size:
                    current_buffer += ("\n" if current_buffer else "") + para
                else:
                    # 当前缓冲区已满，输出
                    if len(current_buffer) >= self.min_chunk_size:
                        chunks.append(Chunk(
                            content=current_buffer.strip(),
                            chunk_index=global_idx,
                            metadata={**meta, "document_id": document_id},
                            token_count=self._estimate_tokens(current_buffer),
                        ))
                        global_idx += 1

                    # 如果单段就超长，强制截断
                    if len(para) > self.chunk_size:
                        for seg in self._split_by_length(para):
                            if len(seg) >= self.min_chunk_size:
                                chunks.append(Chunk(
                                    content=seg.strip(),
                                    chunk_index=global_idx,
                                    metadata={**meta, "document_id": document_id},
                                    token_count=self._estimate_tokens(seg),
                                ))
                                global_idx += 1
                        current_buffer = ""
                    else:
                        current_buffer = para

            # 处理剩余缓冲区
            if current_buffer and len(current_buffer) >= self.min_chunk_size:
                chunks.append(Chunk(
                    content=current_buffer.strip(),
                    chunk_index=global_idx,
                    metadata={**meta, "document_id": document_id},
                    token_count=self._estimate_tokens(current_buffer),
                ))
                global_idx += 1

        return chunks

    def _split_paragraphs(self, text: str) -> list[str]:
        """按空行/换行分割为段落"""
        # 先按双换行（段落边界）分割
        raw_paragraphs = re.split(r"\n\s*\n", text)
        paragraphs = []
        for p in raw_paragraphs:
            p = p.strip()
            if not p:
                continue
            # 单个段落内如果太长，按句号/分号再细分
            if len(p) > self.chunk_size * 1.5:
                sentences = re.split(r"(?<=[。！？；\n])", p)
                paragraphs.extend(s.strip() for s in sentences if s.strip())
            else:
                paragraphs.append(p)
        return paragraphs

    def _split_by_structure(self, text: str, meta: dict, doc_id: int) -> list[Chunk]:
        """按结构（标题下的内容）分割"""
        lines = text.split("\n")
        chunks = []
        current_section = ""
        idx = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 遇到子标题则分段
            if line.startswith("#") or (line.startswith(("一、", "二、", "三、", "四、", "五、",
                                                        "1.", "2.", "3.", "4.", "5.",
                                                        "（1）", "（2）", "（3）"))):
                if current_section and len(current_section) >= self.min_chunk_size:
                    chunks.append(Chunk(
                        content=current_section.strip(),
                        metadata={**meta, "document_id": doc_id},
                        token_count=self._estimate_tokens(current_section),
                    ))
                    idx += 1
                current_section = line + "\n"
            else:
                current_section += line + "\n"

        if current_section and len(current_section) >= self.min_chunk_size:
            chunks.append(Chunk(
                content=current_section.strip(),
                metadata={**meta, "document_id": doc_id},
                token_count=self._estimate_tokens(current_section),
            ))

        return chunks

    def _split_by_length(self, text: str) -> list[str]:
        """固定长度截断 + 重叠（兜底策略）"""
        segments = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            # 尝试在句号/换行处断开
            if end < len(text):
                break_point = text.rfind("。", start, end)
                if break_point == -1 or break_point < start + self.min_chunk_size:
                    break_point = text.rfind("\n", start, end)
                if break_point == -1 or break_point < start + self.min_chunk_size:
                    break_point = end
                else:
                    break_point += 1  # 包含句号
            else:
                break_point = len(text)

            segment = text[start:break_point].strip()
            if segment:
                segments.append(segment)
            start = break_point - self.overlap
            if start < 0:
                start = 0
        return segments

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算 token 数（中文 ~1.5 字符/token，英文 ~4 字符/token）"""
        chinese_chars = len(re.compile(r"[\u4e00-\u9fff]").findall(text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)


# 全局单例
chunker = DocumentChunker()
