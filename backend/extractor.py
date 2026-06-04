"""PyMuPDF-backed PDF text extraction & highlight rendering.

Used by:
- Feature 1 (Analysis Terminal): raw-text ground-truth + page→PNG for the LLM prompt
- Feature 3 (Highlighting & Provenance): exact-match highlight annotations
"""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def find_pdf_path(doc_path: str) -> str:
    """Identity passthrough — the upload pipeline stores absolute paths in mongo `documents.file_path`."""
    if not doc_path:
        return ""
    return doc_path if Path(doc_path).exists() else ""


def extract_page_text(pdf_path: str, page_num: int) -> str:
    """Return the deterministic text-layer content of one page (1-indexed). Empty string on failure."""
    if not pdf_path or not Path(pdf_path).exists():
        return ""
    try:
        with fitz.open(pdf_path) as doc:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                return ""
            return doc[idx].get_text() or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_page_text(%s, %s) failed: %s", pdf_path, page_num, exc)
        return ""


def extract_all_page_texts(pdf_path: str) -> dict[int, str]:
    """Extract every page's text. Returns {page_num: text} keyed 1-indexed. Empty dict on failure."""
    out: dict[int, str] = {}
    if not pdf_path or not Path(pdf_path).exists():
        return out
    try:
        with fitz.open(pdf_path) as doc:
            for i in range(len(doc)):
                out[i + 1] = doc[i].get_text() or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_all_page_texts(%s) failed: %s", pdf_path, exc)
    return out


def render_page_b64(pdf_path: str, page_num: int, dpi: int = 110) -> str:
    """Render one page to base64-encoded PNG. Empty string on failure."""
    if not pdf_path or not Path(pdf_path).exists():
        return ""
    try:
        with fitz.open(pdf_path) as doc:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                return ""
            pix = doc[idx].get_pixmap(dpi=dpi)
            return base64.b64encode(pix.tobytes("png")).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_page_b64(%s, %s) failed: %s", pdf_path, page_num, exc)
        return ""


def render_page_with_highlights(
    pdf_path: str, page_num: int, search_terms: list[str]
) -> Tuple[bytes, int]:
    """Render a PDF page to PNG with yellow highlight annotations for matched terms.

    Uses fitz.search_for (text-layer search) per term. Terms not found are silently skipped.
    Returns (png_bytes, total_quad_count); returns (b'', 0) on any failure.
    """
    try:
        with fitz.open(pdf_path) as doc:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                return b"", 0
            page = doc[idx]
            total_quads = 0
            for term in search_terms or []:
                if not term or not term.strip():
                    continue
                try:
                    quads = page.search_for(term)
                    if quads:
                        page.add_highlight_annot(quads)
                        total_quads += len(quads)
                except Exception:
                    pass
            pix = page.get_pixmap(dpi=150)
            return pix.tobytes("png"), total_quads
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_page_with_highlights(%s, %s) failed: %s", pdf_path, page_num, exc)
        return b"", 0


def render_thumbnail(pdf_path: str, page_num: int, search_terms: list[str]) -> bytes:
    """Render a page at 50 DPI with highlight annotations. Returns PNG bytes or b'' on failure."""
    try:
        with fitz.open(pdf_path) as doc:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                return b""
            page = doc[idx]
            for term in search_terms or []:
                if not term or not term.strip():
                    continue
                try:
                    quads = page.search_for(term)
                    if quads:
                        page.add_highlight_annot(quads)
                except Exception:
                    pass
            pix = page.get_pixmap(dpi=50)
            return pix.tobytes("png")
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_thumbnail(%s, %s) failed: %s", pdf_path, page_num, exc)
        return b""


def page_count(pdf_path: str) -> int:
    """Total pages in the PDF; 0 on failure."""
    if not pdf_path or not Path(pdf_path).exists():
        return 0
    try:
        with fitz.open(pdf_path) as doc:
            return len(doc)
    except Exception:
        return 0
