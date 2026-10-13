"""Document Generation Engine.

Produces finished, usable document outputs (Markdown, HTML, Plain Text, CSV)
and writes them to static/generated_docs/ for immediate verification and download.
Ensures credentials and secrets are never embedded in generated files.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("octapus.tools.document_generator")

BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_DOCS_DIR = BASE_DIR / "static" / "generated_docs"
GENERATED_DOCS_DIR.mkdir(parents=True, exist_ok=True)


class DocumentGenerator:
    """Creates, verifies, and serves generated document deliverables."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or GENERATED_DOCS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        clean = re.sub(r"[^\w\-.]", "_", name.strip())
        return clean[:80] or "document"

    def _sanitize_content(self, content: str) -> str:
        """Strip accidentally passed API keys or credential patterns."""
        sanitized = re.sub(r"(?i)(sk-[a-zA-Z0-9_-]{20,})", "[REDACTED_API_KEY]", content)
        sanitized = re.sub(r"(?i)(ak_ac_[a-zA-Z0-9_-]{20,})", "[REDACTED_API_KEY]", sanitized)
        sanitized = re.sub(r"(?i)(org_[a-zA-Z0-9_-]{20,})", "[REDACTED_API_KEY]", sanitized)
        sanitized = re.sub(r"(?i)(re_[a-zA-Z0-9_-]{20,})", "[REDACTED_API_KEY]", sanitized)
        return sanitized

    def generate_document(
        self,
        title: str,
        content: str,
        format: str = "markdown",
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a document file, verify its existence and contents on disk."""
        if not title.strip():
            raise ValueError("Document title cannot be empty.")
        if not content.strip():
            raise ValueError("Document content cannot be empty.")

        ext_map = {
            "markdown": ".md",
            "md": ".md",
            "html": ".html",
            "text": ".txt",
            "txt": ".txt",
            "csv": ".csv",
        }
        fmt = format.lower().strip()
        ext = ext_map.get(fmt, ".md")

        clean_title = self._sanitize_filename(title)
        out_name = filename or f"{clean_title}{ext}"
        if not out_name.endswith(ext):
            out_name = f"{out_name}{ext}"

        safe_filename = self._sanitize_filename(out_name)
        target_path = self.output_dir / safe_filename

        safe_content = self._sanitize_content(content)

        # Write file to disk
        try:
            target_path.write_text(safe_content, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write generated document {target_path}: {e}")
            raise IOError(f"Could not write document to disk: {e}")

        # Real verification check: file must exist, be readable, and have non-zero size
        if not target_path.exists() or not target_path.is_file():
            raise IOError(f"Document generation verification failed: {target_path} does not exist.")

        written_content = target_path.read_text(encoding="utf-8")
        if written_content != safe_content:
            raise IOError("Document verification failed: written content mismatch.")

        file_size = target_path.stat().st_size
        download_url = f"/static/generated_docs/{safe_filename}"

        logger.info(f"Generated document successfully: {target_path} ({file_size} bytes)")
        return {
            "status": "success",
            "title": title,
            "format": fmt,
            "file_name": safe_filename,
            "file_path": str(target_path),
            "download_url": download_url,
            "size_bytes": file_size,
        }
