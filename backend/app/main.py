from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .api import bills
from .db import Base, engine

Base.metadata.create_all(bind=engine)  # swap for Alembic migrations once schema stabilises

app = FastAPI(title="BillWise API", version="0.1.0")
app.include_router(bills.router)

STATIC = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}
