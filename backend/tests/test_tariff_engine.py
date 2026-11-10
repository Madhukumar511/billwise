"""Tests built from a real BESCOM LT-1 bill (12/08/2026 - 12/09/2026).

Printed values: 94 units, 3 kW sanctioned, 67 units subsidised (Gruha Jyothi).
Sub-total-1 = 1055.55, Sub-total-2 = 881.61, Bill amount (1-2) = 173.94.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.tariff_engine import Tariff, compute_bill, compute_net_bill, verify_bill

TARIFF = Tariff.from_file(Path(__file__).resolve().parents[2] / "tariffs" / "sample_domestic.json")


def _amt(result, type_):
    return sum(li.amount for li in result.line_items if li.type == type_)


def test_gross_bill_matches_printed_subtotal_1():
    r = compute_bill(TARIFF, 94, 3)
    assert _amt(r, "fixed") == Decimal("450.00")
    assert _amt(r, "energy") == Decimal("545.20")
    assert _amt(r, "fuel_adj") == Decimal("-21.62")
    assert _amt(r, "surcharge") == Decimal("32.90")
    assert _amt(r, "tax") == Decimal("49.07")  # 9% of ENERGY only
    assert r.total == Decimal("1055.55")


def test_subsidy_bill_matches_printed_subtotal_2():
    r = compute_bill(TARIFF, 67, 3)
    assert _amt(r, "energy") == Decimal("388.60")
    assert _amt(r, "tax") == Decimal("34.97")
    assert r.total == Decimal("881.61")


def test_net_bill_matches_current_demand():
    nb = compute_net_bill(TARIFF, 94, 3, subsidy_units=67)
    assert nb.net == Decimal("173.94")


def test_verify_real_bill_passes():
    v = verify_bill(TARIFF, 94, 3, 173.94, subsidy_units=67)
    assert not v.flagged and v.variance == Decimal("0.00")


def test_verify_flags_overcharge():
    v = verify_bill(TARIFF, 94, 3, 260.00, subsidy_units=67)
    assert v.flagged and "overcharge" in v.message


def test_consumption_below_entitlement_is_zero():
    # all units subsidised -> nothing to pay
    nb = compute_net_bill(TARIFF, 60, 3, subsidy_units=67)
    assert nb.net == Decimal("0.00")


def test_no_subsidy():
    nb = compute_net_bill(TARIFF, 94, 3)
    assert nb.net == Decimal("1055.55")


def test_negative_units_rejected():
    with pytest.raises(ValueError):
        compute_bill(TARIFF, -1, 3)