import json
from pathlib import Path

from scripts.make_synthetic import generate

SMALL = None


def _small():
    global SMALL
    if SMALL is None:
        SMALL = generate(300, seed=3, eu=True)
    return SMALL


def _engagement_id(client, bank):
    r = client.get("/engagements", headers=bank)
    assert r.status_code == 200 and r.json(), r.text
    return r.json()[0]["id"]


def test_auth_required_and_wrong_password(client):
    assert client.get("/engagements").status_code == 401
    assert client.post("/auth/login", json={"email": "bank@demo.com", "password": "nope"}).status_code == 401


def test_register_and_roles(client):
    r = client.post("/auth/register", json={"email": "New.User@Example.com", "password": "longenough1",
                                            "name": "New", "role": "bank"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "new.user@example.com"
    assert client.post("/auth/register", json={"email": "x@y.com", "password": "longenough1", "name": "X",
                                               "role": "admin"}).status_code == 422
    assert client.post("/auth/register", json={"email": "new.user@example.com", "password": "longenough1",
                                               "name": "N", "role": "bank"}).status_code == 409


def test_full_flow(client, bank, company, admin):
    eid = _engagement_id(client, bank)
    text, exp = _small()
    files = {"file": ("ledger.csv", text.encode(), "text/csv")}

    # client previews the file and gets a suggested mapping
    r = client.post(f"/engagements/{eid}/preview", files=files, headers=company)
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["n_rows"] == 300 and pv["suggested_mapping"]["amount"] == "Amount"

    # bank cannot upload; declaration is mandatory
    assert client.post(f"/engagements/{eid}/uploads", files=files, headers=bank,
                       data={"mapping": json.dumps(pv["suggested_mapping"]), "declaration": "true"}).status_code == 403
    assert client.post(f"/engagements/{eid}/uploads", files=files, headers=company,
                       data={"mapping": json.dumps(pv["suggested_mapping"]), "declaration": "false"}).status_code == 400
    # a mapping that misses a required field is rejected
    bad = dict(pv["suggested_mapping"], amount=None)
    assert client.post(f"/engagements/{eid}/uploads", files=files, headers=company,
                       data={"mapping": json.dumps(bad), "declaration": "true"}).status_code == 400

    # run the verification
    r = client.post(f"/engagements/{eid}/uploads", files=files, headers=company,
                    data={"mapping": json.dumps(pv["suggested_mapping"]), "declaration": "true"})
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["verdict"] == "DUPLICATES_FOUND" and up["summary"]["counts"]["ECONOMIC_DUPLICATE"] == 5

    # bank reads the result and reviews a finding
    r = client.get(f"/uploads/{up['id']}", headers=bank)
    assert r.status_code == 200
    findings = r.json()["findings"]
    exact = next(f for f in findings if f["kind"] == "EXACT_DUPLICATE")
    rows = client.get(f"/findings/{exact['id']}/rows", headers=bank).json()
    assert len(rows["rows"]) == 2 and rows["rows"][0]["fingerprint"] == rows["rows"][1]["fingerprint"]

    assert client.patch(f"/findings/{exact['id']}", json={"status": "RESOLVED"}, headers=company).status_code == 403
    assert client.patch(f"/findings/{exact['id']}", json={"status": "BOGUS"}, headers=bank).status_code == 400
    r = client.patch(f"/findings/{exact['id']}", json={"status": "FALSE_POSITIVE", "note": "Checked with client"},
                     headers=bank)
    assert r.status_code == 200 and r.json()["status"] == "FALSE_POSITIVE"

    # engagement list reflects the latest run
    eng = client.get(f"/engagements/{eid}", headers=bank).json()
    assert eng["latest_upload"]["verdict"] == "DUPLICATES_FOUND" and len(eng["uploads"]) >= 1

    # PDF report
    r = client.get(f"/uploads/{up['id']}/report.pdf", headers=bank)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and len(r.content) > 2000

    # audit trail: actions are recorded and the chain verifies
    trail = client.get(f"/engagements/{eid}/audit", headers=bank).json()
    actions = {a["action"] for a in trail}
    assert {"upload.verified", "finding.status_changed", "report.downloaded", "engagement.created"} <= actions
    assert client.get("/audit/verify", headers=admin).json()["ok"] is True


def test_access_control(client, bank):
    other = client.post("/auth/register", json={"email": "other.bank@example.com", "password": "longenough1",
                                                "name": "Other bank", "role": "bank"}).json()
    h = {"Authorization": f"Bearer {other['access_token']}"}
    eid = _engagement_id(client, bank)
    assert client.get(f"/engagements/{eid}", headers=h).status_code == 404
    assert client.get("/engagements", headers=h).json() == []
    r = client.post("/engagements", json={"name": "Mine", "client_email": "company@example.com"}, headers=h)
    assert r.status_code == 200 and r.json()["client_email"] == "company@example.com"


def test_audit_chain_detects_tampering(client, admin):
    from app.db import SessionLocal
    from app.models import AuditLog
    assert client.get("/audit/verify", headers=admin).json()["ok"] is True
    with SessionLocal() as db:
        entry = db.get(AuditLog, 2)
        entry.actor = "someone.else@example.com"
        db.commit()
    res = client.get("/audit/verify", headers=admin).json()
    assert res["ok"] is False and res["first_bad_id"] == 2
