"""文档批量上传测试：部分失败隔离"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBatchUpload:
    """批量上传接口单元测试"""

    @pytest.mark.asyncio
    async def test_upload_batch_partial_failure(self):
        from app.api import documents as dmod
        from app.api.documents import upload_batch

        f1 = MagicMock()
        f1.filename = "a.txt"
        f2 = MagicMock()
        f2.filename = "b.txt"

        async def fake_ingest_single(file, db):
            if file is f1:
                return {"id": 1, "filename": "a.txt", "file_type": "txt",
                        "status": "ready", "total_chunks": 3}
            raise RuntimeError("boom")

        db = MagicMock()
        db.rollback = AsyncMock()

        with patch.object(dmod, "_ingest_single", side_effect=fake_ingest_single):
            resp = await upload_batch([f1, f2], db)

        assert resp["total"] == 2
        assert resp["succeeded"] == 1
        assert resp["failed"] == 1
        assert resp["results"][0]["status"] == "ready"
        assert resp["results"][1]["status"] == "failed"
        assert "boom" in resp["results"][1]["error"]
        db.rollback.assert_awaited_once()  # 失败文件回滚，不影响其他


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
