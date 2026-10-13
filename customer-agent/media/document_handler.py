"""Document Handler for WhatsApp attachments.

Extracts text from PDF, DOCX, and TXT documents without requiring heavy external dependencies.
Truncates long documents safely to protect context limits.
"""
from __future__ import annotations

import io
import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path
from typing import Optional

logger = logging.getLogger("octapus.media.document")

DEFAULT_MAX_DOC_CHARS = 12000


class DocumentHandler:
    def __init__(self, max_chars: Optional[int] = None):
        self.max_chars = max_chars or int(os.environ.get("MAX_DOC_CHARS", DEFAULT_MAX_DOC_CHARS))

    def extract_text(
        self,
        content_bytes: bytes,
        filename: str = "document.txt",
        mimetype: str = "application/octet-stream",
        caption: str = "",
    ) -> str:
        """
        Extract text from PDF, DOCX, or TXT file bytes.
        Truncates safely if length exceeds max_chars.
        Returns a formatted string ready for the Horus agent.
        """
        if not content_bytes:
            raise ValueError("Document file is empty.")

        fname_lower = (filename or "").lower()
        extracted_text = ""

        # 1. DOCX
        if fname_lower.endswith(".docx") or "wordprocessingml" in mimetype:
            extracted_text = self._extract_docx(content_bytes)

        # 2. PDF
        elif fname_lower.endswith(".pdf") or "pdf" in mimetype:
            extracted_text = self._extract_pdf(content_bytes)

        # 3. TXT / Markdown / Plain Text
        else:
            extracted_text = self._extract_txt(content_bytes)

        extracted_text = extracted_text.strip()
        if not extracted_text:
            extracted_text = "[No readable text found in document]"

        # Safe truncation
        if len(extracted_text) > self.max_chars:
            extracted_text = (
                extracted_text[: self.max_chars]
                + f"\n\n[... Document truncated: displaying first {self.max_chars:,} characters ...]"
            )

        header = f"[Document: {filename}]"
        result = f"{header}\n{extracted_text}"

        if caption and caption.strip():
            result += f"\n\nUser note: {caption.strip()}"

        return result

    @staticmethod
    def _extract_docx(data: bytes) -> str:
        """Extract text from DOCX (Office Open XML word/document.xml)."""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" not in z.namelist():
                    return "[Invalid DOCX format: word/document.xml missing]"
                xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

                paragraphs = []
                for p in root.iter(f"{{{namespaces['w']}}}p"):
                    texts = [
                        t.text
                        for t in p.iter(f"{{{namespaces['w']}}}t")
                        if t.text
                    ]
                    if texts:
                        paragraphs.append("".join(texts))

                return "\n".join(paragraphs)
        except Exception as exc:
            logger.warning("DOCX text extraction error: %s", exc)
            return f"[Error reading DOCX: {exc}]"

    @staticmethod
    def _extract_pdf(data: bytes) -> str:
        """Lightweight pure-python extraction for text streams in PDF."""
        try:
            text_chunks = []
            # Find and decompress FlateDecode streams
            stream_pattern = re.compile(rb"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)
            for match in stream_pattern.finditer(data):
                raw_stream = match.group(1)
                try:
                    decompressed = zlib.decompress(raw_stream)
                except Exception:
                    decompressed = raw_stream

                # Look for text within parentheses in PDF content streams: (Text) Tj or [(Text)] TJ
                # Extract ASCII/UTF-8 readable runs
                runs = re.findall(rb"\((.*?)\)\s*T[jJ]", decompressed)
                for run in runs:
                    try:
                        clean_run = run.decode("utf-8", errors="ignore").strip()
                        if clean_run:
                            text_chunks.append(clean_run)
                    except Exception:
                        pass

                # Also match text inside ET / BT blocks
                block_runs = re.findall(rb"\[(.*?)\]\s*TJ", decompressed)
                for block in block_runs:
                    sub_runs = re.findall(rb"\((.*?)\)", block)
                    combined = "".join(r.decode("utf-8", errors="ignore") for r in sub_runs)
                    if combined.strip():
                        text_chunks.append(combined.strip())

            if text_chunks:
                return "\n".join(text_chunks)

            # Fallback to general printable string extraction
            printable = re.findall(rb"[A-Za-z0-9\s.,!?:;\-_/'\"()]{4,}", data)
            meaningful = [
                p.decode("utf-8", errors="ignore").strip()
                for p in printable
                if not p.startswith(rb"obj") and not p.startswith(rb"endobj")
            ]
            return "\n".join(meaningful[:500])
        except Exception as exc:
            logger.warning("PDF extraction error: %s", exc)
            return f"[Error reading PDF: {exc}]"

    @staticmethod
    def _extract_txt(data: bytes) -> str:
        """Decode plain text file."""
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
