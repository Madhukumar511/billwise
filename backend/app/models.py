import datetime as dt

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now():
    return dt.datetime.now(dt.timezone.utc)


class Premises(Base):
    __tablename__ = "premises"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    utility: Mapped[str] = mapped_column(String(100), default="SAMPLE-DISCOM")
    tariff_category: Mapped[str] = mapped_column(String(100), default="LT-1 Domestic")
    sanctioned_load_kw: Mapped[float] = mapped_column(Float, default=1.0)
    bills: Mapped[list["Bill"]] = relationship(back_populates="premises")


class Bill(Base):
    __tablename__ = "bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    premises_id: Mapped[int] = mapped_column(ForeignKey("premises.id"))
    file_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded|processing|done|failed
    billing_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    billing_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    units_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_billed: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_recomputed: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    premises: Mapped[Premises] = relationship(back_populates="bills")
