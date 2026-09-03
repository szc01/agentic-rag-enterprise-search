"""文档管理 API：上传 / 列表 / 详情 / 删除"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import os
import aiofiles

from app.database import get_db
from app.models.document import Document
from app.models.chunk import Chunk
from app.schemas.document import DocumentUploadResponse, DocumentDetail, DocumentListResponse
from app.config import settings
from app.services.ingestion import ingestion_service
from app.services.retriever import retriever

router = APIRouter()


# 确保上传目录存在
os.makedirs(settings.upload_dir, exist_ok=True)


async def _ingest_single(file: UploadFile, db: AsyncSession) -> dict:
    """处理单个上传文件：校验 → 落盘 → 建记录 → ingestion 入库。

    返回统一结果字典（不抛异常），供单文件与批量接口复用：
        status: "ready" | "failed"
        error:  失败原因（失败时非空）
    """
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    allowed = settings.allowed_extensions.split(",")
    if ext not in allowed:
        return {
            "filename": filename, "status": "failed", "http_status": 400,
            "error": f"不支持的文件类型: {ext}，允许的类型: {allowed}",
        }

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        return {
            "filename": filename, "status": "failed", "http_status": 400,
            "error": f"文件超过 {settings.max_upload_size_mb}MB 限制",
        }

    safe_filename = f"{os.urandom(8).hex()}_{filename}"
    file_path = os.path.join(settings.upload_dir, safe_filename)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    doc = Document(
        filename=filename,
        file_path=file_path,
        file_type=ext.lstrip("."),
        file_size=len(content),
        status="uploaded",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    try:
        doc = await ingestion_service.ingest_document(db, doc.id)
        return {
            "id": doc.id, "filename": doc.filename, "file_type": doc.file_type,
            "status": doc.status, "total_chunks": doc.total_chunks,
        }
    except Exception as e:
        return {
            "id": doc.id, "filename": doc.filename, "file_type": doc.file_type,
            "status": "failed", "total_chunks": 0, "http_status": 500,
            "error": f"{type(e).__name__}: {e}",
        }


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传单个文档 → 保存文件 → 创建记录 → 解析/分片/向量化/入库（同步全链路）"""
    result = await _ingest_single(file, db)
    if result["status"] != "ready":
        raise HTTPException(
            status_code=result.get("http_status", 500),
            detail=result.get("error", "入库失败"),
        )

    return DocumentUploadResponse(
        id=result["id"],
        filename=result["filename"],
        file_type=result["file_type"],
        status=result["status"],
        total_chunks=result["total_chunks"],
        message=f"文档 '{result['filename']}' 已入库，共 {result['total_chunks']} 个分片",
    )


@router.post("/upload-batch")
async def upload_batch(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """批量上传：逐个走 ingestion，部分失败不影响其他文件。"""
    results = []
    for file in files:
        try:
            results.append(await _ingest_single(file, db))
        except Exception as e:
            # 未预期的异常（如落盘/建记录失败）：回滚后记为失败，继续处理后续文件
            await db.rollback()
            results.append({
                "filename": file.filename or "unknown",
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            })

    succeeded = sum(1 for r in results if r["status"] == "ready")
    return {
        "total": len(files),
        "succeeded": succeeded,
        "failed": len(files) - succeeded,
        "results": results,
    }


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, description="按状态筛选"),
    db: AsyncSession = Depends(get_db),
):
    """分页获取文档列表"""
    query = select(Document)
    if status:
        query = query.where(Document.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    docs = result.scalars().all()

    return DocumentListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[DocumentDetail.model_validate(d) for d in docs],
    )


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    """获取文档详情"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档 {doc_id} 不存在")
    return DocumentDetail.model_validate(doc)


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    """删除文档及其所有分片"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档 {doc_id} 不存在")

    # 删除前取出全部 chunk id，供 BM25 索引增量删除
    chunk_ids = [r[0] for r in (await db.execute(
        select(Chunk.id).where(Chunk.document_id == doc_id)
    )).all()]

    # 删除物理文件
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    await db.delete(doc)
    await db.commit()
    await retriever.remove_chunks(chunk_ids, db)  # chunks 级联删除后增量移除
    return {"message": f"文档 '{doc.filename}' 已删除"}
