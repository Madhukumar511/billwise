# BillWise

AI electricity bill checker and savings coach (SDG 7 and 9).
Upload a BESCOM bill photo -> OCR reads it -> tariff engine recomputes it -> plain-language advice.

## Run locally (no Docker)
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload             # http://127.0.0.1:8000
python -m pytest
```
Needs the Tesseract program installed for photo reading (https://github.com/UB-Mannheim/tesseract/wiki).

## Run with Docker + PostgreSQL
```bash
docker compose up --build                           # http://localhost:8000
```

## Deploy on Render (free tier)
1. Push this repo to GitHub.
2. Render Dashboard -> New -> Blueprint -> pick the repo -> Apply. `render.yaml` creates the web service and a PostgreSQL database.
3. Open the service URL once the build finishes.

Free-tier notes: the service sleeps after about 15 minutes idle (first request is slow), the free database expires after 30 days, and the filesystem is ephemeral. `STORE_UPLOADS=false` means bill photos are never kept.

## Layout
- `backend/app/services/tariff_engine.py` : rules-as-data bill recomputation
- `backend/app/services/ocr.py`          : Tesseract + field parsing
- `backend/app/services/coach.py`        : plain-language explanation and savings tips
- `backend/app/api/bills.py`             : upload, scan, verify endpoints
- `backend/app/static/index.html`        : web page
- `tariffs/`                             : tariff JSON (BESCOM LT-1 rates read from real bills)
- `Dockerfile`, `render.yaml`, `docker-compose.yml` : deployment
