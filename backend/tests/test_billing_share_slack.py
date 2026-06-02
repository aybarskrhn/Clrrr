"""ClearVault backend tests for the 3 NEW feature areas:
1. Stripe Checkout (packages, session, status, webhook smoke)
2. Public IC-memo share (create/get/view/revoke + cross-user)
3. Settings PATCH (slack_webhook_url validation, name, firm)
"""
import io
import os
import re
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

SUFFIX = uuid.uuid4().hex[:8]
USER_A = {
    "email": f"billshare_a+{SUFFIX}@clearvault.io",
    "name": "TEST_Bill A",
    "password": "Vault123!",
    "firm": "Boutique Capital LLP",
}
USER_B = {
    "email": f"billshare_b+{SUFFIX}@clearvault.io",
    "name": "TEST_Bill B",
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
    c.drawString(100, 740, "Total Revenue: $58.4M, EBITDA: $11.2M, Net Income: $4.6M")
    c.drawString(100, 720, "Customer concentration: top-1 customer = 42% of revenue (RED FLAG)")
    c.drawString(100, 700, "Off-balance sheet operating leases totaling $7.2M not disclosed.")
    c.drawString(100, 680, "Going concern note flagged by independent auditor KPMG.")
    c.drawString(100, 660, "Material weakness in revenue recognition controls reported in 10-K.")
    c.save()
    return buf.getvalue()


# ---------- 0. Setup ----------
class TestSetup:
    def test_signup_user_a(self):
        r = requests.post(f"{API}/auth/signup", json=USER_A, timeout=20)
        assert r.status_code == 200, r.text
        STATE["token_a"] = r.json()["token"]
        STATE["user_a_id"] = r.json()["user"]["id"]
        # default plan should be "trial"
        assert r.json()["user"]["plan"] == "trial"
        assert r.json()["user"].get("slack_webhook_url") in (None, "")

    def test_signup_user_b(self):
        r = requests.post(f"{API}/auth/signup", json=USER_B, timeout=20)
        assert r.status_code == 200, r.text
        STATE["token_b"] = r.json()["token"]
        STATE["user_b_id"] = r.json()["user"]["id"]

    def test_create_deal_under_a(self):
        r = requests.post(
            f"{API}/deals",
            json={
                "name": "TEST_Share Helios",
                "target_company": "Zephyr Robotics Inc",
                "sector": "Robotics",
                "deal_size": "$120M",
            },
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        STATE["deal_id"] = r.json()["id"]

    def test_create_deal_under_b(self):
        r = requests.post(
            f"{API}/deals",
            json={"name": "TEST_B-Deal", "target_company": "Other Co"},
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        STATE["deal_id_b"] = r.json()["id"]


# ---------- 1. Stripe — packages ----------
class TestPackages:
    def test_list_packages_shape(self):
        r = requests.get(f"{API}/payments/packages", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "packages" in data
        ids = {p["id"]: p for p in data["packages"]}
        assert "desk_monthly" in ids and "desk_annual" in ids
        m = ids["desk_monthly"]
        a = ids["desk_annual"]
        assert m["amount"] == 890.0
        assert isinstance(m["amount"], float)
        assert m["currency"] == "usd"
        assert m["plan"] == "desk"
        assert "label" in m and m["label"]
        assert a["amount"] == 8500.0
        assert a["plan"] == "desk"


# ---------- 2. Stripe — checkout session ----------
class TestCheckoutSession:
    def test_unknown_package_400(self):
        r = requests.post(
            f"{API}/payments/checkout/session",
            json={"package_id": "bogus_pkg", "origin_url": "https://app.example.com"},
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 400, r.text

    def test_create_checkout_session_monthly(self):
        r = requests.post(
            f"{API}/payments/checkout/session",
            json={"package_id": "desk_monthly", "origin_url": "https://app.example.com"},
            headers=_auth(STATE["token_a"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "url" in data and "session_id" in data
        assert data["url"].startswith("https://checkout.stripe.com/"), data["url"]
        assert re.match(r"^cs_test_[A-Za-z0-9]+$", data["session_id"]), data["session_id"]
        STATE["session_id"] = data["session_id"]

    def test_unauthenticated_blocked(self):
        r = requests.post(
            f"{API}/payments/checkout/session",
            json={"package_id": "desk_monthly", "origin_url": "https://app.example.com"},
            timeout=15,
        )
        assert r.status_code == 401


# ---------- 3. Stripe — status ----------
class TestCheckoutStatus:
    def test_status_for_own_session(self):
        sid = STATE["session_id"]
        r = requests.get(
            f"{API}/payments/checkout/status/{sid}",
            headers=_auth(STATE["token_a"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("payment_status", "status", "amount_total", "currency", "plan"):
            assert k in data, f"missing key {k}: {data}"
        # Freshly created session: not paid
        assert data["payment_status"] in ("unpaid", "open", "no_payment_required"), data
        assert data["plan"] == "desk"
        assert data["currency"].lower() == "usd"

    def test_status_other_user_404(self):
        r = requests.get(
            f"{API}/payments/checkout/status/{STATE['session_id']}",
            headers=_auth(STATE["token_b"]),
            timeout=20,
        )
        assert r.status_code == 404

    def test_status_unknown_session_404(self):
        r = requests.get(
            f"{API}/payments/checkout/status/cs_test_does_not_exist_xyz",
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 404


# ---------- 4. Stripe — webhook smoke ----------
class TestStripeWebhook:
    def test_invalid_webhook_returns_400_not_500(self):
        r = requests.post(
            f"{API}/webhook/stripe",
            data=b"{}",
            headers={"Stripe-Signature": "bogus"},
            timeout=15,
        )
        # Must not crash. 400 expected.
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_missing_signature_returns_400(self):
        r = requests.post(f"{API}/webhook/stripe", data=b"", timeout=15)
        assert r.status_code == 400, r.text[:300]


# ---------- 5. Settings PATCH ----------
class TestSettings:
    def test_set_valid_slack_webhook(self):
        url = "https://hooks.slack.com/services/T000/B000/abcDEFghiJKLmnoPQR"
        r = requests.patch(
            f"{API}/auth/settings",
            json={"slack_webhook_url": url, "name": "TEST_Bill A2", "firm": "New Firm"},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["slack_webhook_url"] == url
        assert data["name"] == "TEST_Bill A2"
        assert data["firm"] == "New Firm"

    def test_persisted_via_me(self):
        r = requests.get(f"{API}/auth/me", headers=_auth(STATE["token_a"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["slack_webhook_url"].startswith("https://hooks.slack.com/")

    def test_reject_non_slack_url(self):
        r = requests.patch(
            f"{API}/auth/settings",
            json={"slack_webhook_url": "https://evil.example.com/hook"},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_empty_string_clears(self):
        r = requests.patch(
            f"{API}/auth/settings",
            json={"slack_webhook_url": ""},
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("slack_webhook_url") in (None, "")

    def test_unauthenticated_blocked(self):
        r = requests.patch(f"{API}/auth/settings", json={"name": "x"}, timeout=15)
        assert r.status_code == 401


# ---------- 6. Upload + extraction + rollup (prereq for share) ----------
class TestUploadAndRollup:
    def test_upload_pdf(self):
        pdf = _make_pdf_bytes()
        files = {"file": ("TEST_share_zephyr.pdf", pdf, "application/pdf")}
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/documents",
            files=files,
            headers=_auth(STATE["token_a"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        STATE["doc_id"] = r.json()["id"]

    def test_wait_extraction(self):
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
        assert final["status"] == "completed", f"extraction did not finish: {final}"

    def test_share_before_rollup_400(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_generate_rollup(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/rollup",
            headers=_auth(STATE["token_a"]),
            timeout=90,
        )
        assert r.status_code == 200, r.text
        assert "rollup" in r.json()


# ---------- 7. Public share lifecycle ----------
class TestShareLifecycle:
    def test_get_share_when_none(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("token") is None

    def test_create_share(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("token") and isinstance(data["token"], str)
        assert data["url_path"] == f"/share/{data['token']}"
        assert data["view_count"] == 0
        assert data.get("created_at")
        STATE["share_token"] = data["token"]

    def test_create_share_idempotent(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["token"] == STATE["share_token"], "share must be idempotent"

    def test_get_share_after_create(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["token"] == STATE["share_token"]

    def test_view_share_no_auth_required(self):
        # Explicitly no auth header
        r = requests.get(f"{API}/share/{STATE['share_token']}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "deal" in data and "rollup" in data
        deal = data["deal"]
        assert set(deal.keys()) >= {"name", "target_company", "sector", "deal_size"}
        assert deal["name"] == "TEST_Share Helios"
        assert deal["target_company"] == "Zephyr Robotics Inc"
        assert isinstance(data["rollup"], dict)
        assert data["view_count"] >= 1
        assert "rollup_at" in data and "shared_at" in data

    def test_view_count_increments(self):
        r1 = requests.get(f"{API}/share/{STATE['share_token']}", timeout=15)
        c1 = r1.json()["view_count"]
        r2 = requests.get(f"{API}/share/{STATE['share_token']}", timeout=15)
        c2 = r2.json()["view_count"]
        assert c2 == c1 + 1, f"view_count did not increment: {c1} -> {c2}"

    def test_view_unknown_token_404(self):
        r = requests.get(f"{API}/share/unknown_token_xyz_404", timeout=15)
        assert r.status_code == 404

    def test_cross_user_get_share_returns_none(self):
        # User B querying THEIR OWN /share for deal_id_b returns null token (not 404)
        r = requests.get(
            f"{API}/deals/{STATE['deal_id_b']}/share",
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("token") is None

    def test_cross_user_revoke_404(self):
        # User B tries to revoke User A's deal share — must 404
        r = requests.delete(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_b"]),
            timeout=15,
        )
        assert r.status_code == 404, r.text

    def test_share_token_still_works_after_cross_user_revoke_attempt(self):
        r = requests.get(f"{API}/share/{STATE['share_token']}", timeout=15)
        assert r.status_code == 200, "cross-user revoke should NOT have affected share"

    def test_revoke_by_owner(self):
        r = requests.delete(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text

    def test_view_after_revoke_404(self):
        r = requests.get(f"{API}/share/{STATE['share_token']}", timeout=15)
        assert r.status_code == 404, r.text

    def test_create_new_share_after_revoke(self):
        r = requests.post(
            f"{API}/deals/{STATE['deal_id']}/share",
            headers=_auth(STATE["token_a"]),
            timeout=15,
        )
        assert r.status_code == 200
        new_tok = r.json()["token"]
        assert new_tok != STATE["share_token"], "new share after revoke should mint a fresh token"


# ---------- 8. Regression smoke ----------
class TestRegressionSmoke:
    def test_dashboard(self):
        r = requests.get(f"{API}/dashboard/stats", headers=_auth(STATE["token_a"]), timeout=15)
        assert r.status_code == 200

    def test_export_csv(self):
        r = requests.get(
            f"{API}/deals/{STATE['deal_id']}/export.csv",
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_document_file_header_auth(self):
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}/file",
            headers=_auth(STATE["token_a"]),
            timeout=20,
        )
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_document_file_query_token(self):
        r = requests.get(
            f"{API}/documents/{STATE['doc_id']}/file",
            params={"token": STATE["token_a"]},
            timeout=20,
        )
        assert r.status_code == 200


# ---------- 9. Cleanup ----------
class TestCleanup:
    def test_delete_deals(self):
        requests.delete(f"{API}/deals/{STATE['deal_id']}", headers=_auth(STATE["token_a"]), timeout=15)
        requests.delete(f"{API}/deals/{STATE['deal_id_b']}", headers=_auth(STATE["token_b"]), timeout=15)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
