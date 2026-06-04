"""Iteration 6 — Analysis Terminal · CSV Export · Highlighting & Provenance.

Tests the 5 new endpoints registered under ANALYZE_ROUTER plus unit tests for
provenance._numeric_variants. Live OpenRouter calls are gated to <=2 per run to
keep costs low; if the upstream rate-limits we mark a flake but don't fail
the suite.
"""
from __future__ import annotations

import base64
import io
import os
import uuid
from typing import Optional

import pytest
import requests

from provenance import _numeric_variants  # noqa: E402

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://ui-build-showcase.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

ANALYZE_TIMEOUT = 90  # OpenRouter takes 8-15s, allow margin

SUFFIX = uuid.uuid4().hex[:8]
USER_A = {
    "email": f"i6a_{SUFFIX}@clearvault.io",
    "name": "Iter6 A",
    "password": "Vault123!",
    "firm": "I6 Capital",
}
USER_B = {
    "email": f"i6b_{SUFFIX}@clearvault.io",
    "name": "Iter6 B",
    "password": "Vault123!",
    "firm": "I6 Other",
}

STATE: dict = {}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_text_pdf() -> bytes:
    """A text-layer PDF with values that we will query via /api/analyze."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont("Helvetica", 12)
    c.drawString(100, 760, "TEST_ Northwind Industries — Depreciation Schedule FY2025")
    c.drawString(100, 740, "Equipment depreciation: $4.2M")
    c.drawString(100, 720, "Software depreciation: $3.8M")
    c.drawString(100, 700, "Total depreciation: $8.0M")
    c.drawString(100, 680, "Parties: Northwind Industries, Acquirer Holdings LP")
    c.save()
    return buf.getvalue()


def _make_image_only_pdf() -> bytes:
    """An image-only PDF (no text layer). reportlab drawImage with a small PNG."""
    from reportlab.pdfgen import canvas

    # Tiny 1x1 black PNG embedded into a PDF page — produces empty text layer
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    # Use a small in-memory PNG via reportlab's drawImage with an ImageReader of bytes
    from reportlab.lib.utils import ImageReader

    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    img = ImageReader(io.BytesIO(base64.b64decode(png_b64)))
    c.drawImage(img, 100, 600, width=400, height=200)
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def bootstrap():
    # Sign up both users
    ra = requests.post(f"{API}/auth/signup", json=USER_A, timeout=20)
    assert ra.status_code == 200, ra.text
    STATE["token_a"] = ra.json()["token"]

    rb = requests.post(f"{API}/auth/signup", json=USER_B, timeout=20)
    assert rb.status_code == 200, rb.text
    STATE["token_b"] = rb.json()["token"]

    # User A creates a deal
    deal_payload = {
        "name": "TEST_ I6 Northwind",
        "target_company": "Northwind Industries",
        "sector": "Industrial",
        "deal_size": "$120M",
    }
    rd = requests.post(
        f"{API}/deals", json=deal_payload, headers=_auth(STATE["token_a"]), timeout=20
    )
    assert rd.status_code == 200, rd.text
    STATE["deal_id"] = rd.json()["id"]

    # Upload text-PDF
    files = {"file": ("TEST_northwind_text.pdf", _make_text_pdf(), "application/pdf")}
    ru = requests.post(
        f"{API}/deals/{STATE['deal_id']}/documents",
        files=files,
        headers=_auth(STATE["token_a"]),
        timeout=30,
    )
    assert ru.status_code == 200, ru.text
    STATE["text_doc_id"] = ru.json()["id"]

    # Upload image-only PDF
    files = {"file": ("TEST_northwind_image.pdf", _make_image_only_pdf(), "application/pdf")}
    ri = requests.post(
        f"{API}/deals/{STATE['deal_id']}/documents",
        files=files,
        headers=_auth(STATE["token_a"]),
        timeout=30,
    )
    assert ri.status_code == 200, ri.text
    STATE["image_doc_id"] = ri.json()["id"]

    # Pre-run one live /api/analyze for the text doc; reused by many downstream tests
    body = {
        "question": "Show me the depreciation breakdown for equipment and software.",
        "doc_scope": [STATE["text_doc_id"]],
        "n_results": 2,
    }
    r = requests.post(
        f"{API}/analyze", json=body, headers=_auth(STATE["token_a"]), timeout=ANALYZE_TIMEOUT
    )
    STATE["analyze_text_status"] = r.status_code
    STATE["analyze_text_body"] = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

    yield

    # Best-effort cleanup — delete uploaded docs + deal
    for did in (STATE.get("text_doc_id"), STATE.get("image_doc_id")):
        if did:
            requests.delete(f"{API}/documents/{did}", headers=_auth(STATE["token_a"]), timeout=15)
    if STATE.get("deal_id"):
        requests.delete(
            f"{API}/deals/{STATE['deal_id']}", headers=_auth(STATE["token_a"]), timeout=15
        )


# ---------------------------------------------------------------------------
# Unit tests — provenance._numeric_variants
# ---------------------------------------------------------------------------
class TestNumericVariants:
    def test_currency_strip(self):
        v = _numeric_variants("$4.2M")
        assert "$4.2M" in v
        assert "4.2M" in v

    def test_comma_strip(self):
        v = _numeric_variants("$4,200,000")
        assert "4,200,000" in v
        assert "4200000" in v

    def test_parens_to_minus(self):
        v = _numeric_variants("($1,234)")
        assert "-1,234" in v or "-1234" in v
        assert "(1,234)" in v or "(1234)" in v

    def test_trailing_zeros(self):
        v = _numeric_variants("$5.00")
        assert "5" in v or "5.0" in v or "5.00" in v
        # original always preserved
        assert "$5.00" in v

    def test_empty(self):
        assert _numeric_variants("") == []
        assert _numeric_variants("   ") == []


# ---------------------------------------------------------------------------
# /api/analyze
# ---------------------------------------------------------------------------
class TestAnalyzeValidation:
    def test_unauth_401(self):
        r = requests.post(
            f"{API}/analyze",
            json={"question": "x", "doc_scope": [STATE["text_doc_id"]]},
            timeout=15,
        )
        assert r.status_code in (401, 403), r.text

    def test_empty_question_400(self):
        r = requests.post(
            f"{API}/analyze",
            json={"question": "   ", "doc_scope": [STATE["text_doc_id"]]},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_empty_doc_scope_400(self):
        r = requests.post(
            f"{API}/analyze",
            json={"question": "anything", "doc_scope": []},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_unknown_doc_422(self):
        r = requests.post(
            f"{API}/analyze",
            json={"question": "anything", "doc_scope": ["does-not-exist-" + uuid.uuid4().hex]},
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 422, r.text
        body = r.json()
        assert "No relevant pages found" in (body.get("error") or "")

    def test_cross_user_isolation_422(self):
        r = requests.post(
            f"{API}/analyze",
            json={"question": "Equipment depreciation", "doc_scope": [STATE["text_doc_id"]]},
            headers=_auth(STATE["token_b"]),
            timeout=20,
        )
        assert r.status_code == 422, r.text
        assert "No relevant pages found" in (r.json().get("error") or "")


class TestAnalyzeContract:
    """Validate the live OpenRouter response payload from the bootstrap call."""

    def test_text_pdf_payload_shape(self):
        status = STATE.get("analyze_text_status")
        body = STATE.get("analyze_text_body", {})
        if status == 429 or "rate" in str(body).lower():
            pytest.skip(f"OpenRouter rate-limited (status={status})")
        if status == 502:
            pytest.skip(f"OpenRouter upstream failed: {body}")
        assert status == 200, f"Unexpected status={status} body={body}"

        # Contract: all keys present
        for k in (
            "answer",
            "cited_pages",
            "row_pages",
            "row_docs",
            "row_reasoning",
            "highlight_terms_by_page",
            "provenance_cited_pages",
            "first_chunk_page",
            "is_verified",
        ):
            assert k in body, f"missing key {k}"

        assert isinstance(body["answer"], str) and body["answer"].strip()
        assert isinstance(body["cited_pages"], list)
        assert all(isinstance(p, int) for p in body["cited_pages"])
        assert isinstance(body["row_pages"], list)
        assert isinstance(body["highlight_terms_by_page"], dict)
        # JSON serialization stringifies dict int keys
        for k in body["highlight_terms_by_page"].keys():
            assert isinstance(k, str), f"highlight_terms_by_page key {k!r} must be string"
        assert isinstance(body["provenance_cited_pages"], list)
        assert body["first_chunk_page"] is None or isinstance(body["first_chunk_page"], int)
        assert isinstance(body["is_verified"], bool)

    def test_text_pdf_is_verified_true(self):
        body = STATE.get("analyze_text_body", {})
        if STATE.get("analyze_text_status") != 200:
            pytest.skip("upstream OpenRouter call did not return 200")
        assert body.get("is_verified") is True, f"is_verified must be True for text PDF; got {body.get('is_verified')}"

    def test_text_pdf_cited_pages_present(self):
        body = STATE.get("analyze_text_body", {})
        if STATE.get("analyze_text_status") != 200:
            pytest.skip("upstream OpenRouter call did not return 200")
        # cited_pages may legitimately be empty if the LLM didn't emit citation markers,
        # but provenance_cited_pages should have at least page 1 since the table cells match.
        prov = body.get("provenance_cited_pages") or []
        assert 1 in prov or any(p == 1 for p in (body.get("row_pages") or [])), (
            f"expected page 1 in provenance/row_pages; got prov={prov} row_pages={body.get('row_pages')}"
        )

    def test_image_pdf_is_verified_false(self):
        """One additional live call — image-only PDF must produce is_verified=False."""
        body = {
            "question": "List all depreciation line items in the schedule.",
            "doc_scope": [STATE["image_doc_id"]],
            "n_results": 2,
        }
        r = requests.post(
            f"{API}/analyze", json=body, headers=_auth(STATE["token_a"]), timeout=ANALYZE_TIMEOUT
        )
        if r.status_code == 422:
            # CPU retrieval found no relevant tokens in the empty text layer — that's
            # the deterministic behaviour for image-only PDFs and proves no-fabrication.
            assert "No relevant pages found" in (r.json().get("error") or "")
            return
        if r.status_code in (429, 502):
            pytest.skip(f"upstream error {r.status_code}: {r.text}")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["is_verified"] is False
        # If a table was produced, numeric cells should carry the unverified marker
        if "|" in out.get("answer", ""):
            assert "⚠️ unverified" in out["answer"]


# ---------------------------------------------------------------------------
# /api/export-table
# ---------------------------------------------------------------------------
class TestExportTable:
    def test_no_table_400(self):
        r = requests.post(
            f"{API}/export-table",
            json={"answer": "Just a plain text answer with no markdown table."},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_basic_table_export(self):
        answer_md = (
            "## Direct Answer\nHere is the breakdown.\n\n"
            "| Item | Amount |\n|---|---|\n"
            "| Equipment | $4.2M |\n"
            "| Software | $3.8M |\n"
            "| Total | $8.0M |\n"
        )
        body = {
            "answer": answer_md,
            "row_pages": [1, 1, None],
            "row_docs": ["doc1", "doc1", None],
            "row_reasoning": ["from page 1", "from page 1", "computed total"],
        }
        r = requests.post(
            f"{API}/export-table", json=body, headers=_auth(STATE["token_a"]), timeout=15
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert "csv_data" in out and "filename" in out
        assert "Source Doc,Source Page,Causality / Reasoning" in out["csv_data"]
        assert "Unresolved" in out["csv_data"]
        assert out["has_unresolved"] is True
        assert isinstance(out["row_count"], int) and out["row_count"] >= 3
        assert out["filename"].startswith("table_p1") and out["filename"].endswith(".csv")

    def test_table_no_provenance(self):
        answer_md = (
            "| Metric | Value |\n|---|---|\n| Revenue | $10M |\n"
        )
        r = requests.post(
            f"{API}/export-table",
            json={"answer": answer_md},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        # No provenance columns appended when row_pages/docs/reasoning are all absent
        assert "Source Doc" not in out["csv_data"]
        assert out["has_unresolved"] is False
        assert out["filename"] == "table.csv"


# ---------------------------------------------------------------------------
# /api/highlight-page
# ---------------------------------------------------------------------------
class TestHighlightPage:
    def test_matching_terms(self):
        r = requests.post(
            f"{API}/highlight-page",
            json={
                "doc_name": STATE["text_doc_id"],
                "page_num": 1,
                "search_terms": ["Equipment", "$4.2M"],
            },
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["page_png_b64"]
        assert len(out["page_png_b64"]) > 100
        # PNG bytes round-trip
        png_bytes = base64.b64decode(out["page_png_b64"])
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert out["quad_count"] >= 1

    def test_no_match_returns_page(self):
        r = requests.post(
            f"{API}/highlight-page",
            json={
                "doc_name": STATE["text_doc_id"],
                "page_num": 1,
                "search_terms": ["ZZZ_NOT_PRESENT_TERM"],
            },
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["quad_count"] == 0
        assert out["page_png_b64"]  # page still rendered

    def test_cross_user_404(self):
        r = requests.post(
            f"{API}/highlight-page",
            json={
                "doc_name": STATE["text_doc_id"],
                "page_num": 1,
                "search_terms": ["Equipment"],
            },
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# /api/highlight-thumbnail
# ---------------------------------------------------------------------------
class TestHighlightThumbnail:
    def test_thumbnail_returns(self):
        r = requests.post(
            f"{API}/highlight-thumbnail",
            json={
                "doc_name": STATE["text_doc_id"],
                "page_num": 1,
                "search_terms": ["Equipment"],
            },
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["thumbnail_png_b64"]
        assert len(out["thumbnail_png_b64"]) > 100
        assert base64.b64decode(out["thumbnail_png_b64"])[:8] == b"\x89PNG\r\n\x1a\n"

    def test_thumbnail_cross_user_404(self):
        r = requests.post(
            f"{API}/highlight-thumbnail",
            json={"doc_name": STATE["text_doc_id"], "page_num": 1, "search_terms": []},
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/page-text
# ---------------------------------------------------------------------------
class TestPageText:
    def test_text_pdf(self):
        r = requests.post(
            f"{API}/page-text",
            json={"doc_name": STATE["text_doc_id"], "page_num": 1},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["has_text_layer"] is True
        assert "Equipment depreciation" in out["text"]
        assert out["page_count"] == 1

    def test_image_pdf(self):
        r = requests.post(
            f"{API}/page-text",
            json={"doc_name": STATE["image_doc_id"], "page_num": 1},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["has_text_layer"] is False
        assert out["page_count"] == 1

    def test_cross_user_404(self):
        r = requests.post(
            f"{API}/page-text",
            json={"doc_name": STATE["text_doc_id"], "page_num": 1},
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Numeric-variant matching end-to-end via the live response
# ---------------------------------------------------------------------------
class TestNumericVariantMatching:
    def test_dollar_m_variant_matched_in_provenance(self):
        body = STATE.get("analyze_text_body", {})
        if STATE.get("analyze_text_status") != 200:
            pytest.skip("upstream OpenRouter call did not return 200")
        ht = body.get("highlight_terms_by_page") or {}
        # Page 1 highlights should include at least one numeric variant from the PDF
        terms_on_p1 = ht.get("1") or []
        joined = " ".join(terms_on_p1).lower()
        assert "4.2" in joined or "3.8" in joined or "equipment" in joined or "software" in joined, (
            f"expected a numeric variant or label in highlight_terms_by_page['1']; got {terms_on_p1}"
        )
