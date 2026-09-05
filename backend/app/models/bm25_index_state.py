"""BM25 索引持久化快照 ORM（pgvector 之外的「轻量元数据」落盘）

设计动机：
  HybridRetriever 的 BM25 倒排索引是纯内存结构，应用重启后要重新从 PG 全量
  加载 402 个 chunks（实测 ~1.8s）。把倒排索引快照落 PostgreSQL 后，
  启动时直接从 JSONB 反序列化，理论上能降到 < 100ms；同时文档增删同步保留
  磁盘版本，避免「应用崩溃 → 内存索引丢失 → 需要重建」。

存储格式（JSONB，单条记录）：
  {
    "version": 1,                                # 模式版本，便于不兼容迁移
    "saved_at": "2026-09-02T21:40:00+08:00",     # 落盘时间
    "chunk_count": 402,                           # 总分片数
    "total_tokens": 61234,                        # 所有 chunk token 总数（用于 avgdl）
    "postings": {                                 # 倒排表：term -> {chunk_id: tf}
      "深度学习": {"1": 2, "37": 1, ...},
      ...
    },
    "doc_lengths": {"1": 234, "2": 156, ...},     # chunk_id -> token 数
    "chunk_ids": [1, 2, 3, ...]                  # 所有已索引 chunk_id（一致性校验用）
  }

trade-off：
  - 写：每次 add/remove 后会触发一次 JSONB 更新（20KB-3MB）
  - 读：启动 / 重建时一次性反序列化，避免 402 个 chunk 的 SQL roundtrip
  - 不存：原始 content（防止主键大对象重复存储，重建时 SQL 仍可校验 chunk 是否存在）
"""
from sqlalchemy import String, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class BM25IndexState(Base):
    """BM25 索引快照（单行表，以 singleton_id="singleton" 为唯一键）。

    与 Document/Chunk 等业务表解耦：业务数据变更时不影响本表，只有倒排
    索引结构变化（add/remove chunk）才更新。
    """
    __tablename__ = "bm25_index_state"

    # 单例主键：永远只有一行
    singleton_id: Mapped[str] = mapped_column(
        String(20), primary_key=True, default="singleton"
    )
    # JSONB 快照（见模块 docstring 描述的格式）
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # 元数据（便于运维观察，不参与重建）
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    saved_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return (
            f"<BM25IndexState(singleton='{self.singleton_id}', "
            f"chunks={self.chunk_count}, tokens={self.total_tokens})>"
        )
