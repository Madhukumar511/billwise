from app.services.ocr import parse_bill_text

# Trimmed real OCR output from a BESCOM bill photo (noisy Kannada lines included)
SAMPLE = """
a WeoeoSano Load 3KW-FOHP
Pe hy GUS Reg Date 25/06/2023
3a os Bill Period 12/08/2026 - 12/09/2026
23%¢8/Consumption(Units) 94
Br abades*Eligible for subsidy 67.0
3.0KW 150.0 450.00
Der dod pil! Amount (1-2) 173.94
jays gee8/ Cur.Demand Payable ® 173.94
33 Aog ? 85.00
"""


def test_parse_real_ocr_text():
    r = parse_bill_text(SAMPLE)
    assert r["units_kwh"] == 94
    assert r["sanctioned_load_kw"] == 3
    assert r["amount_billed"] == 173.94
    assert r["subsidy_units"] == 67
    assert r["billing_start"] == "12/08/2026"
    assert r["missing"] == []


def test_missing_fields_reported():
    r = parse_bill_text("nothing useful here")
    assert set(r["missing"]) == {"units_kwh", "sanctioned_load_kw", "amount_billed"}
    assert r["subsidy_units"] == 0.0


def test_subsidy_survives_ocr_misread_of_for():
    r = parse_bill_text("Consumption(Units) 94\nSar ahadés*Eligible tor subsidy 67.0\n")
    assert r["subsidy_units"] == 67


def test_subsidy_from_entitlement_line():
    r = parse_bill_text("Consumption(Units) 94\n93 Entitiemen| Units 67.0\n")
    assert r["subsidy_units"] == 67


def test_subsidy_from_units_chargeable():
    r = parse_bill_text("Consumption(Units) 94\nMII ahwodés*Unils chargeable 27.0\n")
    assert r["subsidy_units"] == 67


BILL2 = """
Bill Pariod 12/06/2026 «12/08/2026
Pres. Aily, 7620
Prov. Rdg. 7285
Constant 1
Consumption(Units) 335
Entitlement Units 134.0
Wer slog 6i/ Amaunt(t-2) 424,00
i. ele. cloclEx.Load. Wp Panalty 337.50
"""


def test_multi_month_bill_fields():
    r = parse_bill_text(BILL2)
    assert r["billing_days"] == 61
    assert r["amount_billed"] == 424.00
    assert r["md_penalty"] == 337.50
    # no "Eligible" or "chargeable" line: entitlement is scaled by 61/30
    assert r["subsidy_units"] == 272.47


def test_units_corrected_from_meter_readings():
    r = parse_bill_text(BILL2.replace("Consumption(Units) 335", "Consumption(Units) 345"))
    assert r["units_kwh"] == 335
    assert r["warnings"]


def test_amount_from_subtotals_when_line_unreadable():
    r = parse_bill_text("Sub-Total-1 2881.47\nSub-Total-2 2457.47\n")
    assert r["amount_billed"] == 424.00


def test_recorded_md_parsed():
    r = parse_bill_text("Recorded M0 2.75, 2.75 KW\nConsumption(Units) 10\n")
    assert r["recorded_md_kw"] == 2.75
