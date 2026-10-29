import hashlib
import json
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from . import audit, storage
from . import engine as verification
from .config import (ALLOW_REGISTRATION, CORS_ORIGIN_REGEX, CORS_ORIGINS, DEMO_PASSWORD, MAX_ROWS, MAX_UPLOAD_MB,
                     SEED_DEMO)
from .db import Base, engine as db_engine, get_db
from .models import AuditLog, Engagement, Finding, Receivable, Upload, User, utcnow
from .report import build_pdf
from .security import create_token, get_current_user, hash_password, require_roles, verify_password
from .seed import seed_demo

FINDING_STATUSES = ["OPEN", "UNDER_REVIEW", "RESOLVED", "FALSE_POSITIVE"]
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


_ready = False
_ready_lock = threading.Lock()


def ensure_ready() -> None:
    """Create tables (and demo data) once per process. Runs at startup and, for hosts that skip the ASGI
    lifespan (serverless), lazily on the first request."""
    global _ready
    if _ready:
        return
    with _ready_lock:
        if _ready:
            return
        with db_engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(727000)"))  # concurrent cold starts
            Base.metadata.create_all(conn)
        if SEED_DEMO:
            seed_demo()
        _ready = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_ready()
    yield


app = FastAPI(title="Receivables Registry (MVP)", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_origin_regex=CORS_ORIGIN_REGEX,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def lazy_init(request, call_next):
    await run_in_threadpool(ensure_ready)
    return await call_next(request)


@app.get("/config")
def public_config():
    """What the login page needs to know."""
    return {"allow_registration": ALLOW_REGISTRATION, "demo_accounts": SEED_DEMO and DEMO_PASSWORD == "demo1234"}


# --------------------------------------------------------------------------- helpers

def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role}


def load_engagement(db: Session, user: User, eid: int) -> Engagement:
    e = db.get(Engagement, eid)
    allowed = e is not None and (
        user.role == "admin"
        or (user.role == "bank" and e.bank_id == user.id)
        or (user.role == "client" and e.client_email == user.email)
    )
    if not allowed:  # 404 on purpose: do not reveal which IDs exist
        raise HTTPException(404, "Engagement not found")
    return e


def load_upload(db: Session, user: User, uid: int) -> tuple[Upload, Engagement]:
    u = db.get(Upload, uid)
    if u is None:
        raise HTTPException(404, "Verification run not found")
    return u, load_engagement(db, user, u.engagement_id)


def upload_out(u: Upload) -> dict:
    return {
        "id": u.id, "engagement_id": u.engagement_id, "filename": u.filename, "file_sha256": u.file_sha256,
        "n_rows": u.n_rows, "verdict": u.verdict, "summary": json.loads(u.summary),
        "mapping": json.loads(u.mapping), "declaration_accepted": u.declaration_accepted,
        "created_at": iso(u.created_at),
    }


def finding_out(f: Finding) -> dict:
    rows = json.loads(f.rows)
    return {
        "id": f.id, "upload_id": f.upload_id, "kind": f.kind, "code": f.code, "severity": f.severity,
        "title": f.title, "description": f.description, "rows_count": len(rows), "rows_preview": rows[:20],
        "status": f.status, "note": f.note, "updated_by": f.updated_by, "updated_at": iso(f.updated_at),
    }


def engagement_out(db: Session, e: Engagement) -> dict:
    bank = db.get(User, e.bank_id)
    latest = db.execute(
        select(Upload).where(Upload.engagement_id == e.id).order_by(Upload.id.desc()).limit(1)
    ).scalar_one_or_none()
    open_findings = 0
    if latest:
        open_findings = db.execute(
            select(func.count(Finding.id)).where(
                Finding.upload_id == latest.id, Finding.status.in_(["OPEN", "UNDER_REVIEW"]),
                Finding.kind != verification.KIND_DQ)
        ).scalar_one()
    return {
        "id": e.id, "name": e.name, "client_email": e.client_email,
        "bank": {"id": bank.id, "name": bank.name, "email": bank.email} if bank else None,
        "created_at": iso(e.created_at),
        "latest_upload": ({"id": latest.id, "filename": latest.filename, "verdict": latest.verdict,
                           "created_at": iso(latest.created_at)} if latest else None),
        "open_duplicate_findings": open_findings,
    }


# --------------------------------------------------------------------------- auth

class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern="^(client|bank)$")


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "Registration is closed")
    email = body.email.strip().lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(409, "An account with this email already exists")
    u = User(email=email, name=body.name.strip(), role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.log(db, actor=u.email, action="user.created", entity="user", entity_id=u.id, details={"role": u.role})
    db.commit()
    return {"access_token": create_token(u), "user": user_out(u)}


@app.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.execute(select(User).where(User.email == body.email.strip().lower())).scalar_one_or_none()
    if u is None or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    audit.log(db, actor=u.email, action="user.login", entity="user", entity_id=u.id)
    db.commit()
    return {"access_token": create_token(u), "user": user_out(u)}


@app.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


# --------------------------------------------------------------------------- engagements

class EngagementIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_email: str = Field(pattern=EMAIL_PATTERN)


@app.get("/engagements")
def list_engagements(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Engagement).order_by(Engagement.id.desc())
    if user.role == "bank":
        q = q.where(Engagement.bank_id == user.id)
    elif user.role == "client":
        q = q.where(Engagement.client_email == user.email)
    return [engagement_out(db, e) for e in db.execute(q).scalars()]


@app.post("/engagements")
def create_engagement(body: EngagementIn, user: User = Depends(require_roles("bank")), db: Session = Depends(get_db)):
    e = Engagement(name=body.name.strip(), bank_id=user.id, client_email=body.client_email.strip().lower())
    db.add(e)
    db.flush()
    audit.log(db, actor=user.email, action="engagement.created", entity="engagement", entity_id=e.id,
              details={"name": e.name, "client_email": e.client_email}, engagement_id=e.id)
    db.commit()
    return engagement_out(db, e)


@app.get("/engagements/{eid}")
def get_engagement(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = load_engagement(db, user, eid)
    uploads = db.execute(select(Upload).where(Upload.engagement_id == eid).order_by(Upload.id.desc())).scalars()
    return {**engagement_out(db, e), "uploads": [upload_out(u) for u in uploads]}


# --------------------------------------------------------------------------- upload + verification

def _read_upload(file: UploadFile) -> bytes:
    limit = MAX_UPLOAD_MB * 1024 * 1024
    content = file.file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB")
    if not content:
        raise HTTPException(400, "The file is empty")
    return content


@app.post("/engagements/{eid}/preview")
def preview_file(eid: int, file: UploadFile = File(...), user: User = Depends(require_roles("client", "admin")),
                 db: Session = Depends(get_db)):
    """Read the file and suggest a column mapping. Nothing is stored."""
    load_engagement(db, user, eid)
    content = _read_upload(file)
    try:
        headers, table = verification.read_table(file.filename or "", content)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    if not headers:
        raise HTTPException(400, "Could not find a header row in the file")
    return {
        "headers": headers,
        "suggested_mapping": verification.suggest_mapping(headers),
        "sample_rows": [rec for _, rec in table[:5]],
        "n_rows": len(table),
        "fields": [{"key": f, "label": verification.FIELD_LABELS[f], "required": f in verification.REQUIRED_FIELDS}
                   for f in verification.CANONICAL_FIELDS],
    }


@app.post("/engagements/{eid}/uploads")
def create_upload(eid: int, file: UploadFile = File(...), mapping: str = Form(...), declaration: bool = Form(False),
                  user: User = Depends(require_roles("client", "admin")), db: Session = Depends(get_db)):
    e = load_engagement(db, user, eid)
    if not declaration:
        raise HTTPException(400, "Confirm the declaration that the file contains all receivables")
    content = _read_upload(file)
    try:
        headers, table = verification.read_table(file.filename or "", content)
        mp = json.loads(mapping)
        if not isinstance(mp, dict):
            raise ValueError("Invalid column mapping")
    except (ValueError, json.JSONDecodeError) as ex:
        raise HTTPException(400, str(ex))
    errors = verification.validate_mapping(mp, headers)
    if errors:
        raise HTTPException(400, " ".join(errors))
    if not table:
        raise HTTPException(400, "The file has no data rows")
    if len(table) > MAX_ROWS:
        raise HTTPException(400, f"The file has more than {MAX_ROWS:,} rows")

    rows = verification.build_rows(table, mp)
    findings, summary = verification.analyse(rows, mp)

    sha = hashlib.sha256(content).hexdigest()
    path = storage.save(e.id, sha, file.filename or "upload", content)
    up = Upload(engagement_id=e.id, uploaded_by=user.id, filename=storage.safe_name(file.filename or "upload"),
                stored_path=path, file_sha256=sha, mapping=json.dumps(mp), n_rows=len(rows),
                verdict=summary["verdict"], summary=json.dumps(summary), declaration_accepted=True)
    db.add(up)
    db.flush()

    db.execute(insert(Receivable), [
        {"upload_id": up.id, "row_number": r.row_number, "raw": json.dumps(r.raw, ensure_ascii=False),
         "invoice_id_norm": r.invoice_id_norm, "debtor_norm": r.debtor_norm, "amount_cents": r.amount_cents,
         "currency": r.currency, "issue_date": r.issue_date, "due_date": r.due_date, "row_hash": r.row_hash}
        for r in rows
    ])
    db.add_all([Finding(upload_id=up.id, kind=f["kind"], code=f["code"], severity=f["severity"], title=f["title"][:500],
                        description=f["description"], rows=json.dumps(f["rows"])) for f in findings])
    audit.log(db, actor=user.email, action="upload.verified", entity="upload", entity_id=up.id, engagement_id=e.id,
              details={"filename": up.filename, "sha256": sha, "rows": len(rows), "verdict": summary["verdict"],
                       "counts": summary["counts"], "declaration_accepted": True})
    db.commit()
    return upload_out(up)


@app.get("/uploads/{uid}")
def get_upload(uid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    up, e = load_upload(db, user, uid)
    fs = db.execute(select(Finding).where(Finding.upload_id == uid).order_by(Finding.id)).scalars()
    return {"upload": upload_out(up), "engagement": engagement_out(db, e), "findings": [finding_out(f) for f in fs]}


@app.get("/uploads/{uid}/report.pdf")
def get_report(uid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    up, e = load_upload(db, user, uid)
    bank = db.get(User, e.bank_id)
    fs = [finding_out(f) | {"rows": json.loads(f.rows)}
          for f in db.execute(select(Finding).where(Finding.upload_id == uid).order_by(Finding.id)).scalars()]
    now = utcnow()
    pdf = build_pdf(engagement=e, bank_name=bank.name if bank else "", client_email=e.client_email, upload=up,
                    summary=json.loads(up.summary), findings=fs, chain_head=audit.head_hash(db), generated_at=now)
    audit.log(db, actor=user.email, action="report.downloaded", entity="upload", entity_id=up.id, engagement_id=e.id)
    db.commit()
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", e.name)[:60] or "report"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="verification_{name}_{up.id}.pdf"'})


# --------------------------------------------------------------------------- findings

class FindingPatch(BaseModel):
    status: str
    note: str = Field(default="", max_length=2000)


def _load_finding(db: Session, user: User, fid: int) -> tuple[Finding, Upload, Engagement]:
    f = db.get(Finding, fid)
    if f is None:
        raise HTTPException(404, "Finding not found")
    up, e = load_upload(db, user, f.upload_id)
    return f, up, e


@app.patch("/findings/{fid}")
def update_finding(fid: int, body: FindingPatch, user: User = Depends(require_roles("bank", "admin")),
                   db: Session = Depends(get_db)):
    f, up, e = _load_finding(db, user, fid)
    if body.status not in FINDING_STATUSES:
        raise HTTPException(400, f"Status must be one of {', '.join(FINDING_STATUSES)}")
    old = f.status
    f.status, f.note, f.updated_by, f.updated_at = body.status, body.note.strip(), user.email, utcnow()
    audit.log(db, actor=user.email, action="finding.status_changed", entity="finding", entity_id=f.id,
              engagement_id=e.id, details={"from": old, "to": body.status, "note": f.note, "title": f.title})
    db.commit()
    return finding_out(f)


@app.get("/findings/{fid}/rows")
def finding_rows(fid: int, limit: int = Query(50, ge=1, le=500), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    f, up, _ = _load_finding(db, user, fid)
    nums = json.loads(f.rows)[:limit]
    recs = db.execute(select(Receivable).where(Receivable.upload_id == up.id, Receivable.row_number.in_(nums))
                      .order_by(Receivable.row_number)).scalars()
    return {
        "total": len(json.loads(f.rows)),
        "rows": [{"row_number": r.row_number, "raw": json.loads(r.raw), "amount_cents": r.amount_cents,
                  "currency": r.currency, "fingerprint": r.row_hash} for r in recs],
    }


# --------------------------------------------------------------------------- audit

@app.get("/engagements/{eid}/audit")
def engagement_audit(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    load_engagement(db, user, eid)
    entries = db.execute(select(AuditLog).where(AuditLog.engagement_id == eid).order_by(AuditLog.id.desc())).scalars()
    return [{"id": a.id, "ts": a.ts, "actor": a.actor, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "details": json.loads(a.details), "entry_hash": a.entry_hash, "prev_hash": a.prev_hash} for a in entries]


@app.get("/audit/verify")
def audit_verify(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return audit.verify_chain(db)


@app.get("/health")
def health():
    return {"ok": True}
