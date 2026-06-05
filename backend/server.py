"""ClearVault — FastAPI backend."""
import csv
import io
import logging
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr
from pymongo import ReturnDocument
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from ai_service import answer_question_with_pdf, extract_pdf, summarize_deal  # noqa: E402
from analysis_pipeline import (  # noqa: E402
    _extract_row_reasoning,
    answer_with_citations,  # noqa: F401  (kept for backwards-compat / future use)
    markdown_table_to_csv,
)
from provenance import extract_table_from_answer, resolve_table_provenance  # noqa: E402
from extractor import (  # noqa: E402
    extract_page_text,
    page_count as pdf_page_count,
    render_page_with_highlights,
    render_thumbnail,
)
from auth import create_token, decode_token, get_current_user_id, hash_password, verify_password  # noqa: E402
from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest  # noqa: E402
from payments import PACKAGES, get_package, make_checkout  # noqa: E402
from slack_notify import notify_extraction_complete  # noqa: E402
from models import (  # noqa: E402
    AuthResponse,
    Deal,
    DealCreate,
    DealOut,
    Document,
    DocumentOut,
    LoginRequest,
    SignupRequest,
    User,
    UserPublic,
    now_iso,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/clearvault_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB

app = FastAPI(title="ClearVault API")
api = APIRouter(prefix="/api")


# ---------- Helpers ----------
def user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        firm=user.firm,
        role=user.role,
        plan=user.plan,
        plan_active_until=user.plan_active_until,
        slack_webhook_url=user.slack_webhook_url,
        current_org_id=user.current_org_id,
        created_at=user.created_at,
    )


async def _find_user_by_id(user_id: str) -> User:
    doc = await db.users.find_one({"_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return User.from_mongo(doc)


# ---------- Organization helpers ----------
async def _ensure_user_org(user_id: str) -> str:
    """Return the user's current org_id, creating a personal org + backfilling
    legacy deals/documents the first time we see this user."""
    user_doc = await db.users.find_one({"_id": user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    if user_doc.get("current_org_id"):
        return user_doc["current_org_id"]

    # First-time setup — personal org
    org_id = str(uuid.uuid4())
    name = user_doc.get("name") or user_doc.get("email", "Personal").split("@")[0]
    await db.organizations.insert_one({
        "_id": org_id,
        "name": f"{name}'s workspace",
        "owner_id": user_id,
        "plan": user_doc.get("plan", "trial"),
        "plan_active_until": user_doc.get("plan_active_until"),
        "created_at": now_iso(),
    })
    await db.org_members.insert_one({
        "_id": str(uuid.uuid4()),
        "org_id": org_id,
        "user_id": user_id,
        "role": "owner",
        "joined_at": now_iso(),
    })
    await db.users.update_one({"_id": user_id}, {"$set": {"current_org_id": org_id}})

    # Backfill any legacy deals owned by this user that don't yet have org_id
    await db.deals.update_many(
        {"user_id": user_id, "$or": [{"org_id": None}, {"org_id": {"$exists": False}}]},
        {"$set": {"org_id": org_id}},
    )
    await db.documents.update_many(
        {"user_id": user_id, "$or": [{"org_id": None}, {"org_id": {"$exists": False}}]},
        {"$set": {"org_id": org_id}},
    )
    return org_id


async def _backfill_missing_doc_org_ids(user_id: str) -> None:
    """One-shot backfill: any document owned by this user with no org_id gets its parent deal's org_id."""
    # Skip if already backfilled (set a flag on the user record after first clean pass)
    flag = await db.users.find_one({"_id": user_id}, {"docs_backfilled": 1})
    if flag and flag.get("docs_backfilled"):
        return
    cursor = db.documents.find({
        "user_id": user_id,
        "$or": [{"org_id": None}, {"org_id": {"$exists": False}}],
    })
    found_any = False
    async for d in cursor:
        found_any = True
        deal = await db.deals.find_one({"_id": d.get("deal_id")})
        if deal and deal.get("org_id"):
            await db.documents.update_one({"_id": d["_id"]}, {"$set": {"org_id": deal["org_id"]}})
    # Mark backfilled when there's nothing left to migrate — subsequent calls are cheap no-ops
    if not found_any:
        await db.users.update_one({"_id": user_id}, {"$set": {"docs_backfilled": True}})


async def _user_org_ids(user_id: str) -> List[str]:
    """All org IDs the user is a member of (auto-creates personal org if missing)."""
    await _ensure_user_org(user_id)
    await _backfill_missing_doc_org_ids(user_id)
    ids: List[str] = []
    async for m in db.org_members.find({"user_id": user_id}):
        ids.append(m["org_id"])
    return ids


async def _require_org_role(org_id: str, user_id: str, *, roles: List[str]) -> dict:
    m = await db.org_members.find_one({"org_id": org_id, "user_id": user_id})
    if not m:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    if m.get("role") not in roles:
        raise HTTPException(status_code=403, detail=f"Requires role: {' or '.join(roles)}")
    return m


async def _accessible_deal(deal_id: str, user_id: str) -> dict:
    """Return the deal raw doc if accessible by this user (via any org membership), else 404."""
    org_ids = await _user_org_ids(user_id)
    raw = await db.deals.find_one({"_id": deal_id, "org_id": {"$in": org_ids}})
    if not raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    return raw


async def _accessible_document(doc_id: str, user_id: str) -> dict:
    """Return the doc raw if user has access via the parent deal's org. Falls back to legacy user_id."""
    org_ids = await _user_org_ids(user_id)
    raw = await db.documents.find_one({"_id": doc_id})
    if not raw:
        raise HTTPException(status_code=404, detail="Document not found")
    if raw.get("org_id") and raw["org_id"] in org_ids:
        return raw
    # Fallback: check deal's org
    deal = await db.deals.find_one({"_id": raw.get("deal_id")})
    if deal and deal.get("org_id") in org_ids:
        # Backfill the doc's org_id while we're here
        await db.documents.update_one({"_id": doc_id}, {"$set": {"org_id": deal["org_id"]}})
        return raw
    raise HTTPException(status_code=404, detail="Document not found")


# ---------- Health ----------
@api.get("/")
async def root():
    return {"app": "ClearVault", "status": "ok"}


# ---------- Auth ----------
@api.post("/auth/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest):
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        name=payload.name,
        password_hash=hash_password(payload.password),
        firm=payload.firm,
    )
    doc = user.to_mongo()
    new_id = str(uuid.uuid4())
    doc["_id"] = new_id
    await db.users.insert_one(doc)
    user.id = new_id

    token = create_token(new_id, user.email)
    return AuthResponse(token=token, user=user_public(user))


@api.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest):
    doc = await db.users.find_one({"email": payload.email.lower()})
    if not doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = User.from_mongo(doc)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Ensure org exists for legacy users
    user.current_org_id = await _ensure_user_org(user.id)
    token = create_token(user.id, user.email)
    return AuthResponse(token=token, user=user_public(user))


@api.get("/auth/me", response_model=UserPublic)
async def me(user_id: str = Depends(get_current_user_id)):
    await _ensure_user_org(user_id)
    user = await _find_user_by_id(user_id)
    return user_public(user)


# ---------- Dashboard ----------
@api.get("/dashboard/stats")
async def dashboard_stats(user_id: str = Depends(get_current_user_id)):
    org_ids = await _user_org_ids(user_id)
    deals_total = await db.deals.count_documents({"org_id": {"$in": org_ids}})
    deals_active = await db.deals.count_documents({"org_id": {"$in": org_ids}, "status": "active"})
    docs_total = await db.documents.count_documents({"org_id": {"$in": org_ids}})
    docs_completed = await db.documents.count_documents({"org_id": {"$in": org_ids}, "status": "completed"})

    # aggregate red flags across all completed extractions in the user's orgs
    red_flags_total = 0
    high_severity = 0
    async for d in db.documents.find({"org_id": {"$in": org_ids}, "status": "completed"}):
        extracted = d.get("extracted") or {}
        flags = extracted.get("red_flags") or []
        red_flags_total += len(flags)
        high_severity += sum(1 for f in flags if (f.get("severity") or "").lower() == "high")

    return {
        "deals_total": deals_total,
        "deals_active": deals_active,
        "documents_total": docs_total,
        "documents_completed": docs_completed,
        "red_flags_total": red_flags_total,
        "red_flags_high": high_severity,
    }


# ---------- Deals ----------
async def _deal_out(deal: Deal) -> DealOut:
    docs_count = await db.documents.count_documents({"deal_id": deal.id})
    red_flags = 0
    async for d in db.documents.find({"deal_id": deal.id, "status": "completed"}):
        red_flags += len((d.get("extracted") or {}).get("red_flags") or [])
    return DealOut(
        id=deal.id,
        name=deal.name,
        target_company=deal.target_company,
        sector=deal.sector,
        deal_size=deal.deal_size,
        stage=deal.stage,
        status=deal.status,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
        documents_count=docs_count,
        red_flags_count=red_flags,
    )


@api.get("/deals", response_model=List[DealOut])
async def list_deals(user_id: str = Depends(get_current_user_id)):
    org_ids = await _user_org_ids(user_id)
    out: List[DealOut] = []
    cursor = db.deals.find({"org_id": {"$in": org_ids}}).sort("created_at", -1)
    async for raw in cursor:
        deal = Deal.from_mongo(raw)
        out.append(await _deal_out(deal))
    return out


@api.post("/deals", response_model=DealOut)
async def create_deal(payload: DealCreate, user_id: str = Depends(get_current_user_id)):
    org_id = await _ensure_user_org(user_id)
    # Use the user's current_org_id if set, else the just-created personal org
    user_doc = await db.users.find_one({"_id": user_id})
    target_org = (user_doc or {}).get("current_org_id") or org_id

    deal = Deal(
        user_id=user_id,
        org_id=target_org,
        name=payload.name,
        target_company=payload.target_company,
        sector=payload.sector or "Industrials",
        deal_size=payload.deal_size,
    )
    doc = deal.to_mongo()
    new_id = str(uuid.uuid4())
    doc["_id"] = new_id
    await db.deals.insert_one(doc)
    deal.id = new_id
    return await _deal_out(deal)


@api.get("/deals/{deal_id}", response_model=DealOut)
async def get_deal(deal_id: str, user_id: str = Depends(get_current_user_id)):
    raw = await _accessible_deal(deal_id, user_id)
    return await _deal_out(Deal.from_mongo(raw))


@api.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, user_id: str = Depends(get_current_user_id)):
    raw = await _accessible_deal(deal_id, user_id)
    await db.deals.delete_one({"_id": deal_id})
    await db.documents.delete_many({"deal_id": deal_id})
    return {"deleted": True}


# ---------- Documents ----------
def _doc_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        deal_id=doc.deal_id,
        filename=doc.filename,
        file_size=doc.file_size,
        status=doc.status,
        error=doc.error,
        created_at=doc.created_at,
        processed_at=doc.processed_at,
        extracted=doc.extracted,
    )


async def _process_document(document_id: str):
    """Background task — runs AI extraction and updates the doc record."""
    raw = await db.documents.find_one({"_id": document_id})
    if not raw:
        logger.warning("Document %s not found for processing", document_id)
        return
    doc = Document.from_mongo(raw)
    await db.documents.update_one({"_id": document_id}, {"$set": {"status": "processing"}})
    try:
        extracted = await extract_pdf(doc.file_path)
        await db.documents.update_one(
            {"_id": document_id},
            {"$set": {"status": "completed", "extracted": extracted, "processed_at": now_iso()}},
        )
        logger.info("Document %s extraction complete", document_id)

        # Slack notification (best-effort)
        try:
            user_raw = await db.users.find_one({"_id": doc.user_id})
            deal_raw = await db.deals.find_one({"_id": doc.deal_id})
            if user_raw and user_raw.get("slack_webhook_url") and deal_raw:
                red = extracted.get("red_flags") or []
                high = sum(1 for f in red if (f.get("severity") or "").lower() == "high")
                await notify_extraction_complete(
                    user_raw.get("slack_webhook_url"),
                    deal_name=deal_raw.get("name", ""),
                    target_company=deal_raw.get("target_company", ""),
                    filename=doc.filename,
                    summary=extracted.get("summary", "") or "",
                    red_flags=red,
                    high_count=high,
                    app_url=os.environ.get("PUBLIC_APP_URL"),
                    deal_id=doc.deal_id,
                )
        except Exception as nexc:  # noqa: BLE001
            logger.warning("Slack notify skipped: %s", nexc)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Extraction failed for %s", document_id)
        await db.documents.update_one(
            {"_id": document_id},
            {"$set": {"status": "failed", "error": str(exc)[:500]}},
        )


@api.post("/deals/{deal_id}/documents", response_model=DocumentOut)
async def upload_document(
    deal_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    deal_raw = await _accessible_deal(deal_id, user_id)
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal not found")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    new_id = str(uuid.uuid4())
    safe_name = file.filename.replace("/", "_")
    target = UPLOAD_DIR / f"{new_id}_{safe_name}"
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    file_size = target.stat().st_size

    document = Document(
        user_id=user_id,
        deal_id=deal_id,
        filename=safe_name,
        file_path=str(target),
        file_size=file_size,
        status="uploaded",
        org_id=deal_raw.get("org_id"),
    )
    doc_dict = document.to_mongo()
    doc_dict["_id"] = new_id
    await db.documents.insert_one(doc_dict)
    document.id = new_id

    background.add_task(_process_document, new_id)
    return _doc_out(document)


@api.get("/deals/{deal_id}/documents", response_model=List[DocumentOut])
async def list_documents(deal_id: str, user_id: str = Depends(get_current_user_id)):
    deal_raw = await _accessible_deal(deal_id, user_id)
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    out: List[DocumentOut] = []
    cursor = db.documents.find({"deal_id": deal_id}).sort("created_at", -1)
    async for raw in cursor:
        out.append(_doc_out(Document.from_mongo(raw)))
    return out


@api.get("/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, user_id: str = Depends(get_current_user_id)):
    raw = await _accessible_document(doc_id, user_id)
    return _doc_out(Document.from_mongo(raw))


@api.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user_id: str = Depends(get_current_user_id)):
    raw = await _accessible_document(doc_id, user_id)
    try:
        Path(raw["file_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    await db.documents.delete_one({"_id": doc_id})
    return {"deleted": True}


# ---------- Recent activity ----------
@api.get("/activity/recent")
async def recent_activity(user_id: str = Depends(get_current_user_id), limit: int = 8):
    org_ids = await _user_org_ids(user_id)
    items = []
    async for raw in db.documents.find({"org_id": {"$in": org_ids}}).sort("created_at", -1).limit(limit):
        items.append(
            {
                "id": str(raw["_id"]),
                "deal_id": raw.get("deal_id"),
                "filename": raw.get("filename"),
                "status": raw.get("status"),
                "created_at": raw.get("created_at"),
            }
        )
    return items


# ---------- CSV export ----------
@api.get("/deals/{deal_id}/export.csv")
async def export_deal_csv(deal_id: str, user_id: str = Depends(get_current_user_id)):
    deal_raw = await _accessible_deal(deal_id, user_id)
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal not found")

    buf = io.StringIO()
    writer = csv.writer(buf)
    deal = Deal.from_mongo(deal_raw)

    writer.writerow([f"# ClearVault export — {deal.name} ({deal.target_company})"])
    writer.writerow([f"# generated_at: {now_iso()}"])
    writer.writerow([])

    # Financial metrics section
    writer.writerow(["section", "document", "label", "value", "period", "notes"])
    async for raw in db.documents.find({"deal_id": deal_id, "status": "completed"}):
        doc = Document.from_mongo(raw)
        ex = doc.extracted or {}
        for m in (ex.get("financial_metrics") or []):
            writer.writerow([
                "financial_metric",
                doc.filename,
                m.get("label", ""),
                m.get("value", ""),
                m.get("period", ""),
                m.get("notes", ""),
            ])

    writer.writerow([])
    writer.writerow(["section", "document", "severity", "title", "description", "page"])
    async for raw in db.documents.find({"deal_id": deal_id, "status": "completed"}):
        doc = Document.from_mongo(raw)
        ex = doc.extracted or {}
        for f in (ex.get("red_flags") or []):
            writer.writerow([
                "red_flag",
                doc.filename,
                f.get("severity", ""),
                f.get("title", ""),
                f.get("description", ""),
                f.get("page", ""),
            ])

    writer.writerow([])
    writer.writerow(["section", "document", "label", "value", "notes"])
    async for raw in db.documents.find({"deal_id": deal_id, "status": "completed"}):
        doc = Document.from_mongo(raw)
        ex = doc.extracted or {}
        for t in (ex.get("key_terms") or []):
            writer.writerow([
                "key_term",
                doc.filename,
                t.get("label", ""),
                t.get("value", ""),
                t.get("notes", ""),
            ])

    buf.seek(0)
    safe = deal.name.replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="clearvault_{safe}.csv"'},
    )


# ---------- Roll-up summary ----------
@api.post("/deals/{deal_id}/rollup")
async def generate_rollup(deal_id: str, user_id: str = Depends(get_current_user_id)):
    deal_raw = await _accessible_deal(deal_id, user_id)
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    deal = Deal.from_mongo(deal_raw)

    completed = []
    async for raw in db.documents.find({"deal_id": deal_id, "status": "completed"}):
        completed.append(Document.from_mongo(raw))

    if not completed:
        raise HTTPException(status_code=400, detail="No completed extractions to roll up. Upload + process at least one PDF first.")

    docs_payload = [
        {"filename": d.filename, "extracted": d.extracted or {}}
        for d in completed
    ]
    rollup = await summarize_deal(
        deal_name=deal.name,
        target_company=deal.target_company,
        sector=deal.sector,
        documents=docs_payload,
    )

    ts = now_iso()
    await db.deals.update_one(
        {"_id": deal_id},
        {"$set": {"rollup": rollup, "rollup_at": ts, "updated_at": ts}},
    )
    return {"rollup": rollup, "rollup_at": ts}


@api.get("/deals/{deal_id}/rollup")
async def get_rollup(deal_id: str, user_id: str = Depends(get_current_user_id)):
    raw = await _accessible_deal(deal_id, user_id)
    return {"rollup": raw.get("rollup"), "rollup_at": raw.get("rollup_at")}


# ---------- Global search ----------
@api.get("/search")
async def global_search(q: str = Query(""), user_id: str = Depends(get_current_user_id)):
    q = (q or "").strip()
    results = {"deals": [], "documents": [], "red_flags": []}
    if len(q) < 2:
        return results

    org_ids = await _user_org_ids(user_id)
    rx = {"$regex": q, "$options": "i"}

    async for raw in db.deals.find(
        {"org_id": {"$in": org_ids}, "$or": [{"name": rx}, {"target_company": rx}, {"sector": rx}]}
    ).limit(8):
        results["deals"].append({
            "id": str(raw["_id"]),
            "name": raw.get("name"),
            "target_company": raw.get("target_company"),
            "sector": raw.get("sector"),
        })

    async for raw in db.documents.find({"org_id": {"$in": org_ids}, "filename": rx}).limit(8):
        results["documents"].append({
            "id": str(raw["_id"]),
            "deal_id": raw.get("deal_id"),
            "filename": raw.get("filename"),
            "status": raw.get("status"),
        })

    q_lower = q.lower()
    flags_found = 0
    async for raw in db.documents.find({"org_id": {"$in": org_ids}, "status": "completed"}):
        if flags_found >= 8:
            break
        for f in (raw.get("extracted") or {}).get("red_flags", []):
            if q_lower in (f.get("title") or "").lower() or q_lower in (f.get("description") or "").lower():
                results["red_flags"].append({
                    "document_id": str(raw["_id"]),
                    "deal_id": raw.get("deal_id"),
                    "filename": raw.get("filename"),
                    "severity": f.get("severity"),
                    "title": f.get("title"),
                    "page": f.get("page"),
                })
                flags_found += 1
                if flags_found >= 8:
                    break

    return results


# ---------- Serve PDF file (iframe needs query token) ----------
@api.get("/documents/{doc_id}/file")
async def get_document_file(
    doc_id: str,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(default=None),
):
    # Accept either header bearer or ?token=
    user_id = None
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
        except HTTPException:
            user_id = None
    if not user_id and authorization and authorization.lower().startswith("bearer "):
        try:
            payload = decode_token(authorization.split(" ", 1)[1].strip())
            user_id = payload.get("sub")
        except HTTPException:
            user_id = None
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    raw = await _accessible_document(doc_id, user_id)
    path = Path(raw["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{raw.get("filename","document.pdf")}"'},
    )


# ---------- Exception passthrough ----------
@app.exception_handler(Exception)
async def unhandled(_, exc):  # noqa: ANN001
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# =============================================================
# Settings (Slack webhook etc.)
# =============================================================
class SettingsUpdate(BaseModel):
    slack_webhook_url: Optional[str] = None
    firm: Optional[str] = None
    name: Optional[str] = None


@api.patch("/auth/settings", response_model=UserPublic)
async def update_settings(payload: SettingsUpdate, user_id: str = Depends(get_current_user_id)):
    update: dict = {}
    if payload.slack_webhook_url is not None:
        url = payload.slack_webhook_url.strip()
        if url and not url.startswith("https://hooks.slack.com/"):
            raise HTTPException(status_code=400, detail="slack_webhook_url must start with https://hooks.slack.com/")
        update["slack_webhook_url"] = url or None
    if payload.firm is not None:
        update["firm"] = payload.firm.strip() or None
    if payload.name is not None and payload.name.strip():
        update["name"] = payload.name.strip()
    if update:
        await db.users.update_one({"_id": user_id}, {"$set": update})
    user = await _find_user_by_id(user_id)
    return user_public(user)


# =============================================================
# Public share — read-only IC memo link
# =============================================================
def _gen_share_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:8]  # 40 chars


def _share_expired(share: dict) -> bool:
    exp = share.get("expires_at")
    if not exp:
        return False
    try:
        return datetime.fromisoformat(exp.replace("Z", "+00:00")) < datetime.now(timezone.utc)
    except Exception:
        return False


class ShareCreate(BaseModel):
    expires_in_days: Optional[int] = None  # None = no expiry
    password: Optional[str] = None


class ShareUnlock(BaseModel):
    password: str


@api.post("/deals/{deal_id}/share")
async def create_share(
    deal_id: str,
    payload: Optional[ShareCreate] = None,
    user_id: str = Depends(get_current_user_id),
):
    deal_raw = await _accessible_deal(deal_id, user_id)
    if not deal_raw.get("rollup"):
        raise HTTPException(status_code=400, detail="Generate the IC roll-up before sharing.")

    payload = payload or ShareCreate()
    expires_at = None
    if payload.expires_in_days and payload.expires_in_days > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)).isoformat()

    password_hash = hash_password(payload.password) if payload.password else None

    # If an existing active share matches the same settings, return it (idempotent).
    # Otherwise revoke and mint a new one (so password/expiry updates take effect).
    existing = await db.shares.find_one({"deal_id": deal_id, "revoked": {"$ne": True}})
    if existing:
        if (
            (existing.get("expires_at") == expires_at)
            and (bool(existing.get("password_hash")) == bool(password_hash))
            and not _share_expired(existing)
        ):
            return _share_out(existing)
        # settings changed → revoke and recreate
        await db.shares.update_one({"_id": existing["_id"]}, {"$set": {"revoked": True}})

    token = _gen_share_token()
    doc = {
        "_id": token,
        "deal_id": deal_id,
        "user_id": user_id,
        "created_at": now_iso(),
        "view_count": 0,
        "revoked": False,
        "expires_at": expires_at,
        "password_hash": password_hash,
    }
    await db.shares.insert_one(doc)
    return _share_out(doc)


def _share_out(share: dict) -> dict:
    return {
        "token": share["_id"],
        "url_path": f"/share/{share['_id']}",
        "created_at": share.get("created_at"),
        "view_count": share.get("view_count", 0),
        "expires_at": share.get("expires_at"),
        "has_password": bool(share.get("password_hash")),
    }


@api.get("/deals/{deal_id}/share")
async def get_share(deal_id: str, user_id: str = Depends(get_current_user_id)):
    await _accessible_deal(deal_id, user_id)
    existing = await db.shares.find_one({"deal_id": deal_id, "revoked": {"$ne": True}})
    if not existing:
        return {"token": None}
    if _share_expired(existing):
        return {"token": None, "expired": True}
    return _share_out(existing)


@api.delete("/deals/{deal_id}/share")
async def revoke_share(deal_id: str, user_id: str = Depends(get_current_user_id)):
    await _accessible_deal(deal_id, user_id)
    await db.shares.update_many({"deal_id": deal_id}, {"$set": {"revoked": True}})
    return {"revoked": True}


@api.get("/share/{token}/meta")
async def share_meta(token: str):
    """Public — lets the viewer know if a password is required & whether the link is alive."""
    share = await db.shares.find_one({"_id": token, "revoked": {"$ne": True}})
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or revoked")
    if _share_expired(share):
        raise HTTPException(status_code=410, detail="This share link has expired")
    deal_raw = await db.deals.find_one({"_id": share["deal_id"]})
    if not deal_raw or not deal_raw.get("rollup"):
        raise HTTPException(status_code=410, detail="The IC memo has been removed")
    return {
        "has_password": bool(share.get("password_hash")),
        "expires_at": share.get("expires_at"),
        "deal_name": deal_raw.get("name"),
        "target_company": deal_raw.get("target_company"),
    }


async def _resolve_share(token: str, password: Optional[str]) -> dict:
    share = await db.shares.find_one({"_id": token, "revoked": {"$ne": True}})
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or revoked")
    if _share_expired(share):
        raise HTTPException(status_code=410, detail="This share link has expired")
    if share.get("password_hash"):
        if not password or not verify_password(password, share["password_hash"]):
            raise HTTPException(status_code=401, detail="Password required or incorrect")
    deal_raw = await db.deals.find_one({"_id": share["deal_id"]})
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal no longer exists")
    if not deal_raw.get("rollup"):
        raise HTTPException(status_code=410, detail="The IC memo has been removed")

    updated = await db.shares.find_one_and_update(
        {"_id": token},
        {"$inc": {"view_count": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return {
        "deal": {
            "name": deal_raw.get("name"),
            "target_company": deal_raw.get("target_company"),
            "sector": deal_raw.get("sector"),
            "deal_size": deal_raw.get("deal_size"),
        },
        "rollup": deal_raw.get("rollup"),
        "rollup_at": deal_raw.get("rollup_at"),
        "shared_at": share.get("created_at"),
        "expires_at": share.get("expires_at"),
        "view_count": (updated or share).get("view_count", 1),
    }


@api.get("/share/{token}")
async def view_share(token: str):
    return await _resolve_share(token, None)


@api.post("/share/{token}/unlock")
async def unlock_share(token: str, payload: ShareUnlock):
    return await _resolve_share(token, payload.password)


# =============================================================
# Stripe Checkout
# =============================================================
class CheckoutCreateRequest(BaseModel):
    package_id: str
    origin_url: str


@api.get("/payments/packages")
async def list_packages():
    return {
        "packages": [
            {"id": pid, "amount": p["amount"], "currency": p["currency"], "label": p["label"], "plan": p["plan"]}
            for pid, p in PACKAGES.items()
        ]
    }


@api.post("/payments/checkout/session")
async def create_checkout_session(payload: CheckoutCreateRequest, request: Request, user_id: str = Depends(get_current_user_id)):
    pkg = get_package(payload.package_id)
    if not pkg:
        raise HTTPException(status_code=400, detail="Unknown package")

    origin = payload.origin_url.rstrip("/")
    host_url = str(request.base_url)
    stripe = make_checkout(host_url)

    success_url = f"{origin}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/billing/cancel"

    metadata = {"user_id": user_id, "package_id": payload.package_id, "plan": pkg["plan"]}
    req = CheckoutSessionRequest(
        amount=pkg["amount"],
        currency=pkg["currency"],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata,
    )
    session = await stripe.create_checkout_session(req)

    await db.payment_transactions.insert_one(
        {
            "_id": session.session_id,
            "user_id": user_id,
            "package_id": payload.package_id,
            "plan": pkg["plan"],
            "amount": pkg["amount"],
            "currency": pkg["currency"],
            "metadata": metadata,
            "payment_status": "initiated",
            "status": "open",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    return {"url": session.url, "session_id": session.session_id}


@api.get("/payments/checkout/status/{session_id}")
async def checkout_status(session_id: str, request: Request, user_id: str = Depends(get_current_user_id)):
    txn = await db.payment_transactions.find_one({"_id": session_id})
    if not txn or txn.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # If we already finalized, return the persisted record (idempotent)
    if txn.get("payment_status") == "paid":
        return {
            "session_id": session_id,
            "status": txn.get("status"),
            "payment_status": txn.get("payment_status"),
            "amount_total": int(txn.get("amount", 0) * 100),
            "currency": txn.get("currency", "usd"),
            "plan": txn.get("plan"),
            "already_processed": True,
        }

    stripe = make_checkout(str(request.base_url))
    status_resp = await stripe.get_checkout_status(session_id)

    new_payment_status = status_resp.payment_status
    new_status = status_resp.status

    update = {"payment_status": new_payment_status, "status": new_status, "updated_at": now_iso()}

    if new_payment_status == "paid" and txn.get("payment_status") != "paid":
        # First time we see it paid — upgrade user plan
        update["paid_at"] = now_iso()
        await db.users.update_one(
            {"_id": user_id},
            {"$set": {"plan": txn.get("plan", "desk"), "plan_active_until": _plan_end(txn.get("package_id"))}},
        )

    await db.payment_transactions.update_one({"_id": session_id}, {"$set": update})

    return {
        "session_id": session_id,
        "status": new_status,
        "payment_status": new_payment_status,
        "amount_total": status_resp.amount_total,
        "currency": status_resp.currency,
        "plan": txn.get("plan"),
        "already_processed": False,
    }


def _plan_end(package_id: Optional[str]) -> str:
    """Return ISO string for plan expiry — monthly = +30d, annual = +365d."""
    days = 365 if (package_id or "").endswith("annual") else 30
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    stripe = make_checkout(str(request.base_url))
    try:
        evt = await stripe.handle_webhook(body, sig)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stripe webhook verify failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook")

    event_id = getattr(evt, "event_id", None)
    session_id = getattr(evt, "session_id", None)
    payment_status = getattr(evt, "payment_status", None)

    # Replay protection — reject duplicate event_id (idempotency)
    if event_id:
        seen = await db.stripe_events.find_one({"_id": event_id})
        if seen:
            logger.info("Stripe webhook replay ignored: %s", event_id)
            return {"ok": True, "replayed": True}
        try:
            await db.stripe_events.insert_one({
                "_id": event_id,
                "session_id": session_id,
                "event_type": getattr(evt, "event_type", None),
                "received_at": now_iso(),
            })
        except Exception:
            # If another worker inserted the same event between our check and insert,
            # treat as replay (race condition is rare but possible).
            return {"ok": True, "replayed": True}

    if not session_id:
        return {"ok": True}

    txn = await db.payment_transactions.find_one({"_id": session_id})
    if not txn:
        return {"ok": True}

    if payment_status == "paid" and txn.get("payment_status") != "paid":
        await db.payment_transactions.update_one(
            {"_id": session_id},
            {"$set": {"payment_status": "paid", "status": "complete", "paid_at": now_iso(), "updated_at": now_iso()}},
        )
        await db.users.update_one(
            {"_id": txn["user_id"]},
            {"$set": {"plan": txn.get("plan", "desk"), "plan_active_until": _plan_end(txn.get("package_id"))}},
        )
    return {"ok": True}


# (org routes appended below; app.include_router(api) is called once at the very end)


# =============================================================
# Organizations / Teams — multi-seat workspaces
# =============================================================
class OrgUpdate(BaseModel):
    name: Optional[str] = None


class OrgInviteCreate(BaseModel):
    email: EmailStr
    role: str = "member"  # member | admin


class OrgMemberUpdate(BaseModel):
    role: str  # admin | member


@api.get("/orgs/current")
async def get_current_org(user_id: str = Depends(get_current_user_id)):
    org_id = await _ensure_user_org(user_id)
    org = await db.organizations.find_one({"_id": org_id})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")

    members = []
    async for m in db.org_members.find({"org_id": org_id}):
        u = await db.users.find_one({"_id": m["user_id"]})
        members.append({
            "user_id": m["user_id"],
            "role": m.get("role"),
            "joined_at": m.get("joined_at"),
            "email": (u or {}).get("email"),
            "name": (u or {}).get("name"),
        })
    invites = []
    async for inv in db.org_invites.find({"org_id": org_id, "accepted_at": None, "revoked": {"$ne": True}}):
        invites.append({
            "id": str(inv["_id"]),
            "email": inv.get("email"),
            "role": inv.get("role"),
            "created_at": inv.get("created_at"),
        })

    my_role = next((m["role"] for m in members if m["user_id"] == user_id), "member")
    return {
        "id": org["_id"],
        "name": org.get("name"),
        "owner_id": org.get("owner_id"),
        "plan": org.get("plan", "trial"),
        "plan_active_until": org.get("plan_active_until"),
        "my_role": my_role,
        "members": members,
        "pending_invites": invites,
    }


@api.patch("/orgs/current")
async def update_org(payload: OrgUpdate, user_id: str = Depends(get_current_user_id)):
    org_id = await _ensure_user_org(user_id)
    await _require_org_role(org_id, user_id, roles=["owner", "admin"])
    update = {}
    if payload.name is not None and payload.name.strip():
        update["name"] = payload.name.strip()
    if update:
        await db.organizations.update_one({"_id": org_id}, {"$set": update})
    return await get_current_org(user_id=user_id)  # type: ignore


@api.post("/orgs/current/invites")
async def create_invite(payload: OrgInviteCreate, user_id: str = Depends(get_current_user_id)):
    org_id = await _ensure_user_org(user_id)
    await _require_org_role(org_id, user_id, roles=["owner", "admin"])
    if payload.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="role must be admin or member")

    email = payload.email.lower()
    # Self-invite guard
    me = await db.users.find_one({"_id": user_id})
    if me and email == (me.get("email") or "").lower():
        raise HTTPException(status_code=400, detail="You cannot invite yourself")
    # If user is already a member, short-circuit
    existing_user = await db.users.find_one({"email": email})
    if existing_user:
        already = await db.org_members.find_one({"org_id": org_id, "user_id": existing_user["_id"]})
        if already:
            raise HTTPException(status_code=400, detail="User is already a member of this organization")

    # Revoke any prior pending invite to the same email for this org (idempotent re-invite)
    await db.org_invites.update_many(
        {"org_id": org_id, "email": email, "accepted_at": None, "revoked": {"$ne": True}},
        {"$set": {"revoked": True}},
    )

    token = uuid.uuid4().hex
    await db.org_invites.insert_one({
        "_id": token,
        "org_id": org_id,
        "email": email,
        "role": payload.role,
        "invited_by": user_id,
        "accepted_at": None,
        "revoked": False,
        "created_at": now_iso(),
    })
    org = await db.organizations.find_one({"_id": org_id})
    return {
        "token": token,
        "url_path": f"/invite/{token}",
        "email": email,
        "role": payload.role,
        "org_name": (org or {}).get("name"),
    }


@api.delete("/orgs/current/invites/{invite_id}")
async def revoke_invite(invite_id: str, user_id: str = Depends(get_current_user_id)):
    org_id = await _ensure_user_org(user_id)
    await _require_org_role(org_id, user_id, roles=["owner", "admin"])
    res = await db.org_invites.update_one(
        {"_id": invite_id, "org_id": org_id},
        {"$set": {"revoked": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"revoked": True}


@api.get("/invites/{token}")
async def get_invite(token: str):
    """Public — lets the invitee see what they're being invited to before logging in."""
    inv = await db.org_invites.find_one({"_id": token, "revoked": {"$ne": True}, "accepted_at": None})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found, revoked, or already accepted")
    org = await db.organizations.find_one({"_id": inv["org_id"]})
    inviter = await db.users.find_one({"_id": inv["invited_by"]})
    return {
        "token": token,
        "email": inv.get("email"),
        "role": inv.get("role"),
        "org_id": inv.get("org_id"),
        "org_name": (org or {}).get("name"),
        "invited_by": (inviter or {}).get("name") or (inviter or {}).get("email"),
        "created_at": inv.get("created_at"),
    }


@api.post("/invites/{token}/accept")
async def accept_invite(token: str, user_id: str = Depends(get_current_user_id)):
    inv = await db.org_invites.find_one({"_id": token, "revoked": {"$ne": True}, "accepted_at": None})
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found, revoked, or already accepted")

    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("email", "").lower() != inv.get("email", "").lower():
        raise HTTPException(status_code=403, detail="This invite is for a different email address")

    org_id = inv["org_id"]
    already = await db.org_members.find_one({"org_id": org_id, "user_id": user_id})
    if not already:
        await db.org_members.insert_one({
            "_id": str(uuid.uuid4()),
            "org_id": org_id,
            "user_id": user_id,
            "role": inv.get("role", "member"),
            "joined_at": now_iso(),
        })

    await db.org_invites.update_one(
        {"_id": token},
        {"$set": {"accepted_at": now_iso()}},
    )
    # Switch user's active workspace to the new org
    await db.users.update_one({"_id": user_id}, {"$set": {"current_org_id": org_id}})
    org = await db.organizations.find_one({"_id": org_id})
    return {
        "joined_org_id": org_id,
        "joined_org_name": (org or {}).get("name"),
        "role": inv.get("role", "member"),
    }


@api.patch("/orgs/current/members/{member_user_id}")
async def update_member(member_user_id: str, payload: OrgMemberUpdate, user_id: str = Depends(get_current_user_id)):
    org_id = await _ensure_user_org(user_id)
    await _require_org_role(org_id, user_id, roles=["owner"])
    if payload.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="role must be admin or member")
    if member_user_id == user_id:
        raise HTTPException(status_code=400, detail="Owner cannot demote themselves")
    res = await db.org_members.update_one(
        {"org_id": org_id, "user_id": member_user_id},
        {"$set": {"role": payload.role}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"updated": True}


@api.delete("/orgs/current/members/{member_user_id}")
async def remove_member(member_user_id: str, user_id: str = Depends(get_current_user_id)):
    org_id = await _ensure_user_org(user_id)
    await _require_org_role(org_id, user_id, roles=["owner", "admin"])
    if member_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself; transfer ownership first")
    target = await db.org_members.find_one({"org_id": org_id, "user_id": member_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the owner")
    await db.org_members.delete_one({"org_id": org_id, "user_id": member_user_id})
    # If the removed user's current_org_id was this org, fall back to their personal org
    other = await db.org_members.find_one({"user_id": member_user_id})
    fallback = other["org_id"] if other else None
    if not fallback:
        # Re-provision a personal org for them
        fallback = await _ensure_user_org(member_user_id)
    await db.users.update_one(
        {"_id": member_user_id, "current_org_id": org_id},
        {"$set": {"current_org_id": fallback}},
    )
    return {"removed": True}


@api.get("/orgs/me/orgs")
async def list_my_orgs(user_id: str = Depends(get_current_user_id)):
    await _ensure_user_org(user_id)
    out = []
    async for m in db.org_members.find({"user_id": user_id}):
        org = await db.organizations.find_one({"_id": m["org_id"]})
        if not org:
            continue
        out.append({
            "id": org["_id"],
            "name": org.get("name"),
            "role": m.get("role"),
            "owner_id": org.get("owner_id"),
            "plan": org.get("plan", "trial"),
        })
    return {"orgs": out}


@api.post("/orgs/switch/{org_id}")
async def switch_org(org_id: str, user_id: str = Depends(get_current_user_id)):
    m = await db.org_members.find_one({"org_id": org_id, "user_id": user_id})
    if not m:
        raise HTTPException(status_code=404, detail="Not a member of this organization")
    await db.users.update_one({"_id": user_id}, {"$set": {"current_org_id": org_id}})
    return {"current_org_id": org_id}


app.include_router(api)

# =============================================================
# Analysis Terminal · CSV Export · Highlighting & Provenance
# (Core Backend Integration blueprint — Features 1, 2, 3)
# =============================================================
import base64 as _b64

ANALYZE_ROUTER = APIRouter(prefix="/api")


class AnalyzeRequest(BaseModel):
    question: str
    doc_scope: List[str]
    n_results: int = 2


class ExportTableRequest(BaseModel):
    answer: str
    row_pages: Optional[List[Optional[int]]] = None
    row_docs: Optional[List[Optional[str]]] = None
    row_reasoning: Optional[List[str]] = None


class HighlightRequest(BaseModel):
    doc_name: str
    page_num: int
    search_terms: List[str] = []


class PageTextRequest(BaseModel):
    doc_name: str
    page_num: int


async def _resolve_scope_docs(doc_ids: List[str], user_id: str) -> list[dict]:
    org_ids = await _user_org_ids(user_id)
    out: list[dict] = []
    for did in doc_ids:
        raw = await db.documents.find_one({"_id": did})
        if not raw:
            continue
        if raw.get("org_id") in org_ids:
            ok = True
        else:
            deal = await db.deals.find_one({"_id": raw.get("deal_id")})
            ok = bool(deal and deal.get("org_id") in org_ids)
        if not ok:
            continue
        out.append({"doc_name": did, "pdf_path": raw.get("file_path", "")})
    return out


@ANALYZE_ROUTER.post("/analyze")
async def analyze(req: AnalyzeRequest, user_id: str = Depends(get_current_user_id)):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    if not req.doc_scope:
        raise HTTPException(status_code=400, detail="doc_scope must contain at least one document id")

    docs = await _resolve_scope_docs(req.doc_scope, user_id)
    if not docs:
        return JSONResponse(
            status_code=422,
            content={"error": "No relevant pages found.", "cited_pages": [], "is_verified": False},
        )

    # Resolve each doc's local file path and assign a short label (1, 2, 3, ...).
    pdf_paths: List[str] = []
    doc_labels: List[str] = []
    label_to_doc: Dict[str, str] = {}
    for idx, d in enumerate(docs, start=1):
        path = (d.get("pdf_path") or "").strip()
        if not path or not Path(path).is_file():
            logger.warning("analyze: skipping doc %s missing file %s", d.get("doc_name"), path)
            continue
        label = str(idx)
        pdf_paths.append(path)
        doc_labels.append(label)
        label_to_doc[label] = d["doc_name"]

    if not pdf_paths:
        return JSONResponse(
            status_code=422,
            content={"error": "Document files not found on server.", "cited_pages": [], "is_verified": False},
        )

    # Build minimal deal context (best-effort)
    deal_ctx: Optional[str] = None
    first_raw = await db.documents.find_one({"_id": docs[0]["doc_name"]})
    if first_raw and first_raw.get("deal_id"):
        deal = await db.deals.find_one({"_id": first_raw["deal_id"]})
        if deal:
            deal_ctx = (
                f"Deal: {deal.get('name', '')}\n"
                f"Target: {deal.get('target_company', '')}\n"
                f"Sector: {deal.get('sector', '')}"
            )

    try:
        answer = await answer_question_with_pdf(
            req.question, pdf_paths, context=deal_ctx, doc_labels=doc_labels
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("answer_question_with_pdf failed")
        raise HTTPException(status_code=502, detail=f"Gemini call failed: {exc}")

    # Parse `[Doc <label> · p.N]` citations from the answer text.
    citation_re = re.compile(r"\[Doc\s+([A-Za-z0-9_\-]+)\s*[·\.\-]\s*p\.?\s*(\d+)\]", re.IGNORECASE)
    cited_pairs: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for m in citation_re.finditer(answer or ""):
        label, page = m.group(1), int(m.group(2))
        doc_id = label_to_doc.get(label)
        if doc_id is None:
            continue
        key = (doc_id, page)
        if key in seen:
            continue
        seen.add(key)
        cited_pairs.append(key)

    cited_pages_sorted = sorted({p for _, p in cited_pairs})
    first_chunk_page = cited_pages_sorted[0] if cited_pages_sorted else None

    # Build chunks (page text) for the cited pages so table provenance can resolve rows.
    enriched_chunks: list[dict] = []
    doc_id_to_path = {label_to_doc[lbl]: pdf_paths[i] for i, lbl in enumerate(doc_labels)}
    for doc_id, page in cited_pairs:
        path = doc_id_to_path.get(doc_id)
        if not path:
            continue
        try:
            text = extract_page_text(path, page) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("extract_page_text(%s, %s) failed: %s", path, page, exc)
            text = ""
        enriched_chunks.append({"doc_name": doc_id, "page_num": page, "text": text})

    # Resolve per-row provenance against the table (if any).
    table_md = extract_table_from_answer(answer or "")
    row_pages: list = []
    row_docs: list = []
    highlight_terms_by_page: Dict[str, list] = {}
    prov_cited_pages: list[int] = []
    if table_md and enriched_chunks:
        prov = resolve_table_provenance(table_md, enriched_chunks)
        row_pages = prov.get("row_pages", []) or []
        row_docs = prov.get("row_docs", []) or []
        highlight_terms_by_page = prov.get("highlight_terms_by_page", {}) or {}
        prov_cited_pages = prov.get("cited_pages", []) or []

    # row_reasoning from `## Row Reasoning` section if present
    row_reasoning: list[str] = []
    if table_md:
        try:
            row_reasoning = _extract_row_reasoning(answer or "", num_rows=len(row_pages) or 0)
        except Exception:  # noqa: BLE001
            row_reasoning = []

    merged_cited = sorted(set(cited_pages_sorted) | set(prov_cited_pages))

    return {
        "answer": answer,
        "is_verified": True,
        "cited_pages": merged_cited,
        "provenance_cited_pages": prov_cited_pages,
        "row_pages": row_pages,
        "row_docs": row_docs,
        "row_reasoning": row_reasoning,
        "highlight_terms_by_page": highlight_terms_by_page,
        "first_chunk_page": first_chunk_page,
    }


@ANALYZE_ROUTER.post("/export-table")
async def export_table(req: ExportTableRequest, user_id: str = Depends(get_current_user_id)):
    from provenance import extract_table_from_answer as _xt

    table_md = _xt(req.answer or "")
    if not table_md:
        raise HTTPException(status_code=400, detail="No Markdown table found in answer")

    csv_data = markdown_table_to_csv(
        table_md,
        row_pages=req.row_pages,
        row_docs=req.row_docs,
        row_reasoning=req.row_reasoning,
    )
    if not csv_data:
        raise HTTPException(status_code=500, detail="CSV serialization produced empty output")

    first_page = next((p for p in (req.row_pages or []) if isinstance(p, int)), None)
    filename = f"table_p{first_page}.csv" if first_page is not None else "table.csv"
    row_count = max(0, csv_data.count("\n") - 1)
    has_unresolved = "Unresolved" in csv_data
    return {
        "csv_data": csv_data,
        "filename": filename,
        "row_count": row_count,
        "has_unresolved": has_unresolved,
    }


async def _authorized_doc_pdf(doc_id: str, user_id: str) -> tuple[str, str]:
    raw = await _accessible_document(doc_id, user_id)
    return raw.get("file_path", ""), raw.get("filename", doc_id)


@ANALYZE_ROUTER.post("/highlight-page")
async def highlight_page(req: HighlightRequest, user_id: str = Depends(get_current_user_id)):
    pdf_path, _filename = await _authorized_doc_pdf(req.doc_name, user_id)
    if not pdf_path:
        raise HTTPException(status_code=404, detail="Document file not available")
    png, quads = render_page_with_highlights(pdf_path, req.page_num, req.search_terms)
    if not png:
        return {"page_png_b64": "", "quad_count": 0, "page_num": req.page_num, "doc_name": req.doc_name}
    return {
        "page_png_b64": _b64.b64encode(png).decode("ascii"),
        "quad_count": quads,
        "page_num": req.page_num,
        "doc_name": req.doc_name,
    }


@ANALYZE_ROUTER.post("/highlight-thumbnail")
async def highlight_thumbnail(req: HighlightRequest, user_id: str = Depends(get_current_user_id)):
    pdf_path, _filename = await _authorized_doc_pdf(req.doc_name, user_id)
    if not pdf_path:
        raise HTTPException(status_code=404, detail="Document file not available")
    png = render_thumbnail(pdf_path, req.page_num, req.search_terms)
    return {
        "thumbnail_png_b64": _b64.b64encode(png).decode("ascii") if png else "",
        "page_num": req.page_num,
    }


@ANALYZE_ROUTER.post("/page-text")
async def page_text(req: PageTextRequest, user_id: str = Depends(get_current_user_id)):
    pdf_path, _filename = await _authorized_doc_pdf(req.doc_name, user_id)
    if not pdf_path:
        raise HTTPException(status_code=404, detail="Document file not available")
    text = extract_page_text(pdf_path, req.page_num)
    return {
        "text": text or "",
        "has_text_layer": bool(text and text.strip()),
        "page_count": pdf_page_count(pdf_path),
    }


app.include_router(ANALYZE_ROUTER)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
