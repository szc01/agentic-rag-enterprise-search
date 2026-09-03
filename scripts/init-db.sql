-- Agentic RAG 系统数据库初始化脚本
-- 首次启动容器时自动执行（只执行一次）
CREATE EXTENSION IF NOT EXISTS vector;

-- 注：chunks 表的 HNSW 向量索引不在这里建——此时表还不存在。
-- 它由应用启动时（app/__init__.py lifespan）幂等执行：
--   CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
--   ON chunks USING hnsw (embedding vector_cosine_ops);
