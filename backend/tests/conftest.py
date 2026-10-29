import os
import sys
import tempfile
from pathlib import Path

# Isolated database and storage for the whole test session (must be set before the app is imported).
_tmp = tempfile.mkdtemp(prefix="rr-tests-")
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["SEED_DEMO"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def login(client, email, password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def bank(client):
    return login(client, "bank@demo.com")


@pytest.fixture(scope="session")
def company(client):
    return login(client, "client@demo.com")


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin@demo.com")
