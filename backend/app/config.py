"""应用配置管理 - 从 .env / 环境变量加载
.env 文件查找顺序（找到第一个就停）：
  1. backend/.env（与 app/ 同级，开发期常用）
  2. 项目根目录的 .env（容器/Docker 部署常用）
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache


# 项目根目录 = 当前文件 (app/config.py) 的上两级
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _find_env_file() -> Optional[str]:
    """依次查找 backend/.env 和 项目根/.env，返回第一个存在的路径"""
    candidates = [
        BACKEND_DIR / ".env",
        PROJECT_ROOT / ".env",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


class Settings(BaseSettings):
    """全局配置（全部从环境变量读取）"""

    # === LLM ===
    openai_api_key: str = "sk-placeholder-set-in-env-file"
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # === Judge 模型 ===
    judge_model: str = "gpt-4o-mini"
    judge_base_url: str = "https://api.openai.com/v1"
    judge_api_key: Optional[str] = None

    # === 数据库（占位符仅供骨架启动验证，连库时会报错是预期的）===
    database_url: str = "postgresql+asyncpg://rag_user:rag_pass@localhost:5432/rag_db"
    sync_database_url: str = "postgresql://rag_user:rag_pass@localhost:5432/rag_db"

    # === Redis ===
    redis_url: str = "redis://localhost:6379/0"

    # === Embedding ===
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_device: str = "cpu"
    embedding_dimension: int = 1024

    # Reranker
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_enabled: bool = True  # 检索对比实验需要能一键关闭

    # === 查询增强（默认关，不影响既有行为）===
    query_rewrite_enabled: bool = False  # LLM 查询改写（多查询召回合并）
    hyde_enabled: bool = False  # HyDE 假设文档向量

    # === JWT（开发期占位符，生产前必须改）===
    jwt_secret: str = "dev-placeholder-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # === 服务 ===
    host: str = "0.0.0.0"
    port: int = 8000

    # === LangGraph Checkpointer ===
    checkpoint_postgres_uri: str = ""

    # === 文件上传 ===
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50
    allowed_extensions: str = ".pdf,.docx,.doc,.md,.txt,.html"

    # === 报告 PDF 导出（Chrome headless 渲染，不用 weasyprint）===
    chrome_path: str = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"

    model_config = SettingsConfigDict(
        # 动态选择 .env 路径：backend/ 下找 → 根目录找
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# 启动时打印实际使用的 .env 路径（方便排查）
_env_used = _find_env_file()
if _env_used:
    print(f"[config] 加载环境变量: {_env_used}")
else:
    print(f"[config] ⚠️ 未找到 .env 文件，将使用系统环境变量或默认值")
