"""文档相关 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DocumentUploadResponse(BaseModel):
    """文档上传成功响应"""
    id: int
    filename: str
    file_type: str
    status: str
    total_chunks: int = 0
    message: str = "文档上传成功，正在解析..."


class DocumentDetail(BaseModel):
    """文档详情"""
    id: int
    filename: str
    file_type: str
    file_size: int
    title: str = ""
    summary: str = ""
    total_chunks: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """文档列表（分页）"""
    total: int
    page: int
    page_size: int
    items: list[DocumentDetail]


class ChunkInfo(BaseModel):
    """分片信息（用于检索结果展示）"""
    chunk_id: int
    document_id: int
    document_title: str
    chunk_index: int
    content: str
    metadata: dict = {}
    score: float = 0.0
    highlight: str = ""  # 关键词高亮后的内容片段
