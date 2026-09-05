"""异步 SQLAlchemy 数据库引擎与 Session 管理"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# 异步引擎（asyncpg 驱动）
engine = create_async_engine(
    settings.database_url,
    echo=True,  # 开发阶段打印 SQL，生产关掉
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# 异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def ensure_schema() -> None:
    """建表 + 建 pgvector HNSW 向量索引（幂等）。

    供应用启动（lifespan）与脚本复用。
    注意：需先 import app.models 把 ORM 模型注册到 Base.metadata，
    否则 create_all 不会建出 chunks 等表。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # pgvector HNSW 向量索引（幂等；chunks 表由 create_all 建好后再建索引，
        # 故不放 init-db.sql——那里执行时表还不存在）
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw "
            "ON chunks USING hnsw (embedding vector_cosine_ops)"
        ))
        # Day 9 Task 4: BM25 索引状态表（JSONB 快照，单行）
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS bm25_index_state ("
            "  singleton_id VARCHAR(20) PRIMARY KEY DEFAULT 'singleton',"
            "  state JSONB NOT NULL DEFAULT '{}'::jsonb,"
            "  chunk_count INTEGER NOT NULL DEFAULT 0,"
            "  total_tokens INTEGER NOT NULL DEFAULT 0,"
            "  schema_version INTEGER NOT NULL DEFAULT 1,"
            "  saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        # query_logs 增量列（幂等）：早期版本的 query_logs 表可能已存在，
        # create_all 不会给既有表加列，这里用 ALTER 补上新增字段。
        await conn.execute(text(
            "ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS "
            "use_agentic BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS "
            "status VARCHAR(20) NOT NULL DEFAULT 'success'"
        ))
        await conn.execute(text(
            "ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS error TEXT"
        ))
