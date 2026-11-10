"""Tariff engine: recompute a bill from rules-as-data.

Supports: slab or flat energy rates, fixed charge per kW, any number of per-kWh
charges (fuel adjustment, surcharges; negative rates allowed), tax on energy
only or on everything, and the Gruha Jyothi style subsidy (a second bill on the
eligible units that is subtracted from the gross bill).

Money uses Decimal. Every line is rounded to 2 places before summing, which is
how the printed bill behaves.
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
class PerUnitCharge:
    name: str
    type: str
    rate: float  # may be negative


@dataclass
class Tariff:
    utility: str
    category: str
    version: str
    fixed_charge_per_kw: float
    slabs: list[Slab]
    per_unit_charges: list[PerUnitCharge] = field(default_factory=list)
    tax_percent: float = 0.0
    tax_base: str = "energy"  # "energy" or "all"

    @classmethod
    def from_dict(cls, d: dict) -> "Tariff":
        return cls(
            utility=d["utility"],
            category=d["category"],
            version=d.get("version", "n/a"),
            fixed_charge_per_kw=d.get("fixed_charge_per_kw", 0.0),
            slabs=[Slab(**s) for s in d["slabs"]],
            per_unit_charges=[PerUnitCharge(**c) for c in d.get("per_unit_charges", [])],
            tax_percent=d.get("tax_percent", 0.0),
            tax_base=d.get("tax_base", "energy"),
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
            "line_items": [{**li.__dict__, "amount": float(li.amount)} for li in self.line_items],
        }


def compute_bill(tariff: Tariff, units: float, sanctioned_load_kw: float) -> BillResult:
    """Gross bill for `units` consumed (no subsidy)."""
    if units < 0:
        raise ValueError("units must be >= 0")

    result = BillResult(units=units)
    energy_total = Decimal("0")
    other_total = Decimal("0")

    fixed = _money(_d(tariff.fixed_charge_per_kw) * _d(sanctioned_load_kw))
    result.line_items.append(
        LineItem("fixed", "Fixed charges", sanctioned_load_kw, tariff.fixed_charge_per_kw, fixed)
    )
    other_total += fixed

    for slab in tariff.slabs:
        upper = slab.to_unit if slab.to_unit is not None else float("inf")
        in_slab = max(0.0, min(units, upper) - slab.from_unit)
        if in_slab <= 0:
            continue
        amt = _money(_d(in_slab) * _d(slab.rate))
        result.line_items.append(LineItem("energy", "Energy charges", in_slab, slab.rate, amt))
        energy_total += amt

    for c in tariff.per_unit_charges:
        amt = _money(_d(c.rate) * _d(units))
        result.line_items.append(LineItem(c.type, c.name, units, c.rate, amt))
        other_total += amt

    base = energy_total if tariff.tax_base == "energy" else energy_total + other_total
    tax = _money(base * _d(tariff.tax_percent) / Decimal(100))
    result.line_items.append(
        LineItem("tax", f"Tax @ {tariff.tax_percent:g}% on {tariff.tax_base}", None, tariff.tax_percent, tax)
    )

    result.total = _money(energy_total + other_total + tax)
    return result


@dataclass
class NetBill:
    gross: BillResult
    subsidy: BillResult | None
    net: Decimal


def compute_net_bill(
    tariff: Tariff, units: float, sanctioned_load_kw: float, subsidy_units: float = 0.0
) -> NetBill:
    """Gross bill minus the subsidy bill (Gruha Jyothi style).

    The subsidy is itself a full bill (including the fixed charge) computed on the
    eligible units, capped at the units actually consumed.
    """
    gross = compute_bill(tariff, units, sanctioned_load_kw)
    if subsidy_units <= 0:
        return NetBill(gross, None, gross.total)
    sub = compute_bill(tariff, min(subsidy_units, units), sanctioned_load_kw)
    return NetBill(gross, sub, _money(gross.total - sub.total))


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
    subsidy_units: float = 0.0,
    tolerance_inr: float = 5.0,
    tolerance_pct: float = 1.0,
) -> Verification:
    """Compare the billed current demand with the recomputed amount.

    Flags only if the gap exceeds BOTH the rupee and percentage tolerances.
    `billed_amount` should be the current demand (before true-ups and arrears).
    """
    res = compute_net_bill(tariff, units, sanctioned_load_kw, subsidy_units).net
    billed = _money(_d(billed_amount))
    variance = _money(billed - res)
    pct = abs(variance) / res * 100 if res else (Decimal(0) if variance == 0 else Decimal(100))
    flagged = abs(variance) > _d(tolerance_inr) and pct > _d(tolerance_pct)
    if not flagged:
        msg = "Bill matches the tariff within tolerance."
    elif variance > 0:
        msg = f"Possible overcharge of Rs {variance} versus the tariff calculation."
    else:
        msg = f"Billed amount is Rs {abs(variance)} lower than the tariff calculation."
    return Verification(res, billed, variance, flagged, msg)