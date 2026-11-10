import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Bill, Premises
from ..services.tariff_engine import Tariff, verify_bill

router = APIRouter(prefix="/api")

ALLOWED = {"application/pdf", "image/jpeg", "image/png"}
TARIFF_FILE = Path(__file__).resolve().parents[3] / "tariffs" / "sample_domestic.json"
if not TARIFF_FILE.exists():  # docker layout: /app/tariffs
    TARIFF_FILE = Path("/app/tariffs/sample_domestic.json")


@router.post("/premises")
def create_premises(label: str, sanctioned_load_kw: float = 1.0, db: Session = Depends(get_db)):
    p = Premises(label=label, sanctioned_load_kw=sanctioned_load_kw)
    db.add(p)
    db.commit()
    return {"id": p.id, "label": p.label}


@router.post("/premises/{premises_id}/bills")
async def upload_bill(premises_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not db.get(Premises, premises_id):
        raise HTTPException(404, "Premises not found")
    if file.content_type not in ALLOWED:
        raise HTTPException(415, "Only PDF, JPG or PNG files are allowed")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")

    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[file.content_type]
    path = Path(settings.upload_dir) / f"{uuid.uuid4().hex}{ext}"  # never trust the client filename
    path.write_bytes(data)

    bill = Bill(premises_id=premises_id, file_path=str(path), status="uploaded")
    db.add(bill)
    db.commit()
    # TODO (Week 2): enqueue OCR + extraction job here
    return {"bill_id": bill.id, "status": bill.status}


@router.post("/bills/{bill_id}/verify")
def verify(bill_id: int, units_kwh: float, amount_billed: float, subsidy_units: float = 0.0,
           db: Session = Depends(get_db)):
    """Manual-entry path: verify a bill without OCR. Useful while OCR is being built."""
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")
    tariff = Tariff.from_file(TARIFF_FILE)
    v = verify_bill(tariff, units_kwh, bill.premises.sanctioned_load_kw, amount_billed, subsidy_units)
    bill.units_kwh, bill.amount_billed = units_kwh, amount_billed
    bill.amount_recomputed, bill.variance = float(v.recomputed), float(v.variance)
    bill.status = "done"
    db.commit()
    return {"recomputed": float(v.recomputed), "billed": float(v.billed),
            "variance": float(v.variance), "flagged": v.flagged, "message": v.message}