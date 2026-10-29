# Entrypoint for Vercel: it looks for a FastAPI instance called `app` in a file like this one.
from app.main import app  # noqa: F401
