"""ClearVault — FastAPI backend."""
import csv
import io
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo import ReturnDocument
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from ai_service import extract_pdf, summarize_deal  # noqa: E402
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
        created_at=user.created_at,
    )


async def _find_user_by_id(user_id: str) -> User:
    doc = await db.users.find_one({"_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return User.from_mongo(doc)


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
    token = create_token(user.id, user.email)
    return AuthResponse(token=token, user=user_public(user))


@api.get("/auth/me", response_model=UserPublic)
async def me(user_id: str = Depends(get_current_user_id)):
    user = await _find_user_by_id(user_id)
    return user_public(user)


# ---------- Dashboard ----------
@api.get("/dashboard/stats")
async def dashboard_stats(user_id: str = Depends(get_current_user_id)):
    deals_total = await db.deals.count_documents({"user_id": user_id})
    deals_active = await db.deals.count_documents({"user_id": user_id, "status": "active"})
    docs_total = await db.documents.count_documents({"user_id": user_id})
    docs_completed = await db.documents.count_documents({"user_id": user_id, "status": "completed"})

    # aggregate red flags across all completed extractions for this user
    red_flags_total = 0
    high_severity = 0
    async for d in db.documents.find({"user_id": user_id, "status": "completed"}):
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
    out: List[DealOut] = []
    cursor = db.deals.find({"user_id": user_id}).sort("created_at", -1)
    async for raw in cursor:
        deal = Deal.from_mongo(raw)
        out.append(await _deal_out(deal))
    return out


@api.post("/deals", response_model=DealOut)
async def create_deal(payload: DealCreate, user_id: str = Depends(get_current_user_id)):
    deal = Deal(
        user_id=user_id,
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
    raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
    if not raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    return await _deal_out(Deal.from_mongo(raw))


@api.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, user_id: str = Depends(get_current_user_id)):
    res = await db.deals.delete_one({"_id": deal_id, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Deal not found")
    # also delete child documents
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
    deal_raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
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
    )
    doc_dict = document.to_mongo()
    doc_dict["_id"] = new_id
    await db.documents.insert_one(doc_dict)
    document.id = new_id

    background.add_task(_process_document, new_id)
    return _doc_out(document)


@api.get("/deals/{deal_id}/documents", response_model=List[DocumentOut])
async def list_documents(deal_id: str, user_id: str = Depends(get_current_user_id)):
    deal_raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    out: List[DocumentOut] = []
    cursor = db.documents.find({"deal_id": deal_id}).sort("created_at", -1)
    async for raw in cursor:
        out.append(_doc_out(Document.from_mongo(raw)))
    return out


@api.get("/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, user_id: str = Depends(get_current_user_id)):
    raw = await db.documents.find_one({"_id": doc_id, "user_id": user_id})
    if not raw:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_out(Document.from_mongo(raw))


@api.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user_id: str = Depends(get_current_user_id)):
    raw = await db.documents.find_one({"_id": doc_id, "user_id": user_id})
    if not raw:
        raise HTTPException(status_code=404, detail="Document not found")
    # remove file
    try:
        Path(raw["file_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    await db.documents.delete_one({"_id": doc_id})
    return {"deleted": True}


# ---------- Recent activity ----------
@api.get("/activity/recent")
async def recent_activity(user_id: str = Depends(get_current_user_id), limit: int = 8):
    items = []
    async for raw in db.documents.find({"user_id": user_id}).sort("created_at", -1).limit(limit):
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
    deal_raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
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
    deal_raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
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
    raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
    if not raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"rollup": raw.get("rollup"), "rollup_at": raw.get("rollup_at")}


# ---------- Global search ----------
@api.get("/search")
async def global_search(q: str = Query(""), user_id: str = Depends(get_current_user_id)):
    q = (q or "").strip()
    results = {"deals": [], "documents": [], "red_flags": []}
    if len(q) < 2:
        return results

    rx = {"$regex": q, "$options": "i"}

    async for raw in db.deals.find(
        {"user_id": user_id, "$or": [{"name": rx}, {"target_company": rx}, {"sector": rx}]}
    ).limit(8):
        results["deals"].append({
            "id": str(raw["_id"]),
            "name": raw.get("name"),
            "target_company": raw.get("target_company"),
            "sector": raw.get("sector"),
        })

    async for raw in db.documents.find({"user_id": user_id, "filename": rx}).limit(8):
        results["documents"].append({
            "id": str(raw["_id"]),
            "deal_id": raw.get("deal_id"),
            "filename": raw.get("filename"),
            "status": raw.get("status"),
        })

    # red flag search: scan extracted titles
    q_lower = q.lower()
    flags_found = 0
    async for raw in db.documents.find({"user_id": user_id, "status": "completed"}):
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

    raw = await db.documents.find_one({"_id": doc_id, "user_id": user_id})
    if not raw:
        raise HTTPException(status_code=404, detail="Document not found")
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


@api.post("/deals/{deal_id}/share")
async def create_share(deal_id: str, user_id: str = Depends(get_current_user_id)):
    deal_raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    if not deal_raw.get("rollup"):
        raise HTTPException(status_code=400, detail="Generate the IC roll-up before sharing.")

    existing = await db.shares.find_one({"deal_id": deal_id, "revoked": {"$ne": True}})
    if existing:
        return {
            "token": existing["_id"],
            "url_path": f"/share/{existing['_id']}",
            "created_at": existing.get("created_at"),
            "view_count": existing.get("view_count", 0),
        }

    token = _gen_share_token()
    await db.shares.insert_one(
        {
            "_id": token,
            "deal_id": deal_id,
            "user_id": user_id,
            "created_at": now_iso(),
            "view_count": 0,
            "revoked": False,
        }
    )
    return {"token": token, "url_path": f"/share/{token}", "created_at": now_iso(), "view_count": 0}


@api.get("/deals/{deal_id}/share")
async def get_share(deal_id: str, user_id: str = Depends(get_current_user_id)):
    existing = await db.shares.find_one({"deal_id": deal_id, "user_id": user_id, "revoked": {"$ne": True}})
    if not existing:
        return {"token": None}
    return {
        "token": existing["_id"],
        "url_path": f"/share/{existing['_id']}",
        "created_at": existing.get("created_at"),
        "view_count": existing.get("view_count", 0),
    }


@api.delete("/deals/{deal_id}/share")
async def revoke_share(deal_id: str, user_id: str = Depends(get_current_user_id)):
    deal_raw = await db.deals.find_one({"_id": deal_id, "user_id": user_id})
    if not deal_raw:
        raise HTTPException(status_code=404, detail="Deal not found")
    await db.shares.update_many({"deal_id": deal_id, "user_id": user_id}, {"$set": {"revoked": True}})
    return {"revoked": True}


@api.get("/share/{token}")
async def view_share(token: str):
    share = await db.shares.find_one({"_id": token, "revoked": {"$ne": True}})
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or revoked")
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
        "view_count": (updated or share).get("view_count", 1),
    }


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
    from datetime import datetime, timedelta, timezone
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

    session_id = getattr(evt, "session_id", None)
    payment_status = getattr(evt, "payment_status", None)
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


app.include_router(api)

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
