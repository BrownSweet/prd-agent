from __future__ import annotations

from types import SimpleNamespace

import pytest

from prd_agent.attachments import (
    IncomingAttachment,
    extract_attachment_text,
    store_incoming_attachment,
)


ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

SIMPLE_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 300 144] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT /F1 18 Tf 30 100 Td (PDF Requirement) Tj ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000241 00000 n 
0000000311 00000 n 
trailer
<< /Root 1 0 R /Size 6 >>
startxref
404
%%EOF
"""


def _store(tmp_path, filename: str, content: bytes):
    data = store_incoming_attachment(
        tmp_path,
        "project-1",
        IncomingAttachment(filename, None, content),
    )
    return SimpleNamespace(**data, status="pending", extracted_text=None)


def test_extracts_text_markdown_html_docx_and_pdf(tmp_path) -> None:
    markdown = _store(tmp_path, "需求.md", "# 标题\n\n- 结构化输入".encode())
    html = _store(
        tmp_path,
        "需求.html",
        "<h1>需求</h1><script>ignore()</script><p>HTML 输入</p>".encode(),
    )

    from docx import Document

    docx_path = tmp_path / "source.docx"
    document = Document()
    document.add_paragraph("DOCX 输入")
    document.save(docx_path)
    docx = _store(tmp_path, "需求.docx", docx_path.read_bytes())
    pdf = _store(tmp_path, "需求.pdf", SIMPLE_PDF)

    assert "结构化输入" in extract_attachment_text(markdown, tmp_path)
    assert "HTML 输入" in extract_attachment_text(html, tmp_path)
    assert "DOCX 输入" in extract_attachment_text(docx, tmp_path)
    assert "PDF Requirement" in extract_attachment_text(pdf, tmp_path)


def test_rejects_unsupported_and_empty_attachments(tmp_path) -> None:
    with pytest.raises(ValueError, match="不支持的附件类型"):
        _store(tmp_path, "需求.exe", b"binary")

    empty = _store(tmp_path, "empty.txt", b"   ")
    with pytest.raises(ValueError, match="没有可用文本"):
        extract_attachment_text(empty, tmp_path)


def test_image_uses_vision_llm(tmp_path) -> None:
    image = _store(tmp_path, "screen.png", ONE_PIXEL_PNG)

    class VisionLLM:
        def supports_multimodal(self) -> bool:
            return True

        def call(self, messages):
            assert messages[0]["files"]
            return "图片里有创建项目按钮"

    assert extract_attachment_text(image, tmp_path, VisionLLM()) == "图片里有创建项目按钮"


def test_image_rejects_non_vision_llm(tmp_path) -> None:
    image = _store(tmp_path, "screen.png", ONE_PIXEL_PNG)

    class TextOnlyLLM:
        def supports_multimodal(self) -> bool:
            return False

    with pytest.raises(ValueError, match="不支持图片分析"):
        extract_attachment_text(image, tmp_path, TextOnlyLLM())
