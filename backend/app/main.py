from fastapi import FastAPI

from .api import bills
from .db import Base, engine

Base.metadata.create_all(bind=engine)  # swap for Alembic migrations once schema stabilises

app = FastAPI(title="BillWise API", version="0.1.0")
app.include_router(bills.router)


@app.get("/health")
def health():
    return {"status": "ok"}
