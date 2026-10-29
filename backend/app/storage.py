"""File storage. Local disk for now; replace the body of save() with an object-storage upload (S3, Vercel Blob) later."""
import re
from pathlib import Path

from .config import STORAGE_DIR


def safe_name(name: str) -> str:
    base = Path(name).name or "upload"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120]


def save(engagement_id: int, sha256: str, filename: str, content: bytes) -> str:
    """Keep the original file. Returns "" when the disk is not writable (serverless): the parsed rows and the
    file's SHA-256 are still stored in the database, only the original bytes are not kept."""
    try:
        folder = Path(STORAGE_DIR) / f"engagement_{engagement_id}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{sha256[:12]}_{safe_name(filename)}"
        path.write_bytes(content)
        return str(path)
    except OSError:
        return ""
