"""Tariff engine: recompute a bill from rules-as-data.

Pure Python, no I/O besides optional JSON loading, so it is easy to test.
Money is handled with Decimal to avoid float rounding drift.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

TWO = Decimal("0.01")


def _d(x) -> Decimal:
    return Decimal(str(x))


def _money(x: Decimal) -> Decimal:
    return x.quantize(TWO, rounding=ROUND_HALF_UP)


@dataclass
class Slab:
    from_unit: float
    to_unit: float | None  # None = unlimited
    rate: float


@dataclass
class Tariff:
    utility: str
    category: str
    version: str
    fixed_charge_per_kw: float
    slabs: list[Slab]
    fuel_adjustment_per_kwh: float = 0.0
    tax_percent: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "Tariff":
        return cls(
            utility=d["utility"],
            category=d["category"],
            version=d.get("version", "n/a"),
            fixed_charge_per_kw=d.get("fixed_charge_per_kw", 0.0),
            slabs=[Slab(**s) for s in d["slabs"]],
            fuel_adjustment_per_kwh=d.get("fuel_adjustment_per_kwh", 0.0),
            tax_percent=d.get("tax_percent", 0.0),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "Tariff":
        return cls.from_dict(json.loads(Path(path).read_text()))


@dataclass
class LineItem:
    type: str
    description: str
    quantity: float | None
    rate: float | None
    amount: Decimal


@dataclass
class BillResult:
    units: float
    line_items: list[LineItem] = field(default_factory=list)
    total: Decimal = Decimal("0.00")

    def as_dict(self) -> dict:
        return {
            "units": self.units,
            "total": float(self.total),
            "line_items": [
                {**li.__dict__, "amount": float(li.amount)} for li in self.line_items
            ],
        }


def compute_bill(tariff: Tariff, units: float, sanctioned_load_kw: float) -> BillResult:
    """Telescopic slabs: each slab's rate applies only to units inside that slab."""
    if units < 0:
        raise ValueError("units must be >= 0")

    result = BillResult(units=units)
    subtotal = Decimal("0")

    for slab in tariff.slabs:
        upper = slab.to_unit if slab.to_unit is not None else float("inf")
        in_slab = max(0.0, min(units, upper) - slab.from_unit)
        if in_slab <= 0:
            continue
        amt = _money(_d(in_slab) * _d(slab.rate))
        label = f"{slab.from_unit:g}-{'' if slab.to_unit is None else format(slab.to_unit, 'g')}"
        result.line_items.append(LineItem("energy", f"Energy slab {label}", in_slab, slab.rate, amt))
        subtotal += amt

    fixed = _money(_d(tariff.fixed_charge_per_kw) * _d(sanctioned_load_kw))
    result.line_items.append(
        LineItem("fixed", "Fixed charge", sanctioned_load_kw, tariff.fixed_charge_per_kw, fixed)
    )
    subtotal += fixed

    fuel = _money(_d(tariff.fuel_adjustment_per_kwh) * _d(units))
    result.line_items.append(
        LineItem("fuel_adj", "Fuel adjustment charge", units, tariff.fuel_adjustment_per_kwh, fuel)
    )
    subtotal += fuel

    tax = _money(subtotal * _d(tariff.tax_percent) / Decimal(100))
    result.line_items.append(LineItem("tax", f"Tax @ {tariff.tax_percent:g}%", None, tariff.tax_percent, tax))

    result.total = _money(subtotal + tax)
    return result


@dataclass
class Verification:
    recomputed: Decimal
    billed: Decimal
    variance: Decimal
    flagged: bool
    message: str


def verify_bill(
    tariff: Tariff,
    units: float,
    sanctioned_load_kw: float,
    billed_amount: float,
    tolerance_inr: float = 5.0,
    tolerance_pct: float = 1.0,
) -> Verification:
    """Compare billed vs recomputed. Flag only if the gap exceeds BOTH tolerances
    (absolute and percentage), which avoids noise from rounding and minor rebates."""
    res = compute_bill(tariff, units, sanctioned_load_kw)
    billed = _money(_d(billed_amount))
    variance = _money(billed - res.total)
    pct = abs(variance) / res.total * 100 if res.total else Decimal(0)
    flagged = abs(variance) > _d(tolerance_inr) and pct > _d(tolerance_pct)
    if not flagged:
        msg = "Bill matches the tariff within tolerance."
    elif variance > 0:
        msg = f"Possible overcharge of Rs {variance} versus the tariff calculation."
    else:
        msg = f"Billed amount is Rs {abs(variance)} lower than the tariff calculation."
    return Verification(res.total, billed, variance, flagged, msg)
