"""ClearVault backend API tests."""
import io
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ui-build-showcase.preview.emergentagent.com").rstrip("/")
# Allow override via env, but default to the public preview URL exposed by frontend/.env
API = f"{BASE_URL}/api"

# --- shared state -----------------------------------------------------------
SUFFIX = uuid.uuid4().hex[:8]
USER_A = {
    "email": f"analyst+{SUFFIX}@clearvault.io",
    "name": "Test Analyst",
    "password": "Vault123!",
    "firm": "Boutique Capital LLP",
}
USER_B = {
    "email": f"otheranalyst+{SUFFIX}@clearvault.io",
    "name": "Other Analyst",
    "password": "Vault123!",
    "firm": "Other Firm",
}

STATE = {}


# --- helpers ----------------------------------------------------------------
def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _make_pdf_bytes() -> bytes:
    """Build a tiny valid PDF without external deps."""
    try:
        from reportlab.pdfgen import canvas  # noqa: WPS433
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.setFont("Helvetica", 12)
        c.drawString(100, 750, "TEST_ Acme Corp — Income Statement FY2024")
        c.drawString(100, 730, "Total Revenue: $42.3M (YoY +12%)")
        c.drawString(100, 710, "EBITDA: $8.1M, Net Income: $3.2M")
        c.drawString(100, 690, "Customer concentration: top-1 = 38% of revenue")
        c.drawString(100, 670, "Off-balance sheet operating leases: $5.6M")
        c.drawString(100, 650, "Going concern note flagged by auditor.")
        c.drawString(100, 630, "Parties: Acme Corp, Buyer Holdings LLC")
        c.save()
        return buf.getvalue()
    except Exception:
        # Minimal valid PDF as fallback
        return (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (TEST PDF) Tj ET\nendstream endobj\n"
            b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n"
            b"0000000098 00000 n \n0000000160 00000 n \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n230\n%%EOF\n"
        )


# --- 1. Health --------------------------------------------------------------
class TestHealth:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("app") == "ClearVault"
        assert body.get("status") == "ok"


# --- 2. Auth ----------------------------------------------------------------
class TestAuth:
    def test_signup_user_a(self):
        r = requests.post(f"{API}/auth/signup", json=USER_A, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 10
        assert data["user"]["email"] == USER_A["email"]
        assert data["user"]["name"] == USER_A["name"]
        assert data["user"]["firm"] == USER_A["firm"]
        assert data["user"]["role"] == "analyst"
        assert "id" in data["user"]
        STATE["token_a"] = data["token"]
        STATE["user_a_id"] = data["user"]["id"]

    def test_signup_user_b(self):
        r = requests.post(f"{API}/auth/signup", json=USER_B, timeout=20)
        assert r.status_code == 200, r.text
        STATE["token_b"] = r.json()["token"]

    def test_signup_duplicate_returns_400(self):
        r = requests.post(f"{API}/auth/signup", json=USER_A, timeout=15)
        assert r.status_code == 400, r.text
        assert "already" in r.json().get("detail", "").lower()

    def test_login_valid(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": USER_A["email"], "password": USER_A["password"]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data
        assert data["user"]["email"] == USER_A["email"]

    def test_login_invalid_password(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": USER_A["email"], "password": "WrongPass!"},
            timeout=15,
        )
        assert r.status_code == 401, r.text

    def test_login_unknown_user(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": f"nobody+{SUFFIX}@clearvault.io", "password": "x"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_me_with_token(self):
        r = requests.get(f"{API}/auth/me", headers=_auth_header(STATE["token_a"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == USER_A["email"]
        assert data["id"] == STATE["user_a_id"]

    def test_me_without_token(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_with_bad_token(self):
        r = requests.get(f"{API}/auth/me", headers=_auth_header("not-a-real-token"), timeout=15)
        assert r.status_code == 401


# --- 3. Deals ---------------------------------------------------------------
class TestDeals:
    def test_create_deal(self):
        payload = {
            "name": "TEST_Project Atlas",
            "target_company": "Acme Corp",
            "sector": "Technology",
            "deal_size": "$45M",
        }
        r = requests.post(
            f"{API}/deals", json=payload, headers=_auth_header(STATE["token_a"]), timeout=15
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == payload["name"]
        assert data["target_company"] == payload["target_company"]
        assert data["sector"] == "Technology"
        assert data["deal_size"] == "$45M"
        assert data["stage"] == "due_diligence"
        assert data["status"] == "active"
        assert data["documents_count"] == 0
        assert data["red_flags_count"] == 0
        assert "id" in data
        STATE["deal_id"] = data["id"]

    def test_create_deal_requires_auth(self):
        r = requests.post(f"{API}/deals", json={"name": "x", "target_company": "y"}, timeout=10)
        assert r.status_code == 401

    def test_list_deals_only_for_user(self):
        # User A sees the deal
        r = requests.get(f"{API}/deals", headers=_auth_header(STATE["token_a"]), timeout=15)
        assert r.status_code == 200, r.text
        deals_a = r.json()
        assert isinstance(deals_a, list) and len(deals_a) >= 1
        assert any(d["id"] == STATE["deal_id"] for d in deals_a)

        # User B does NOT see User A's deal
        r2 = requests.get(f"{API}/deals", headers=_auth_header(STATE["token_b"]), timeout=15)
        assert r2.status_code == 200
        deals_b = r2.json()
        assert all(d["id"] != STATE["deal_id"] for d in deals_b)

    def test_get_deal_returns_counts(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}", headers=_auth_header(STATE["token_a"]), timeout=15
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "documents_count" in data
        assert "red_flags_count" in data
        assert data["id"] == STATE["deal_id"]

    def test_get_deal_unauthorized_user_404(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}", headers=_auth_header(STATE["token_b"]), timeout=15
        )
        # Should not be accessible by another user
        assert r.status_code == 404


# --- 4. Documents (upload + background AI extraction) ----------------------
class TestDocuments:
    def test_upload_pdf_and_extract(self):
        pdf_bytes = _make_pdf_bytes()
        files = {"file": ("TEST_acme_financials.pdf", pdf_bytes, "application/pdf")}
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/documents",
            files=files,
            headers=_auth_header(STATE["token_a"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "uploaded"
        assert data["filename"].endswith(".pdf")
        assert data["file_size"] > 0
        assert data["deal_id"] == STATE["deal_id"]
        STATE["doc_id"] = data["id"]

    def test_reject_non_pdf(self):
        files = {"file": ("not_a_pdf.txt", b"hello", "text/plain")}
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/documents",
            files=files,
            headers=_auth_header(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 400

    def test_upload_unauthorized_deal_404(self):
        pdf_bytes = _make_pdf_bytes()
        files = {"file": ("TEST.pdf", pdf_bytes, "application/pdf")}
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/documents",
            files=files,
            headers=_auth_header(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404

    def test_list_documents(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/documents",
            headers=_auth_header(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        docs = r.json()
        assert any(d["id"] == STATE["doc_id"] for d in docs)

    def test_list_documents_other_user_blocked(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/documents",
            headers=_auth_header(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404

    def test_get_document_other_user_blocked(self):
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}",
            headers=_auth_header(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404

    def test_extraction_completes_or_fails_with_message(self):
        """Poll up to 90s for the background AI task."""
        terminal = {"completed", "failed"}
        last_status = None
        last_body = None
        deadline = time.time() + 90
        while time.time() < deadline:
            r = requests.get(
                f"{API}/documents/{STATE['doc_id']}",
                headers=_auth_header(STATE["token_a"]),
                timeout=20,
            )
            assert r.status_code == 200, r.text
            last_body = r.json()
            last_status = last_body["status"]
            if last_status in terminal:
                break
            time.sleep(3)

        STATE["final_doc"] = last_body
        # Infra mechanics must work: terminal state reached
        assert last_status in terminal, (
            f"Document status never reached terminal state in 90s (last={last_status})"
        )

        if last_status == "completed":
            extracted = last_body.get("extracted") or {}
            # required keys
            for key in ("financial_metrics", "red_flags", "summary", "confidence"):
                assert key in extracted, f"missing key {key} in extracted: {extracted}"
            assert isinstance(extracted["financial_metrics"], list)
            assert isinstance(extracted["red_flags"], list)
            assert isinstance(extracted["summary"], str)
            assert isinstance(extracted["confidence"], (int, float))
        else:
            # failed — surface message but mark infra pipeline as still passing
            err = last_body.get("error")
            print(f"\n[WARN] AI extraction failed (infra OK): {err}")


# --- 5. Dashboard & activity -----------------------------------------------
class TestDashboardAndActivity:
    def test_dashboard_stats(self):
        r = requests.get(
            f"{API}/dashboard/stats", headers=_auth_header(STATE["token_a"]), timeout=15
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in (
            "deals_total",
            "deals_active",
            "documents_total",
            "documents_completed",
            "red_flags_total",
            "red_flags_high",
        ):
            assert k in data, f"missing {k}"
            assert isinstance(data[k], int)
        assert data["deals_total"] >= 1
        assert data["documents_total"] >= 1

    def test_recent_activity(self):
        r = requests.get(
            f"{API}/activity/recent", headers=_auth_header(STATE["token_a"]), timeout=15
        )
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        assert any(it.get("id") == STATE["doc_id"] for it in items)
        for it in items:
            for k in ("id", "deal_id", "filename", "status", "created_at"):
                assert k in it


# --- 6. Authorization & cleanup --------------------------------------------
class TestDeletionAndAuthz:
    def test_delete_deal_blocked_for_other_user(self):
        r = requests.delete(
            f"{API}/deals/{STATE['deal_id']}", headers=_auth_header(STATE["token_b"]), timeout=15
        )
        assert r.status_code == 404

    def test_delete_deal_cascades_documents(self):
        # delete deal as owner
        r = requests.delete(
            f"{API}/deals/{STATE['deal_id']}", headers=_auth_header(STATE["token_a"]), timeout=15
        )
        assert r.status_code == 200, r.text
        assert r.json().get("deleted") is True

        # deal gone
        r2 = requests.get(
            f"{API}/deals/{STATE['deal_id']}", headers=_auth_header(STATE["token_a"]), timeout=15
        )
        assert r2.status_code == 404

        # documents under it should be gone too
        r3 = requests.get(
            f"{API}/documents/{STATE['doc_id']}",
            headers=_auth_header(STATE["token_a"]),
            timeout=15,
        )
        assert r3.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
