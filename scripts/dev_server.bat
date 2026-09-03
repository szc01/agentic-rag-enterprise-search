@echo off
REM Agentic RAG 开发服务器启动脚本
REM 目的：规避 WorkBuddy/Claude Code 环境注入的 HTTP_PROXY 导致的 HuggingFace 502 问题。
REM   - 清空代理变量：让 httpx 直连 DeepSeek（api.deepseek.com 国内可直连）
REM   - HF_HUB_OFFLINE=1：embedding/reranker 走本地缓存，不联网下载
cd /d "%~dp0..\backend"

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
