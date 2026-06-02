"""MongoDB document models for ClearVault."""
from datetime import datetime, timezone
from typing import Any, List, Optional
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, EmailStr
from typing_extensions import Annotated


def _validate_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        return v
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[str, BeforeValidator(_validate_object_id)]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        return data

    @classmethod
    def from_mongo(cls, doc: dict) -> "BaseDocument":
        if not doc:
            return None
        doc = dict(doc)
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return cls(**doc)


# ---------- User ----------
class User(BaseDocument):
    email: EmailStr
    name: str
    password_hash: str
    firm: Optional[str] = None
    role: str = "analyst"
    plan: str = "trial"  # trial | desk | firm
    plan_active_until: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    current_org_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str
    firm: Optional[str] = None
    role: str
    plan: str = "trial"
    plan_active_until: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    current_org_id: Optional[str] = None
    created_at: str


class SignupRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    firm: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


# ---------- Deal ----------
class Deal(BaseDocument):
    user_id: str  # original creator
    org_id: Optional[str] = None  # owning organization
    name: str
    target_company: str
    sector: str = "Industrials"
    deal_size: Optional[str] = None  # e.g. "$45M"
    stage: str = "due_diligence"  # due_diligence | review | closed | flagged
    status: str = "active"
    rollup: Optional[dict] = None
    rollup_at: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# ---------- Organization ----------
class Organization(BaseDocument):
    name: str
    owner_id: str
    plan: str = "trial"
    plan_active_until: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class OrgMember(BaseDocument):
    org_id: str
    user_id: str
    role: str = "member"  # owner | admin | member
    joined_at: str = Field(default_factory=now_iso)


class OrgInvite(BaseDocument):
    org_id: str
    email: EmailStr
    role: str = "member"
    invited_by: str
    accepted_at: Optional[str] = None
    revoked: bool = False
    created_at: str = Field(default_factory=now_iso)


class DealCreate(BaseModel):
    name: str
    target_company: str
    sector: Optional[str] = "Industrials"
    deal_size: Optional[str] = None


class DealOut(BaseModel):
    id: str
    name: str
    target_company: str
    sector: str
    deal_size: Optional[str]
    stage: str
    status: str
    created_at: str
    updated_at: str
    documents_count: Optional[int] = 0
    red_flags_count: Optional[int] = 0


# ---------- Document ----------
class Document(BaseDocument):
    user_id: str
    deal_id: str
    filename: str
    file_path: str
    file_size: int
    mime_type: str = "application/pdf"
    status: str = "uploaded"  # uploaded | processing | completed | failed
    error: Optional[str] = None
    extracted: Optional[dict] = None  # full structured extraction blob
    created_at: str = Field(default_factory=now_iso)
    processed_at: Optional[str] = None


class DocumentOut(BaseModel):
    id: str
    deal_id: str
    filename: str
    file_size: int
    status: str
    error: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    extracted: Optional[dict] = None


class ExtractedData(BaseModel):
    """Schema returned by the AI parser."""
    document_type: str
    summary: str
    financial_metrics: List[dict] = []  # [{label, value, period, notes}]
    key_terms: List[dict] = []  # [{label, value, notes}]
    red_flags: List[dict] = []  # [{severity, title, description, page}]
    parties: List[str] = []
    confidence: float = 0.85
