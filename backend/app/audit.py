"""Hash-chained audit trail. Entry N commits to entry N-1, so editing or deleting history is detectable."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import AuditLog

GENESIS = "GENESIS"


def _payload(ts, actor, action, entity, entity_id, engagement_id, details) -> str:
    return json.dumps(
        {"ts": ts, "actor": actor, "action": action, "entity": entity, "entity_id": entity_id,
         "engagement_id": engagement_id, "details": details},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def _hash(prev_hash: str, payload: str) -> str:
    return hashlib.sha256((prev_hash + "|" + payload).encode()).hexdigest()


def head_hash(db: Session) -> str:
    last = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    return last.entry_hash if last else GENESIS


def log(db: Session, *, actor: str, action: str, entity: str, entity_id, details: dict | None = None,
        engagement_id: int | None = None) -> AuditLog:
    details = details or {}
    if db.get_bind().dialect.name == "postgresql":
        # Several serverless instances may write at once: take a transaction-scoped lock so the chain cannot fork.
        db.execute(text("SELECT pg_advisory_xact_lock(727001)"))
    ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    prev = head_hash(db)
    payload = _payload(ts, actor, action, entity, str(entity_id), engagement_id, details)
    entry = AuditLog(
        ts=ts, actor=actor, action=action, entity=entity, entity_id=str(entity_id),
        engagement_id=engagement_id, details=json.dumps(details, sort_keys=True, ensure_ascii=False),
        prev_hash=prev, entry_hash=_hash(prev, payload),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for e in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
        payload = _payload(e.ts, e.actor, e.action, e.entity, e.entity_id, e.engagement_id, json.loads(e.details))
        if e.prev_hash != prev or e.entry_hash != _hash(prev, payload):
            return {"ok": False, "entries": count, "first_bad_id": e.id}
        prev = e.entry_hash
        count += 1
    return {"ok": True, "entries": count, "first_bad_id": None}
