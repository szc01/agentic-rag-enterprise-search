"""调研报告 API：生成 / 列表 / 下载"""
import asyncio
import logging
import os
import subprocess
import tempfile
from datetime import datetime

import markdown as md_lib
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.models.report import Report

logger = logging.getLogger(__name__)

router = APIRouter()

# ── PDF 导出（markdown → HTML → Chrome headless → PDF）──────────────

_PDF_CSS = """
body {
  font-family: "Microsoft YaHei", "PingFang SC", "SimSun", sans-serif;
  color: #1f2328;
  line-height: 1.7;
  font-size: 14px;
  max-width: 820px;
  margin: 40px auto;
  padding: 0 24px;
}
h1, h2, h3, h4 { color: #0f1419; line-height: 1.3; }
h1 { font-size: 24px; border-bottom: 2px solid #e1e4e8; padding-bottom: 8px; }
h2 { font-size: 20px; border-bottom: 1px solid #e1e4e8; padding-bottom: 6px; margin-top: 28px; }
h3 { font-size: 16px; margin-top: 20px; }
code {
  font-family: Consolas, "Courier New", monospace;
  background: #f6f8fa;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 13px;
}
pre {
  background: #f6f8fa;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}
pre code { background: transparent; padding: 0; }
blockquote {
  margin: 12px 0;
  padding: 4px 16px;
  border-left: 4px solid #d0d7de;
  color: #57606a;
  background: #f6f8fa;
}
table { border-collapse: collapse; width: 100%; margin: 16px 0; }
th, td { border: 1px solid #d0d7de; padding: 6px 12px; text-align: left; }
th { background: #f6f8fa; font-weight: 600; }
a { color: #0969da; text-decoration: none; }
"""


def _markdown_to_html(md: str) -> str:
    """把 Markdown 报告渲染为内联 CSS 的完整 HTML 文档。"""
    body = md_lib.markdown(
        md,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br", "codehilite"],
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f"<style>{_PDF_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def _md_to_pdf_sync(md: str) -> bytes:
    """同步执行 markdown → PDF（Chrome headless），返回 PDF bytes。"""
    if not md or not md.strip():
        raise ValueError("报告内容为空，无法导出 PDF")

    chrome = settings.chrome_path
    if not os.path.isfile(chrome):
        raise RuntimeError(f"未找到 Chrome 可执行文件：{chrome}，请在 .env 配置 CHROME_PATH")

    html_doc = _markdown_to_html(md)
    html_path = None
    pdf_path = None
    try:
        # Windows 下先关闭文件句柄再交给 Chrome 读取
        with tempfile.NamedTemporaryFile(
            "w", suffix=".html", encoding="utf-8", delete=False
        ) as f:
            f.write(html_doc)
            html_path = f.name
        pdf_path = html_path + ".pdf"

        proc = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                f"--print-to-pdf={pdf_path}",
                "--no-pdf-header-footer",
                html_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"Chrome 退出码 {proc.returncode}: {stderr}")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        if not pdf_bytes.startswith(b"%PDF-"):
            raise RuntimeError("Chrome 输出不是合法 PDF（文件头不是 %PDF-）")
        return pdf_bytes
    finally:
        for p in (html_path, pdf_path):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass


async def markdown_to_pdf(md: str) -> bytes:
    """异步包装：把阻塞的 Chrome 渲染丢进线程池。"""
    return await asyncio.to_thread(_md_to_pdf_sync, md)


class ReportGenerateRequest(BaseModel):
    """报告生成请求"""
    topic: str = Field(..., min_length=1, max_length=500, description="调研主题")
    depth: int = Field(default=2, ge=1, le=5, description="检索深度（迭代轮数）")
    format: str = Field(default="markdown", pattern="^(markdown|pdf)$")


async def _generate_report_task(report_id: int) -> None:
    """后台任务：跑 Agentic 报告编排，回写 Report 记录。

    使用独立的数据库会话（请求会话在响应后已关闭），
    失败时把 status 置为 failed 并记录 error。
    """
    from app.graph import run_agentic_report

    async with AsyncSessionLocal() as db:
        report = await db.get(Report, report_id)
        if report is None:
            logger.warning(f"报告后台任务: report {report_id} 不存在")
            return

        try:
            result = await run_agentic_report(report.topic, report.depth, db)

            report.content = result["answer"]
            report.citations = result["citations"]
            report.stats = {
                "sub_queries": result["trace"]["sub_queries"],
                "chunks_used": result["trace"]["chunks_retrieved"],
                "iterations": result["trace"]["iterations"],
                "confidence": result["confidence_score"],
            }
            report.status = "ready"
            report.completed_at = datetime.utcnow()
            await db.commit()
            logger.info(f"报告 {report_id} 生成完成: "
                        f"chunks={report.stats['chunks_used']}, "
                        f"citations={len(report.citations)}")
        except Exception as e:
            logger.exception(f"报告 {report_id} 生成失败")
            report.status = "failed"
            report.error = f"{type(e).__name__}: {e}"
            report.completed_at = datetime.utcnow()
            await db.commit()


@router.post("/generate")
async def generate_report(
    request: ReportGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    给定主题，自动执行多步 Agentic 检索并生成带引用的结构化调研报告。

    流程：
    1. 创建报告记录（status=generating），立即返回 report_id
    2. BackgroundTasks 后台执行 Agentic 编排（planner→retrieval→critic→synthesizer）
    3. Synthesizer 报告模式按「背景/现状/技术方案/案例/趋势」输出 Markdown
    4. 前端轮询 GET /reports 直到 status=ready
    """
    report = Report(topic=request.topic, depth=request.depth, status="generating")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    background_tasks.add_task(_generate_report_task, report.id)

    return {
        "report_id": report.id,
        "status": report.status,
        "topic": report.topic,
        "message": "报告已进入后台生成，轮询 GET /reports 直到 status=ready 后即可下载",
    }


@router.get("")
async def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, description="按状态筛选"),
    db: AsyncSession = Depends(get_db),
):
    """分页获取历史报告列表（含置信度摘要）"""
    query = select(Report)
    if status:
        query = query.where(Report.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Report.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    reports = result.scalars().all()

    items = []
    for r in reports:
        stats = r.stats or {}
        items.append({
            "id": r.id,
            "topic": r.topic,
            "status": r.status,
            "depth": r.depth,
            "confidence": stats.get("confidence"),
            "sub_queries": len(stats.get("sub_queries", [])),
            "chunks_used": stats.get("chunks_used", 0),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{report_id}/download")
async def download_report(
    report_id: int,
    fmt: str = Query(default="markdown", pattern="^(markdown|pdf)$"),
    db: AsyncSession = Depends(get_db),
):
    """下载报告（markdown 直接返回全文；pdf 用 Chrome headless 渲染导出）"""
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"报告 {report_id} 不存在")

    if fmt == "pdf":
        if report.status != "ready":
            raise HTTPException(
                status_code=409,
                detail=f"报告尚未生成完成（当前 status={report.status}）",
            )
        try:
            pdf_bytes = await markdown_to_pdf(report.content)
        except Exception as e:
            logger.exception("报告 PDF 导出失败")
            raise HTTPException(
                status_code=500,
                detail=f"PDF 生成失败：{type(e).__name__}: {e}",
            ) from e

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="report_{report_id}.pdf"'
            },
        )

    if report.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"报告尚未生成完成（当前 status={report.status}）",
        )

    filename = f"report_{report_id}.md"
    return Response(
        content=report.content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
