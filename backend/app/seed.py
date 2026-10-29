from sqlalchemy import func, select

from . import audit
from .config import DEMO_PASSWORD
from .db import SessionLocal
from .models import Engagement, User
from .security import hash_password

DEMO_USERS = [
    ("admin@demo.com", "Admin", "admin"),
    ("bank@demo.com", "Bank A (demo)", "bank"),
    ("client@demo.com", "Company B (demo)", "client"),
]


def seed_demo() -> None:
    """Create demo users and one engagement on first start (only if there are no users)."""
    with SessionLocal() as db:
        if db.execute(select(func.count(User.id))).scalar_one() > 0:
            return
        users = {}
        for email, name, role in DEMO_USERS:
            u = User(email=email, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
            db.add(u)
            users[role] = u
        db.flush()
        for u in users.values():
            audit.log(db, actor="system", action="user.created", entity="user", entity_id=u.id,
                      details={"email": u.email, "role": u.role, "demo": True})
        e = Engagement(name="Demo: Bank A financing Company B", bank_id=users["bank"].id, client_email="client@demo.com")
        db.add(e)
        db.flush()
        audit.log(db, actor=users["bank"].email, action="engagement.created", entity="engagement", entity_id=e.id,
                  details={"name": e.name, "client_email": e.client_email}, engagement_id=e.id)
        db.commit()
