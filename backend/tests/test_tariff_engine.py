from decimal import Decimal
from pathlib import Path

import pytest

from app.services.tariff_engine import Tariff, compute_bill, verify_bill

TARIFF = Tariff.from_file(Path(__file__).resolve().parents[2] / "tariffs" / "sample_domestic.json")


def test_within_first_slab():
    r = compute_bill(TARIFF, 80, 2)
    # energy 80*4.15=332 ; fixed 2*50=100 ; fuel 80*.3=24 ; subtotal 456 ; tax 9% = 41.04
    assert r.total == Decimal("497.04")


def test_spans_all_slabs():
    r = compute_bill(TARIFF, 250, 2)
    # 100*4.15 + 100*5.60 + 50*7.15 = 415 + 560 + 357.5 = 1332.5
    energy = sum(li.amount for li in r.line_items if li.type == "energy")
    assert energy == Decimal("1332.50")
    # subtotal = 1332.5 + 100 + 75 = 1507.5 ; tax = 135.675 -> 135.68 ; total 1643.18
    assert r.total == Decimal("1643.18")


def test_zero_units_still_charges_fixed():
    r = compute_bill(TARIFF, 0, 3)
    assert any(li.type == "fixed" and li.amount == Decimal("150.00") for li in r.line_items)


def test_negative_units_rejected():
    with pytest.raises(ValueError):
        compute_bill(TARIFF, -1, 2)


def test_verify_matches():
    v = verify_bill(TARIFF, 250, 2, 1643.18)
    assert not v.flagged


def test_verify_flags_overcharge():
    v = verify_bill(TARIFF, 250, 2, 1855.00)
    assert v.flagged and v.variance > 0 and "overcharge" in v.message


def test_small_rounding_gap_not_flagged():
    v = verify_bill(TARIFF, 250, 2, 1644.00)
    assert not v.flagged
