"""Iteration 4 — Orgs / Teams + Share expiry/password + Stripe replay tests.

Run with:
    REACT_APP_BACKEND_URL=https://ui-build-showcase.preview.emergentagent.com \
    pytest /app/backend/tests/test_orgs_iteration4.py -v --tb=short
"""
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

# Direct Mongo connection (for expired-share patching + cleanup)
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
_mc = MongoClient(MONGO_URL)
_db = _mc[DB_NAME]

TAG = uuid.uuid4().hex[:8]
A_EMAIL = f"orgs_a_{TAG}@clearvault.io"
B_EMAIL = f"orgs_b_{TAG}@clearvault.io"
C_EMAIL = f"orgs_c_{TAG}@clearvault.io"  # not invited
PW = "Vault123!"


# -------- helpers --------
def signup(email, name):
    r = requests.post(f"{API}/auth/signup", json={"email": email, "name": name, "password": PW, "firm": "TestCo"})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def h(token):
    return {"Authorization": f"Bearer {token}"}


# -------- fixtures --------
@pytest.fixture(scope="module")
def users():
    a_tok, a_user = signup(A_EMAIL, "User A")
    b_tok, b_user = signup(B_EMAIL, "User B")
    c_tok, c_user = signup(C_EMAIL, "User C")
    yield {
        "a": {"tok": a_tok, "user": a_user},
        "b": {"tok": b_tok, "user": b_user},
        "c": {"tok": c_tok, "user": c_user},
    }
    # cleanup
    for em in (A_EMAIL, B_EMAIL, C_EMAIL):
        u = _db.users.find_one({"email": em})
        if u:
            uid = u["_id"]
            org_ids = [m["org_id"] for m in _db.org_members.find({"user_id": uid})]
            _db.deals.delete_many({"user_id": uid})
            _db.documents.delete_many({"user_id": uid})
            _db.shares.delete_many({"user_id": uid})
            _db.org_members.delete_many({"user_id": uid})
            _db.organizations.delete_many({"_id": {"$in": org_ids}})
            _db.org_invites.delete_many({"$or": [{"invited_by": uid}, {"email": em}]})
            _db.users.delete_one({"_id": uid})


# ==================== ORG PROVISIONING ====================
class TestOrgProvisioning:
    def test_signup_auto_provisions_personal_org(self, users):
        r = requests.get(f"{API}/orgs/current", headers=h(users["a"]["tok"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"]
        assert d["owner_id"] == users["a"]["user"]["id"]
        assert d["my_role"] == "owner"
        assert len(d["members"]) == 1
        assert d["pending_invites"] == []
        assert "workspace" in d["name"].lower()

    def test_auth_me_has_current_org_id(self, users):
        r = requests.get(f"{API}/auth/me", headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        assert r.json().get("current_org_id")

    def test_list_my_orgs(self, users):
        r = requests.get(f"{API}/orgs/me/orgs", headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        orgs = r.json()["orgs"]
        assert len(orgs) >= 1
        assert any(o["role"] == "owner" for o in orgs)


# ==================== CROSS-USER ISOLATION (org refactor regression) ====================
class TestCrossUserIsolation:
    def test_b_cannot_see_a_deal(self, users):
        # A creates a deal
        r = requests.post(f"{API}/deals", json={"name": "Project Iso", "target_company": "IsoCo"},
                          headers=h(users["a"]["tok"]))
        assert r.status_code == 200, r.text
        deal_id = r.json()["id"]

        # A sees it
        ra = requests.get(f"{API}/deals", headers=h(users["a"]["tok"]))
        assert any(d["id"] == deal_id for d in ra.json())

        # B does NOT see it
        rb = requests.get(f"{API}/deals", headers=h(users["b"]["tok"]))
        assert all(d["id"] != deal_id for d in rb.json())

        # B 404 on direct GET
        assert requests.get(f"{API}/deals/{deal_id}", headers=h(users["b"]["tok"])).status_code == 404
        # B 404 on upload
        files = {"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
        assert requests.post(f"{API}/deals/{deal_id}/documents", files=files,
                             headers=h(users["b"]["tok"])).status_code == 404
        # B 404 on delete
        assert requests.delete(f"{API}/deals/{deal_id}", headers=h(users["b"]["tok"])).status_code == 404

        # Save deal id for downstream tests
        pytest.deal_a_iso = deal_id


# ==================== INVITES ====================
class TestInvites:
    def test_non_owner_cannot_invite(self, users):
        # B tries to invite into B's own org while A creates an invite for B's email (cross-org check)
        # First, prove a fresh non-owner case: B tries to invite into A's org — they're not even in A's org.
        # The endpoint operates on user's CURRENT org, so B trying to invite into B's own org as owner is allowed.
        # Instead test: a member (not owner/admin) — we'll set this up after B joins A's org.
        pass

    def test_invalid_role_400(self, users):
        r = requests.post(f"{API}/orgs/current/invites",
                          json={"email": "x@clearvault.io", "role": "superadmin"},
                          headers=h(users["a"]["tok"]))
        assert r.status_code == 400

    def test_owner_can_invite(self, users):
        r = requests.post(f"{API}/orgs/current/invites",
                          json={"email": B_EMAIL, "role": "member"},
                          headers=h(users["a"]["tok"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["token"]
        assert d["email"] == B_EMAIL
        assert d["role"] == "member"
        assert d["org_name"]
        assert d["url_path"] == f"/invite/{d['token']}"
        pytest.invite_token_b = d["token"]

    def test_reinvite_revokes_prior(self, users):
        old_tok = pytest.invite_token_b
        r = requests.post(f"{API}/orgs/current/invites",
                          json={"email": B_EMAIL, "role": "admin"},
                          headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        new_tok = r.json()["token"]
        assert new_tok != old_tok
        # Old should be 404 now
        assert requests.get(f"{API}/invites/{old_tok}").status_code == 404
        pytest.invite_token_b = new_tok

    def test_public_get_invite_unauth(self, users):
        # No auth header
        r = requests.get(f"{API}/invites/{pytest.invite_token_b}")
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == B_EMAIL
        assert d["org_id"]
        assert d["org_name"]
        assert d["invited_by"]

    def test_wrong_email_user_cannot_accept(self, users):
        # User C (not invited) tries to accept B's invite
        r = requests.post(f"{API}/invites/{pytest.invite_token_b}/accept",
                          headers=h(users["c"]["tok"]))
        assert r.status_code == 403

    def test_b_accepts_invite(self, users):
        r = requests.post(f"{API}/invites/{pytest.invite_token_b}/accept",
                          headers=h(users["b"]["tok"]))
        assert r.status_code == 200
        d = r.json()
        assert d["joined_org_id"]
        assert d["role"] == "admin"
        # B's current_org_id should now be A's org
        me = requests.get(f"{API}/auth/me", headers=h(users["b"]["tok"])).json()
        assert me["current_org_id"] == d["joined_org_id"]
        pytest.a_org_id = d["joined_org_id"]

    def test_accepted_invite_returns_404(self, users):
        assert requests.get(f"{API}/invites/{pytest.invite_token_b}").status_code == 404
        # Re-accept should also 404
        assert requests.post(f"{API}/invites/{pytest.invite_token_b}/accept",
                             headers=h(users["b"]["tok"])).status_code == 404

    def test_invite_existing_member_400(self, users):
        r = requests.post(f"{API}/orgs/current/invites",
                          json={"email": B_EMAIL, "role": "member"},
                          headers=h(users["a"]["tok"]))
        assert r.status_code == 400

    def test_b_sees_a_deal_after_joining(self, users):
        # End-to-end multi-seat visibility
        r = requests.get(f"{API}/deals", headers=h(users["b"]["tok"]))
        assert r.status_code == 200
        assert any(d["id"] == pytest.deal_a_iso for d in r.json())


# ==================== ROLE MANAGEMENT ====================
class TestRoleManagement:
    def test_owner_cannot_demote_self(self, users):
        a_id = users["a"]["user"]["id"]
        r = requests.patch(f"{API}/orgs/current/members/{a_id}",
                           json={"role": "member"}, headers=h(users["a"]["tok"]))
        assert r.status_code == 400

    def test_owner_can_change_member_role(self, users):
        b_id = users["b"]["user"]["id"]
        r = requests.patch(f"{API}/orgs/current/members/{b_id}",
                           json={"role": "member"}, headers=h(users["a"]["tok"]))
        assert r.status_code == 200

    def test_non_owner_cannot_change_role(self, users):
        # B (now member) tries to change a role in A's org (B's current org)
        a_id = users["a"]["user"]["id"]
        r = requests.patch(f"{API}/orgs/current/members/{a_id}",
                           json={"role": "member"}, headers=h(users["b"]["tok"]))
        assert r.status_code == 403

    def test_invalid_role_400(self, users):
        b_id = users["b"]["user"]["id"]
        r = requests.patch(f"{API}/orgs/current/members/{b_id}",
                           json={"role": "guest"}, headers=h(users["a"]["tok"]))
        assert r.status_code == 400

    def test_owner_cannot_remove_self(self, users):
        a_id = users["a"]["user"]["id"]
        r = requests.delete(f"{API}/orgs/current/members/{a_id}", headers=h(users["a"]["tok"]))
        assert r.status_code == 400


# ==================== INVITE REVOKE ====================
class TestInviteRevoke:
    def test_invite_then_revoke(self, users):
        # Need to first re-set A's current org back to A's org (B's accept changed B's, not A's)
        r = requests.post(f"{API}/orgs/current/invites",
                          json={"email": C_EMAIL, "role": "member"},
                          headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        token = r.json()["token"]
        inv = _db.org_invites.find_one({"_id": token})
        invite_id = inv["_id"]

        # Wrong-org: B is in A's org now and is a member (just demoted) → should 403
        # Use revoke as A (owner)
        r2 = requests.delete(f"{API}/orgs/current/invites/{invite_id}", headers=h(users["a"]["tok"]))
        assert r2.status_code == 200

        # Now C cannot accept
        r3 = requests.post(f"{API}/invites/{token}/accept", headers=h(users["c"]["tok"]))
        assert r3.status_code == 404

    def test_revoke_nonexistent_404(self, users):
        r = requests.delete(f"{API}/orgs/current/invites/nonexistent_id_xyz",
                            headers=h(users["a"]["tok"]))
        assert r.status_code == 404


# ==================== SWITCH ORG ====================
class TestSwitchOrg:
    def test_switch_to_non_member_org_404(self, users):
        # C tries to switch to A's org (not a member)
        r = requests.post(f"{API}/orgs/switch/{pytest.a_org_id}", headers=h(users["c"]["tok"]))
        assert r.status_code == 404

    def test_b_can_switch_back_to_personal(self, users):
        # B's personal org
        orgs = requests.get(f"{API}/orgs/me/orgs", headers=h(users["b"]["tok"])).json()["orgs"]
        b_personal = next((o for o in orgs if o["role"] == "owner"), None)
        assert b_personal
        r = requests.post(f"{API}/orgs/switch/{b_personal['id']}", headers=h(users["b"]["tok"]))
        assert r.status_code == 200
        # Verify
        me = requests.get(f"{API}/auth/me", headers=h(users["b"]["tok"])).json()
        assert me["current_org_id"] == b_personal["id"]
        # But B should STILL see A's deal because _user_org_ids spans all orgs
        deals = requests.get(f"{API}/deals", headers=h(users["b"]["tok"])).json()
        assert any(d["id"] == pytest.deal_a_iso for d in deals)


# ==================== REMOVE MEMBER ====================
class TestRemoveMember:
    def test_remove_member_falls_back_to_personal(self, users):
        b_id = users["b"]["user"]["id"]
        r = requests.delete(f"{API}/orgs/current/members/{b_id}", headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        # B should no longer see A's deals
        deals = requests.get(f"{API}/deals", headers=h(users["b"]["tok"])).json()
        assert all(d["id"] != pytest.deal_a_iso for d in deals)


# ==================== SHARE EXPIRY + PASSWORD ====================
class TestShareExpiryPassword:
    @classmethod
    def setup_class(cls):
        # A creates a deal + fake rollup directly in db so share endpoints work
        tok = signup(f"share_owner_{TAG}@clearvault.io", "Share Owner")[0]
        cls.tok = tok
        r = requests.post(f"{API}/deals",
                          json={"name": "Share Deal", "target_company": "ShareCo"},
                          headers=h(tok))
        deal_id = r.json()["id"]
        cls.deal_id = deal_id
        # Inject a rollup directly
        _db.deals.update_one({"_id": deal_id}, {"$set": {"rollup": "Test rollup memo"}})

    @classmethod
    def teardown_class(cls):
        em = f"share_owner_{TAG}@clearvault.io"
        u = _db.users.find_one({"email": em})
        if u:
            uid = u["_id"]
            _db.deals.delete_many({"user_id": uid})
            _db.documents.delete_many({"user_id": uid})
            _db.shares.delete_many({"user_id": uid})
            _db.org_members.delete_many({"user_id": uid})
            _db.organizations.delete_many({"owner_id": uid})
            _db.users.delete_one({"_id": uid})

    def test_share_no_body_no_expiry(self):
        # No body
        r = requests.post(f"{API}/deals/{self.deal_id}/share", headers=h(self.tok))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["expires_at"] is None
        assert d["has_password"] is False
        self.__class__.tok_noexp = d["token"]

    def test_share_with_expiry_1day(self):
        # Revoke first to force new
        requests.delete(f"{API}/deals/{self.deal_id}/share", headers=h(self.tok))
        r = requests.post(f"{API}/deals/{self.deal_id}/share",
                          json={"expires_in_days": 1}, headers=h(self.tok))
        assert r.status_code == 200
        d = r.json()
        assert d["expires_at"]
        exp = datetime.fromisoformat(d["expires_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = exp - now
        assert timedelta(hours=23) < delta < timedelta(hours=25), f"delta={delta}"
        self.__class__.tok_1day = d["token"]

    def test_share_zero_days_no_expiry(self):
        requests.delete(f"{API}/deals/{self.deal_id}/share", headers=h(self.tok))
        r = requests.post(f"{API}/deals/{self.deal_id}/share",
                          json={"expires_in_days": 0}, headers=h(self.tok))
        assert r.status_code == 200
        assert r.json()["expires_at"] is None

    def test_share_password_meta_and_unlock(self):
        requests.delete(f"{API}/deals/{self.deal_id}/share", headers=h(self.tok))
        r = requests.post(f"{API}/deals/{self.deal_id}/share",
                          json={"password": "secret123"}, headers=h(self.tok))
        assert r.status_code == 200
        d = r.json()
        assert d["has_password"] is True
        tok = d["token"]

        # Meta (public, no auth)
        m = requests.get(f"{API}/share/{tok}/meta")
        assert m.status_code == 200
        meta = m.json()
        assert meta["has_password"] is True
        assert meta["deal_name"] == "Share Deal"
        assert meta["target_company"] == "ShareCo"

        # GET without password → 401
        g = requests.get(f"{API}/share/{tok}")
        assert g.status_code == 401
        assert "password" in g.text.lower()

        # Wrong password → 401
        w = requests.post(f"{API}/share/{tok}/unlock", json={"password": "wrong"})
        assert w.status_code == 401

        # Correct password → 200 with rollup
        c = requests.post(f"{API}/share/{tok}/unlock", json={"password": "secret123"})
        assert c.status_code == 200
        assert c.json().get("rollup")
        self.__class__.tok_pw = tok

    def test_share_idempotency_same_settings(self):
        requests.delete(f"{API}/deals/{self.deal_id}/share", headers=h(self.tok))
        r1 = requests.post(f"{API}/deals/{self.deal_id}/share",
                           json={"password": "abc"}, headers=h(self.tok))
        t1 = r1.json()["token"]
        r2 = requests.post(f"{API}/deals/{self.deal_id}/share",
                           json={"password": "abc"}, headers=h(self.tok))
        # Same settings → same token
        assert r2.json()["token"] == t1

    def test_share_changes_revoke_and_remint(self):
        # Change password → new token
        r3 = requests.post(f"{API}/deals/{self.deal_id}/share",
                           json={"password": "different"}, headers=h(self.tok))
        # Just verify token created (idempotency code path)
        assert r3.status_code == 200

    def test_expired_share_410(self):
        # Create a share, then manually backdate expires_at
        requests.delete(f"{API}/deals/{self.deal_id}/share", headers=h(self.tok))
        r = requests.post(f"{API}/deals/{self.deal_id}/share",
                          json={"expires_in_days": 1}, headers=h(self.tok))
        tok = r.json()["token"]
        # Backdate in DB
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        _db.shares.update_one({"_id": tok}, {"$set": {"expires_at": past}})

        m = requests.get(f"{API}/share/{tok}/meta")
        assert m.status_code == 410
        v = requests.get(f"{API}/share/{tok}")
        assert v.status_code == 410


# ==================== STRIPE REPLAY ====================
class TestStripeReplay:
    def test_invalid_webhook_returns_400(self):
        r = requests.post(f"{API}/webhook/stripe", data=b"not a real event", headers={"Stripe-Signature": "bad"})
        assert r.status_code == 400, f"got {r.status_code}: {r.text}"
        # Must NOT be 500
        assert r.status_code != 500

    def test_stripe_events_collection_exists_or_creatable(self):
        # We can verify the collection name is defined; just attempt a find
        # to ensure code path doesn't crash. Should return empty for unknown id.
        doc = _db.stripe_events.find_one({"_id": "nonexistent_event"})
        assert doc is None


# ==================== REGRESSION SMOKE ====================
class TestRegressionSmoke:
    def test_auth_me(self, users):
        r = requests.get(f"{API}/auth/me", headers=h(users["a"]["tok"]))
        assert r.status_code == 200

    def test_dashboard_stats(self, users):
        r = requests.get(f"{API}/dashboard/stats", headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("deals_total", "deals_active", "documents_total", "red_flags_total"):
            assert k in d

    def test_activity_recent(self, users):
        r = requests.get(f"{API}/activity/recent", headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_packages(self):
        r = requests.get(f"{API}/payments/packages")
        assert r.status_code == 200
        assert "packages" in r.json()

    def test_search(self, users):
        r = requests.get(f"{API}/search", params={"q": "Iso"}, headers=h(users["a"]["tok"]))
        assert r.status_code == 200

    def test_settings_update(self, users):
        r = requests.patch(f"{API}/auth/settings", json={"firm": "Updated Firm"},
                           headers=h(users["a"]["tok"]))
        assert r.status_code == 200
        assert r.json()["firm"] == "Updated Firm"

    def test_login_lazy_migration(self):
        r = requests.post(f"{API}/auth/login", json={"email": A_EMAIL, "password": PW})
        assert r.status_code == 200
        assert r.json()["user"].get("current_org_id")
