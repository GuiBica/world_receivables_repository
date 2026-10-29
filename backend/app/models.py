from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # client | bank | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Engagement(Base):
    """A bank asks a client company to submit its receivables for verification."""
    __tablename__ = "engagements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    bank_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    client_email: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Upload(Base):
    """One verification run: a file, its column mapping and the result."""
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_sha256: Mapped[str] = mapped_column(String(64))
    mapping: Mapped[str] = mapped_column(Text)  # JSON
    n_rows: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)  # JSON
    declaration_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Receivable(Base):
    __tablename__ = "receivables"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    raw: Mapped[str] = mapped_column(Text)  # JSON of the mapped raw values
    invoice_id_norm: Mapped[str] = mapped_column(String(255), default="")
    debtor_norm: Mapped[str] = mapped_column(String(255), default="")
    amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    __table_args__ = (Index("ix_receivables_upload_row", "upload_id", "row_number"),)


class Finding(Base):
    """An exception raised by the engine. Reviewed by the bank (OPEN -> UNDER_REVIEW -> RESOLVED / FALSE_POSITIVE)."""
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(48), default="")
    severity: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    rows: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of row numbers
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    note: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    """Append-only, hash-chained: each entry commits to the one before it."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(32))
    engagement_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    details: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
