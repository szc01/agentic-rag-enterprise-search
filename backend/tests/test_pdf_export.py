"""报告 PDF 导出测试：markdown→HTML、Chrome headless 渲染、下载端点"""
import os
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


class TestMarkdownToHtml:
    def test_html_contains_meta_and_styles(self):
        from app.api.report import _markdown_to_html

        html = _markdown_to_html(
            "# 标题\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint(1)\n```"
        )
        assert '<meta charset="utf-8">' in html
        assert "<table>" in html
        assert "<pre>" in html  # 代码块被渲染
        assert "Microsoft YaHei" in html  # 中文字体内联 CSS


class TestMdToPdfSync:
    def test_returns_valid_pdf_bytes(self):
        from app.api import report as rmod

        # 假 Chrome 可执行文件（_md_to_pdf_sync 会做 isfile 校验）
        fd, chrome = tempfile.mkstemp()
        os.close(fd)

        def fake_run(cmd, **kwargs):
            pdf_flag = next(a for a in cmd if a.startswith("--print-to-pdf="))
            pdf_path = pdf_flag.split("--print-to-pdf=", 1)[1]
            with open(pdf_path, "wb") as f:
                f.write(b"%PDF-1.4 fake pdf content")
            return MagicMock(returncode=0, stderr=b"")

        try:
            with patch.object(rmod.settings, "chrome_path", chrome), \
                 patch.object(rmod.subprocess, "run", side_effect=fake_run):
                pdf = rmod._md_to_pdf_sync("# 标题\n正文")
        finally:
            os.remove(chrome)

        assert pdf.startswith(b"%PDF-")

    def test_empty_content_raises(self):
        from app.api.report import _md_to_pdf_sync
        with pytest.raises(ValueError):
            _md_to_pdf_sync("   ")


class TestDownloadPdfEndpoint:
    @pytest.mark.asyncio
    async def test_pdf_download_ready(self):
        from app.api import report as rmod

        report = MagicMock()
        report.id = 1
        report.status = "ready"
        report.content = "# 报告"
        db = MagicMock()
        db.get = AsyncMock(return_value=report)

        with patch.object(rmod, "markdown_to_pdf", new=AsyncMock(return_value=b"%PDF-1.4 x")):
            resp = await rmod.download_report(1, "pdf", db)

        assert resp.media_type == "application/pdf"
        assert resp.body.startswith(b"%PDF-")
        assert 'attachment; filename="report_1.pdf"' in resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_pdf_download_generating_returns_409(self):
        from app.api import report as rmod

        report = MagicMock()
        report.status = "generating"
        db = MagicMock()
        db.get = AsyncMock(return_value=report)

        with pytest.raises(HTTPException) as e:
            await rmod.download_report(1, "pdf", db)
        assert e.value.status_code == 409

    @pytest.mark.asyncio
    async def test_pdf_download_failure_returns_500(self):
        from app.api import report as rmod

        report = MagicMock()
        report.status = "ready"
        report.content = "x"
        db = MagicMock()
        db.get = AsyncMock(return_value=report)

        with patch.object(
            rmod, "markdown_to_pdf", new=AsyncMock(side_effect=RuntimeError("chrome 挂了"))
        ):
            with pytest.raises(HTTPException) as e:
                await rmod.download_report(1, "pdf", db)
        assert e.value.status_code == 500
        assert "chrome 挂了" in e.value.detail


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
