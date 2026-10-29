import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ON_VERCEL = bool(os.getenv("VERCEL"))


def _normalise_db_url(url: str) -> str:
    """Hosted Postgres providers hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg driver name."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


# SQLite by default (zero setup, local use). In production set DATABASE_URL to a PostgreSQL URL.
DATABASE_URL = _normalise_db_url(os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data.db'}"))

# Change this in any real deployment.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-dev-secret-change-me")
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "720"))

# Uploaded files are kept on local disk for now (swap for S3 / object storage later, see storage.py).
# On serverless hosts the disk is read-only or ephemeral, so the original file is then best-effort only.
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/tmp/receivables-storage" if ON_VERCEL else str(BASE_DIR / "storage")))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
# Optional regex for extra allowed origins, e.g. Vercel preview URLs: https://my-app-.*\\.vercel\\.app
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX") or None

# Demo users + one demo engagement, created on first start. Password is DEMO_PASSWORD.
SEED_DEMO = os.getenv("SEED_DEMO", "1") == "1"
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")

# Set to 0 once your own accounts exist, so strangers cannot sign up.
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "1") == "1"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "4" if ON_VERCEL else "25"))  # Vercel Functions reject request bodies above 4.5 MB
MAX_ROWS = int(os.getenv("MAX_ROWS", "200000"))

if ON_VERCEL:
    if SECRET_KEY.startswith("dev-secret"):
        raise RuntimeError("Set the SECRET_KEY environment variable (a long random string) before deploying.")
    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Set DATABASE_URL to a PostgreSQL database: SQLite does not persist on Vercel.")
    if SEED_DEMO and DEMO_PASSWORD == "demo1234":
        raise RuntimeError("Set SEED_DEMO=0, or set DEMO_PASSWORD to something private: the default demo password is public.")
