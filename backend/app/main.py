"""FastAPI 应用入口（独立文件方便 uvicorn 直接启动）

用法：
    uvicorn app.main:app --reload --port 8000   # 开发热重载（推荐）
    python -m app.main                          # 直接启动
"""
import uvicorn

from app import app  # FastAPI 实例定义在 app/__init__.py

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
