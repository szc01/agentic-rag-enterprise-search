"""文档解析器测试"""
import pytest
from app.services.parser import DocumentParser, ParsedBlock


class TestDocumentParser:
    """解析器单元测试"""

    def setup_method(self):
        self.parser = DocumentParser()

    def test_parse_text_file(self, tmp_path):
        """测试纯文本文件解析"""
        p = tmp_path / "test.txt"
        p.write_text("第一段内容\n\n第二段内容\n\n第三段", encoding="utf-8")
        
        blocks = list(self.parser.parse(str(p)))
        assert len(blocks) == 3
        assert all(isinstance(b, ParsedBlock) for b in blocks)
        assert "第一段" in blocks[0].content

    def test_parse_markdown(self, tmp_path):
        """测试 Markdown 文件解析"""
        content = "# 标题\n\n正文段落1\n\n## 子标题\n\n正文段落2"
        p = tmp_path / "test.md"
        p.write_text(content, encoding="utf-8")

        blocks = list(self.parser.parse(str(p)))
        assert len(blocks) >= 3
        # 第一个块应该是标题
        heading_blocks = [b for b in blocks if b.metadata.get("is_heading")]
        assert len(heading_blocks) >= 1

    def test_unsupported_extension_fallback(self, tmp_path):
        """测试不支持的文件类型回退为纯文本"""
        p = tmp_path / "test.xyz"
        p.write_text("这是未知格式的内容", encoding="utf-8")

        blocks = list(self.parser.parse(str(p)))
        assert len(blocks) == 1
        assert blocks[0].metadata.get("source_type") == "text"

    def test_empty_file(self, tmp_path):
        """测试空文件"""
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")

        blocks = list(self.parser.parse(str(p)))
        assert len(blocks) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
