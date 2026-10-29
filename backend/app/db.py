from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # prepare_threshold=None keeps this working behind transaction poolers (Supabase, Neon);
    # small pools because each serverless instance has its own.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=3, max_overflow=2,
                           connect_args={"prepare_threshold": None})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
