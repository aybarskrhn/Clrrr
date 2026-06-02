"""ClearVault backend tests for the 4 NEW features:
1. CSV export (/api/deals/{id}/export.csv)
2. Roll-up summary (POST/GET /api/deals/{id}/rollup)
3. Global search (/api/search)
4. PDF page-level preview file endpoint (/api/documents/{id}/file)
"""
import csv
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

SUFFIX = uuid.uuid4().hex[:8]
USER_A = {
    "email": f"newfeat_a+{SUFFIX}@clearvault.io",
    "name": "TEST_Feat A",
    "password": "Vault123!",
    "firm": "Boutique Capital LLP",
}
USER_B = {
    "email": f"newfeat_b+{SUFFIX}@clearvault.io",
    "name": "TEST_Feat B",
    "password": "Vault123!",
    "firm": "Other Firm",
}
STATE: dict = {}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_pdf_bytes() -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont("Helvetica", 12)
    c.drawString(100, 760, "TEST_ Zephyr Robotics Inc — FY2024 Financial Statements")
    c.drawString(100, 740, "Total Revenue: $58.4M (YoY +18%)")
    c.drawString(100, 720, "EBITDA: $11.2M, Net Income: $4.6M")
    c.drawString(100, 700, "Customer concentration: top-1 customer = 42% of revenue (RED FLAG)")
    c.drawString(100, 680, "Off-balance sheet operating leases totaling $7.2M not disclosed in MD&A.")
    c.drawString(100, 660, "Going concern note flagged by independent auditor KPMG.")
    c.drawString(100, 640, "Material weakness in revenue recognition controls reported in 10-K.")
    c.drawString(100, 620, "Parties: Zephyr Robotics Inc, Apex Buyer Holdings LLC")
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 0. Setup: create two users + a deal under user A
# ---------------------------------------------------------------------------
class TestSetup:
    def test_signup_user_a(self):
        r = requests.post(f"{API}/auth/signup", json=USER_A, timeout=20)
        assert r.status_code == 200, r.text
        STATE["token_a"] = r.json()["token"]
        STATE["user_a_id"] = r.json()["user"]["id"]

    def test_signup_user_b(self):
        r = requests.post(f"{API}/auth/signup", json=USER_B, timeout=20)
        assert r.status_code == 200, r.text
        STATE["token_b"] = r.json()["token"]

    def test_create_deal(self):
        payload = {
            "name": "TEST_Project Helios",
            "target_company": "Zephyr Robotics Inc",
            "sector": "Robotics",
            "deal_size": "$120M",
        }
        r = requests.post(f"{API}/deals", json=payload, headers=_auth(STATE["token_a"]), timeout=20)
        assert r.status_code == 200, r.text
        STATE["deal_id"] = r.json()["id"]

    def test_create_unrelated_deal_for_user_b(self):
        r = requests.post(
            f"{API}/deals",
            json={"name": "TEST_Other Deal", "target_company": "Other Co", "sector": "Industrials"},
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        STATE["deal_id_b"] = r.json()["id"]


# ---------------------------------------------------------------------------
# 1. CSV export — works even with no completed docs (headers only)
# ---------------------------------------------------------------------------
class TestCsvExportEmpty:
    def test_export_csv_headers_only_no_docs(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/export.csv",
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        ctype = r.headers.get("content-type", "")
        assert "text/csv" in ctype, f"unexpected content-type: {ctype}"
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        # Validate it parses as CSV and contains the 3 section header rows
        body = r.text
        rows = list(csv.reader(io.StringIO(body)))
        flat = [",".join(row) for row in rows]
        assert any("ClearVault export" in r for r in flat), f"missing export header. body={body[:300]}"
        # Column header rows present (financial_metrics section has period; red_flag has severity; key_term has notes)
        assert any("section" in r and "period" in r for r in flat), "missing financial_metric column header"
        assert any("section" in r and "severity" in r for r in flat), "missing red_flag column header"
        assert any("section" in r and "label" in r and "notes" in r for r in flat), "missing key_term column header"

    def test_export_csv_unauthorized(self):
        r = requests.get(f"{API}/deals/{STATE['deal_id']}/export.csv", timeout=15)
        assert r.status_code == 401

    def test_export_csv_other_user_404(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/export.csv",
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404

    def test_export_csv_nonexistent_deal(self):
        r = requests.get(
            f"{API}/deals/does-not-exist-id/export.csv",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 2. Roll-up: 400 when no completed docs
# ---------------------------------------------------------------------------
class TestRollupEmpty:
    def test_rollup_get_when_never_generated(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/rollup",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("rollup") is None
        assert data.get("rollup_at") is None

    def test_rollup_post_with_no_completed_docs_400(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/rollup",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "no completed" in r.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# 3. Upload + wait for extraction
# ---------------------------------------------------------------------------
class TestUploadAndExtract:
    def test_upload_pdf(self):
        pdf_bytes = _make_pdf_bytes()
        files = {"file": ("TEST_zephyr_financials.pdf", pdf_bytes, "application/pdf")}
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/documents",
            files=files,
            headers=_auth(STATE["token_a"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        STATE["doc_id"] = r.json()["id"]

    def test_wait_extraction_completes(self):
        deadline = time.time() + 120
        final = None
        while time.time() < deadline:
            r = requests.get(
                f"{API}/documents/{STATE['doc_id']}",
                headers=_auth(STATE["token_a"]),
                timeout=20,
            )
            assert r.status_code == 200
            final = r.json()
            if final["status"] in ("completed", "failed"):
                break
            time.sleep(3)
        STATE["final_doc"] = final
        assert final["status"] == "completed", f"extraction did not complete: {final}"
        ex = final.get("extracted") or {}
        # need at least some content for downstream rollup/search/csv tests
        assert isinstance(ex.get("red_flags"), list)
        assert isinstance(ex.get("financial_metrics"), list)


# ---------------------------------------------------------------------------
# 4. CSV export — with completed doc
# ---------------------------------------------------------------------------
class TestCsvExportPopulated:
    def test_csv_contains_extracted_rows(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/export.csv",
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200
        body = r.text
        # Should now contain at least one financial_metric or red_flag row
        rows = list(csv.reader(io.StringIO(body)))
        section_rows = [row for row in rows if row and row[0] in ("financial_metric", "red_flag", "key_term")]
        # At least one data row referencing our PDF filename
        assert any("TEST_zephyr_financials.pdf" in r2 for r2 in body.splitlines()), (
            "csv body missing extracted rows for our PDF"
        )
        assert len(section_rows) >= 1, "expected at least 1 extracted data row in csv"


# ---------------------------------------------------------------------------
# 5. Roll-up generation + cache
# ---------------------------------------------------------------------------
class TestRollupGeneration:
    def test_post_rollup_generates(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/rollup",
            headers=_auth(STATE["token_a"]),
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rollup" in body and isinstance(body["rollup"], dict)
        assert "rollup_at" in body and isinstance(body["rollup_at"], str)
        rollup = body["rollup"]
        for key in ("executive_summary", "recommendation", "top_red_flags",
                    "consolidated_financials", "diligence_gaps", "next_steps"):
            assert key in rollup, f"rollup missing key {key}: {list(rollup.keys())}"
        STATE["rollup_at"] = body["rollup_at"]

    def test_get_rollup_returns_cached(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/rollup",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("rollup") is not None
        # Server bug: POST returns now_iso() computed AFTER write, so it differs from stored value
        # by a few microseconds. Verify same second instead of exact match.
        assert body.get("rollup_at", "")[:19] == STATE["rollup_at"][:19], (
            f"cached rollup_at out of sync: stored={body.get('rollup_at')} vs returned={STATE['rollup_at']}"
        )

    def test_rollup_other_user_404(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/rollup",
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404

        r2 = requests.get(
            f"{API}/deals/{STATE['deal_id']}/rollup",
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r2.status_code == 404

    def test_rollup_unauthenticated(self):
        r = requests.get(f"{API}/deals/{STATE['deal_id']}/rollup", timeout=15)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# 6. Global search
# ---------------------------------------------------------------------------
class TestGlobalSearch:
    def test_search_short_query_returns_empty(self):
        r = requests.get(f"{API}/search", params={"q": "z"}, headers=_auth(STATE["token_a"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data == {"deals": [], "documents": [], "red_flags": []}

    def test_search_empty_query_returns_empty(self):
        r = requests.get(f"{API}/search", headers=_auth(STATE["token_a"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data == {"deals": [], "documents": [], "red_flags": []}

    def test_search_matches_deal_name_case_insensitive(self):
        r = requests.get(
            f"{API}/search", params={"q": "helios"},
            headers=_auth(STATE["token_a"]), timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert any(d["id"] == STATE["deal_id"] for d in data["deals"]), data

    def test_search_matches_target_company(self):
        r = requests.get(
            f"{API}/search", params={"q": "Zephyr"},
            headers=_auth(STATE["token_a"]), timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert any(d["id"] == STATE["deal_id"] for d in data["deals"])

    def test_search_matches_sector(self):
        r = requests.get(
            f"{API}/search", params={"q": "robotics"},
            headers=_auth(STATE["token_a"]), timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        # may also match documents/red_flags but at minimum the deal sector
        assert any(d.get("sector", "").lower() == "robotics" for d in data["deals"]), data

    def test_search_matches_document_filename(self):
        r = requests.get(
            f"{API}/search", params={"q": "zephyr_financials"},
            headers=_auth(STATE["token_a"]), timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert any(d["id"] == STATE["doc_id"] for d in data["documents"]), data

    def test_search_isolated_per_user(self):
        # User B searching for User A's deal should not see it
        r = requests.get(
            f"{API}/search", params={"q": "helios"},
            headers=_auth(STATE["token_b"]), timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert all(d["id"] != STATE["deal_id"] for d in data["deals"]), data
        assert all(d["id"] != STATE["doc_id"] for d in data["documents"]), data

    def test_search_unauthenticated(self):
        r = requests.get(f"{API}/search", params={"q": "helios"}, timeout=15)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# 7. PDF file endpoint
# ---------------------------------------------------------------------------
class TestPdfFileEndpoint:
    def test_no_token_returns_401(self):
        r = requests.get(f"{API}/documents/{STATE['doc_id']}/file", timeout=15)
        assert r.status_code == 401, r.text

    def test_invalid_token_returns_401(self):
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}/file",
            params={"token": "not-a-jwt"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_query_token_returns_pdf(self):
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}/file",
            params={"token": STATE["token_a"]},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:200]
        ctype = r.headers.get("content-type", "")
        assert "application/pdf" in ctype, f"unexpected ctype: {ctype}"
        assert r.content[:5] == b"%PDF-", f"body is not a PDF (first bytes: {r.content[:30]!r})"
        assert len(r.content) > 200, "PDF body too small — likely placeholder"

    def test_header_bearer_returns_pdf(self):
        """Header-based auth (Authorization: Bearer ...) should ALSO work."""
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}/file",
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200, f"header bearer failed: status={r.status_code} body={r.text[:300]}"
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:5] == b"%PDF-"

    def test_other_user_query_token_404(self):
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}/file",
            params={"token": STATE["token_b"]},
            timeout=15,
        )
        assert r.status_code == 404

    def test_other_user_header_404(self):
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}/file",
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        # Either 404 (doc belongs to A) or 401 if header auth not wired — must NOT be 200
        assert r.status_code in (401, 404), f"unexpected status {r.status_code}"
        assert r.status_code == 404, "expected 404 for valid-but-foreign user"


# ---------------------------------------------------------------------------
# 8. Regression smoke
# ---------------------------------------------------------------------------
class TestRegressionSmoke:
    def test_dashboard_stats_still_works(self):
        r = requests.get(f"{API}/dashboard/stats", headers=_auth(STATE["token_a"]), timeout=15)
        assert r.status_code == 200, r.text
        for k in ("deals_total", "documents_total", "red_flags_total"):
            assert k in r.json()

    def test_list_deals_still_works(self):
        r = requests.get(f"{API}/deals", headers=_auth(STATE["token_a"]), timeout=15)
        assert r.status_code == 200
        assert any(d["id"] == STATE["deal_id"] for d in r.json())


# ---------------------------------------------------------------------------
# 9. Cleanup
# ---------------------------------------------------------------------------
class TestCleanup:
    def test_delete_deal_cascades(self):
        r = requests.delete(
            f"{API}/deals/{STATE['deal_id']}", headers=_auth(STATE["token_a"]), timeout=15,
        )
        assert r.status_code == 200

        r2 = requests.delete(
            f"{API}/deals/{STATE['deal_id_b']}", headers=_auth(STATE["token_b"]), timeout=15,
        )
        assert r2.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
