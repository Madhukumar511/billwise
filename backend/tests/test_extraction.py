import pytest

from app.services.extraction import ExtractedBill


def test_schema_validates_and_reconciles():
    b = ExtractedBill(units_kwh=250, total_amount=1643.18,
                      line_items=[{"type": "energy", "description": "e", "amount": 1500.0},
                                  {"type": "tax", "description": "t", "amount": 143.18}])
    assert b.line_items_reconcile()


def test_detects_mismatched_items():
    b = ExtractedBill(units_kwh=100, total_amount=500,
                      line_items=[{"type": "energy", "description": "e", "amount": 100.0}])
    assert not b.line_items_reconcile()


def test_bad_dates_rejected():
    with pytest.raises(ValueError):
        ExtractedBill(units_kwh=1, total_amount=1, billing_start="2026-02-01", billing_end="2026-01-01")
