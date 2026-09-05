"""ORM 模型统一导出。

导入本包会把所有模型注册到 Base.metadata，
确保 lifespan 里 Base.metadata.create_all 能建出全部表。
"""
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.query_log import QueryLog
from app.models.report import Report
from app.models.bm25_index_state import BM25IndexState

__all__ = ["Document", "Chunk", "QueryLog", "Report", "BM25IndexState"]
