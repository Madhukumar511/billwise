# BillWise

AI electricity bill analyzer and savings coach (SDG 7 and 9).

## Run locally (no Docker)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload      # http://localhost:8000/docs
pytest                             # run tests
```

## Run with Docker (Postgres + Redis + API)
```bash
cp .env.example .env               # add ANTHROPIC_API_KEY
docker compose up --build
```

## Try it
1. `POST /api/premises?label=Home&sanctioned_load_kw=2`
2. `POST /api/premises/1/bills` with a PDF/JPG/PNG
3. `POST /api/bills/1/verify?units_kwh=250&amount_billed=1855` -> flags a possible overcharge

## Layout
- `backend/app/services/tariff_engine.py` : rules-as-data bill recomputation and verification
- `backend/app/services/extraction.py`    : LLM structured extraction (schema-validated)
- `backend/app/api/bills.py`              : upload and verify endpoints
- `tariffs/`                              : tariff JSON (placeholder values, replace with real tariff orders)

## Next steps
Week 2: OCR + queue worker. Week 3: wire extraction into worker + correction UI.
Week 4: real tariffs for one utility.
