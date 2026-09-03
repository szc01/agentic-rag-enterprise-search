"""Agentic RAG 企业智能搜索与自动调研系统 - FastAPI 入口"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, ensure_schema
from app import models  # noqa: F401  确保 ORM 模型注册到 metadata（建表）
from app.api import documents, search, report, dashboard

# 纯静态前端目录（backend/static/）
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 建向量索引，关闭时释放连接"""
    await ensure_schema()
    yield
    # 关闭：释放引擎
    await engine.dispose()


app = FastAPI(
    title="Agentic RAG 企业智能搜索系统",
    description="基于多步检索规划 + 混合检索 + 引用溯源的企业知识管理平台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（前端 Vue 开发服务器）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由（先于静态挂载，避免 /static 挂载吞掉 /api 路由）
app.include_router(documents.router, prefix="/api/documents", tags=["文档管理"])
app.include_router(search.router, prefix="/api/search", tags=["搜索问答"])
app.include_router(report.router, prefix="/api/reports", tags=["调研报告"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["运营看板"])


@app.get("/", include_in_schema=False)
async def index():
    """首页：返回前端单页应用"""
    return FileResponse(STATIC_DIR / "index.html")


# 静态资源（CSS/JS 等），挂在 /static 下
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
