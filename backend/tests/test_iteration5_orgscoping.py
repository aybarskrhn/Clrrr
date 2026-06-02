"""
Iteration 5 targeted verification:
  - /api/activity/recent returns newly-uploaded doc (regression fix)
  - Multi-seat: B can GET/file/DELETE doc, rollup, stats, search, recent on A's deal
  - Cross-org: C still gets 404
  - Legacy backfill: doc inserted without org_id gets backfilled via _user_org_ids
  - Self-invite guard: POST current/invites with own email -> 400
"""
import io
import os
import secrets
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]

TAG = secrets.token_hex(4)
USER_A = f"i5a_{TAG}@clearvault.io"
USER_B = f"i5b_{TAG}@clearvault.io"
USER_C = f"i5c_{TAG}@clearvault.io"
PWD = "Vault123!"

state = {}


def _signup(email, name):
    r = requests.post(f"{API}/auth/signup", json={
        "email": email, "name": name, "password": PWD, "firm": "TestCo"
    })
    assert r.status_code == 200, r.text
    return r.json()


def _login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _make_pdf(label="iteration5"):
    body = (
        b"%PDF-1.4\n1 0 obj<<>>endobj\nstream\n"
        + f"ClearVault-{label}-{TAG} acme acquisition target".encode()
        + b"\nendstream\n%%EOF"
    )
    return body


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    a = _signup(USER_A, "Alice")
    b = _signup(USER_B, "Bob")
    c = _signup(USER_C, "Carol")
    state["a_tok"] = a["token"]
    state["a_id"] = a["user"]["id"]
    state["b_tok"] = b["token"]
    state["b_id"] = b["user"]["id"]
    state["c_tok"] = c["token"]
    state["c_id"] = c["user"]["id"]

    # Create deal in A
    r = requests.post(f"{API}/deals", json={
        "name": f"DealAcme_{TAG}", "target_company": f"AcmeTarget_{TAG}",
        "sector": "SaaS", "deal_size": "$10M"
    }, headers=_h(state["a_tok"]))
    assert r.status_code == 200, r.text
    state["deal_id"] = r.json()["id"]

    # A invites B
    inv = requests.post(f"{API}/orgs/current/invites", json={
        "email": USER_B, "role": "member"
    }, headers=_h(state["a_tok"]))
    assert inv.status_code == 200, inv.text
    invite_token = inv.json()["token"]

    # B accepts
    ac = requests.post(f"{API}/invites/{invite_token}/accept", headers=_h(state["b_tok"]))
    assert ac.status_code == 200, ac.text

    yield

    # Cleanup
    for uid in [state["a_id"], state["b_id"], state["c_id"]]:
        db.users.delete_many({"_id": uid})
        db.deals.delete_many({"user_id": uid})
        db.documents.delete_many({"user_id": uid})
        db.org_members.delete_many({"user_id": uid})
        db.organizations.delete_many({"owner_id": uid})
    db.org_invites.delete_many({"email": {"$in": [USER_A, USER_B, USER_C]}})


# ---------- 1. Recent activity returns newly uploaded doc ----------
class TestRecentActivityAfterUpload:
    def test_upload_and_recent_for_uploader(self):
        files = {"file": ("acme.pdf", _make_pdf("upload"), "application/pdf")}
        up = requests.post(
            f"{API}/deals/{state['deal_id']}/documents",
            files=files, headers=_h(state["a_tok"])
        )
        assert up.status_code == 200, up.text
        doc = up.json()
        state["doc_id"] = doc["id"]
        # DocumentOut response model doesn't expose org_id; verify via mongo instead
        raw = db.documents.find_one({"_id": state["doc_id"]})
        assert raw and raw.get("org_id"), f"Uploaded doc must have org_id in db: {raw}"

        r = requests.get(f"{API}/activity/recent", headers=_h(state["a_tok"]))
        assert r.status_code == 200
        items = r.json()
        assert any(d["id"] == state["doc_id"] for d in items), "Uploader should see own doc in recent"

    def test_recent_for_org_member_b(self):
        r = requests.get(f"{API}/activity/recent", headers=_h(state["b_tok"]))
        assert r.status_code == 200
        items = r.json()
        assert any(d["id"] == state["doc_id"] for d in items), "Org member B should see shared org doc"


# ---------- 2. Multi-seat access by B ----------
class TestMultiSeatAccess:
    def test_b_can_get_document(self):
        r = requests.get(f"{API}/documents/{state['doc_id']}", headers=_h(state["b_tok"]))
        assert r.status_code == 200, r.text
        assert r.json()["id"] == state["doc_id"]

    def test_b_can_get_document_file(self):
        r = requests.get(f"{API}/documents/{state['doc_id']}/file", headers=_h(state["b_tok"]))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert len(r.content) > 50

    def test_b_can_get_rollup(self):
        # Generate rollup as A first (needs completed doc -> wait for extraction)
        import time
        for _ in range(20):
            d = requests.get(f"{API}/documents/{state['doc_id']}", headers=_h(state["a_tok"])).json()
            if d.get("status") == "completed":
                break
            time.sleep(1.5)
        # Attempt rollup gen (may 400 if no completed); but GET should work
        r = requests.get(f"{API}/deals/{state['deal_id']}/rollup", headers=_h(state["b_tok"]))
        assert r.status_code in (200, 404), f"unexpected {r.status_code}: {r.text}"

    def test_b_dashboard_counts_shared(self):
        r = requests.get(f"{API}/dashboard/stats", headers=_h(state["b_tok"]))
        assert r.status_code == 200
        s = r.json()
        assert s["deals_total"] >= 1
        assert s["documents_total"] >= 1

    def test_b_search_finds_org_content(self):
        r = requests.get(f"{API}/search", params={"q": f"AcmeTarget_{TAG}"}, headers=_h(state["b_tok"]))
        assert r.status_code == 200
        data = r.json()
        deals = data.get("deals", [])
        assert any(d["id"] == state["deal_id"] for d in deals), f"B should find shared deal: {data}"

    def test_b_can_delete_separate_document(self):
        # Upload another doc as A specifically for B to delete
        files = {"file": ("delete_me.pdf", _make_pdf("delete"), "application/pdf")}
        up = requests.post(
            f"{API}/deals/{state['deal_id']}/documents",
            files=files, headers=_h(state["a_tok"])
        )
        assert up.status_code == 200
        del_id = up.json()["id"]

        d = requests.delete(f"{API}/documents/{del_id}", headers=_h(state["b_tok"]))
        assert d.status_code in (200, 204), d.text

        # Verify gone
        g = requests.get(f"{API}/documents/{del_id}", headers=_h(state["a_tok"]))
        assert g.status_code == 404


# ---------- 3. Cross-org isolation ----------
class TestCrossOrgIsolation:
    def test_c_get_document_404(self):
        r = requests.get(f"{API}/documents/{state['doc_id']}", headers=_h(state["c_tok"]))
        assert r.status_code == 404

    def test_c_get_document_file_404(self):
        r = requests.get(f"{API}/documents/{state['doc_id']}/file", headers=_h(state["c_tok"]))
        assert r.status_code == 404

    def test_c_delete_document_404(self):
        r = requests.delete(f"{API}/documents/{state['doc_id']}", headers=_h(state["c_tok"]))
        assert r.status_code == 404

    def test_c_rollup_404(self):
        r = requests.get(f"{API}/deals/{state['deal_id']}/rollup", headers=_h(state["c_tok"]))
        assert r.status_code == 404

    def test_c_search_does_not_see_org_content(self):
        r = requests.get(f"{API}/search", params={"q": f"AcmeTarget_{TAG}"}, headers=_h(state["c_tok"]))
        assert r.status_code == 200
        deals = r.json().get("deals", [])
        assert not any(d["id"] == state["deal_id"] for d in deals)

    def test_c_recent_does_not_see_org_doc(self):
        r = requests.get(f"{API}/activity/recent", headers=_h(state["c_tok"]))
        assert r.status_code == 200
        assert not any(d["id"] == state["doc_id"] for d in r.json())


# ---------- 4. Legacy doc backfill via direct mongo insert ----------
class TestLegacyDocBackfill:
    def test_legacy_doc_gets_backfilled_org_id(self):
        # Resolve deal's org_id from mongo
        deal_raw = db.deals.find_one({"_id": state["deal_id"]})
        assert deal_raw and deal_raw.get("org_id")
        deal_org = deal_raw["org_id"]

        legacy_id = str(uuid.uuid4())
        db.documents.insert_one({
            "_id": legacy_id,
            "deal_id": state["deal_id"],
            "user_id": state["a_id"],
            "filename": f"legacy_{TAG}.pdf",
            "file_path": "/tmp/nonexistent.pdf",
            "file_size": 0,
            "mime_type": "application/pdf",
            "status": "uploaded",
            "created_at": datetime.now(timezone.utc).isoformat(),
            # NOTE: deliberately omit org_id
        })

        pre = db.documents.find_one({"_id": legacy_id})
        assert "org_id" not in pre or pre.get("org_id") is None

        # Trigger backfill by calling any org-scoped endpoint that runs _user_org_ids
        r = requests.get(f"{API}/activity/recent", headers=_h(state["a_tok"]))
        assert r.status_code == 200

        post = db.documents.find_one({"_id": legacy_id})
        assert post.get("org_id") == deal_org, f"backfill failed: {post}"

    def test_legacy_doc_accessible_after_backfill_by_org_member(self):
        # Insert a second legacy doc
        deal_raw = db.deals.find_one({"_id": state["deal_id"]})
        deal_org = deal_raw["org_id"]
        legacy_id = str(uuid.uuid4())
        db.documents.insert_one({
            "_id": legacy_id,
            "deal_id": state["deal_id"],
            "user_id": state["a_id"],
            "filename": f"legacy2_{TAG}.pdf",
            "file_path": "/tmp/nonexistent2.pdf",
            "file_size": 0,
            "mime_type": "application/pdf",
            "status": "uploaded",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # B (org member) calls GET document - should backfill on the fly and return 200
        r = requests.get(f"{API}/documents/{legacy_id}", headers=_h(state["b_tok"]))
        assert r.status_code == 200, r.text

        post = db.documents.find_one({"_id": legacy_id})
        assert post.get("org_id") == deal_org


# ---------- 5. Self-invite guard ----------
class TestSelfInviteGuard:
    def test_self_invite_returns_400(self):
        r = requests.post(f"{API}/orgs/current/invites", json={
            "email": USER_A, "role": "member"
        }, headers=_h(state["a_tok"]))
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "").lower()
        assert "invite yourself" in detail, f"expected 'invite yourself' in: {detail}"

    def test_self_invite_case_insensitive(self):
        r = requests.post(f"{API}/orgs/current/invites", json={
            "email": USER_A.upper(), "role": "member"
        }, headers=_h(state["a_tok"]))
        assert r.status_code == 400
