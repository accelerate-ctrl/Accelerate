from io import BytesIO

import pytest

from app.services.text_extraction import extract


def test_txt_extract():
    content = b"Hello\nWorld"
    doc = extract(content, file_name="x.txt")
    assert doc.text == "Hello\nWorld"
    assert doc.extractor == "txt"
    assert doc.page_count == 1


def test_docx_extract():
    docx = pytest.importorskip("docx")  # python-docx
    Document = docx.Document
    doc_obj = Document()
    doc_obj.add_paragraph("Alpha")
    doc_obj.add_paragraph("Beta")
    buf = BytesIO()
    doc_obj.save(buf)
    out = extract(buf.getvalue(), file_name="x.docx")
    assert out.text == "Alpha\nBeta"
    assert out.extractor == "docx"


def test_unsupported_raises():
    with pytest.raises(ValueError):
        extract(b"x", file_name="x.unknown")
