"""Unit tests for WhatsApp Document Pipeline (PDF, DOCX, TXT)."""
import io
import sys
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from media.document_handler import DocumentHandler


def test_extract_txt_document():
    handler = DocumentHandler()
    raw_txt = b"Octapus LLC - Service Agreement Terms\nSection 1: ERP solutions"
    extracted = handler.extract_text(raw_txt, filename="terms.txt", mimetype="text/plain", caption="Review please")

    assert "[Document: terms.txt]" in extracted
    assert "Service Agreement Terms" in extracted
    assert "User note: Review please" in extracted


def test_extract_docx_document():
    handler = DocumentHandler()
    docx_xml = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:body>'
        b'<w:p><w:r><w:t>Project Scope for Tailoring ERP</w:t></w:r></w:p>'
        b'<w:p><w:r><w:t>Estimated delivery: 4 weeks</w:t></w:r></w:p>'
        b'</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", docx_xml)

    extracted = handler.extract_text(buf.getvalue(), filename="proposal.docx")
    assert "[Document: proposal.docx]" in extracted
    assert "Project Scope for Tailoring ERP" in extracted
    assert "Estimated delivery: 4 weeks" in extracted


def test_extract_pdf_document():
    handler = DocumentHandler()
    stream_content = b"BT /F1 12 Tf (Octapus Invoice INV-2026-001) Tj ET"
    compressed_stream = zlib.compress(stream_content)
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(compressed_stream)).encode() + b" /Filter /FlateDecode >>\n"
        b"stream\n" + compressed_stream + b"\nendstream\nendobj\nxref\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    )

    extracted = handler.extract_text(pdf_bytes, filename="invoice.pdf", mimetype="application/pdf")
    assert "[Document: invoice.pdf]" in extracted
    assert "Octapus Invoice INV-2026-001" in extracted


def test_document_safe_truncation():
    handler = DocumentHandler(max_chars=100)
    huge_text = ("A" * 200).encode("utf-8")
    extracted = handler.extract_text(huge_text, filename="large.txt")

    assert len("A" * 200) == 200
    assert "[... Document truncated: displaying first 100 characters ...]" in extracted
    assert extracted.count("A") == 100
