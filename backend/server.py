"""ClearVault — FastAPI backend."""
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from ai_service import extract_pdf  # noqa: E402
from auth import create_token, get_current_user_id, hash_password, verify_password  # noqa: E402
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


# ---------- Exception passthrough ----------
@app.exception_handler(Exception)
async def unhandled(_, exc):  # noqa: ANN001
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


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
