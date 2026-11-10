import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_and_verify_flow():
    pid = client.post("/api/premises", params={"label": "Home", "sanctioned_load_kw": 2}).json()["id"]
    r = client.post(f"/api/premises/{pid}/bills", files={"file": ("bill.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 200
    bill_id = r.json()["bill_id"]
    v = client.post(f"/api/bills/{bill_id}/verify", params={"units_kwh": 250, "amount_billed": 1855}).json()
    assert v["flagged"] is True


def test_rejects_bad_file_type():
    pid = client.post("/api/premises", params={"label": "X"}).json()["id"]
    r = client.post(f"/api/premises/{pid}/bills", files={"file": ("a.exe", b"x", "application/x-msdownload")})
    assert r.status_code == 415
