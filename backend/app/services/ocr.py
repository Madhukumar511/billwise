"""Free OCR path: Tesseract reads the photo, regexes pick out the key fields.

No API key needed. Works on JPG/PNG photos. Output is a SUGGESTION: the web page
shows the values so the user can correct them before verifying.
"""
from __future__ import annotations

import datetime as dt
import io
import os
import re

import pytesseract
from PIL import Image, ImageOps

_WIN_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.name == "nt" and os.path.exists(_WIN_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = _WIN_TESSERACT

MULTI_MONTH_DAYS = 45  # keep in sync with tariff_engine.py


def ocr_image(data: bytes) -> str:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("L")  # fix phone rotation, grayscale
    if img.width < 1200:  # small photos read better when enlarged
        scale = 1200 / img.width
        img = img.resize((1200, int(img.height * scale)))
    return pytesseract.image_to_string(img, lang="eng", config="--psm 4")


def _num(s: str) -> float:
    s = s.strip()
    if re.search(r",\d{2}$", s):  # OCR sometimes reads "424.00" as "424,00"
        s = s[:-3] + "." + s[-2:]
    return float(s.replace(",", ""))


def _first(patterns: list[str], text: str, flags=re.IGNORECASE):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m
    return None


MONEY = r"(\d[\d,]*[.,]\d{2})"
QTY = r"(\d[\d,]*\.?\d*)"


def parse_bill_text(text: str) -> dict:
    """Extract the fields BillWise needs from OCR text (BESCOM-style layout)."""
    out: dict = {}
    warnings: list[str] = []

    # --- billing period and number of days
    m = re.search(r"(\d{2}/\d{2}/\d{4})\D{1,4}(\d{2}/\d{2}/\d{4})", text)
    if m:
        out["billing_start"], out["billing_end"] = m.group(1), m.group(2)
        try:
            d1 = dt.datetime.strptime(m.group(1), "%d/%m/%Y").date()
            d2 = dt.datetime.strptime(m.group(2), "%d/%m/%Y").date()
            if d2 > d1:
                out["billing_days"] = (d2 - d1).days
        except ValueError:
            pass

    # --- units, cross-checked with the meter readings
    m = _first([r"Consumption\s*\(?Units\)?\D{0,8}" + QTY], text)
    if m:
        out["units_kwh"] = _num(m.group(1))

    pres = _first([r"Pres\W+\w+\W+(\d{3,7})\b"], text)
    prev = _first([r"Pr[eo][vw]\W+\w+\W+(\d{3,7})\b"], text)
    const = _first([r"Constant\D{0,4}(\d+)"], text)
    if pres and prev and const and int(const.group(1)) == 1 and int(pres.group(1)) > int(prev.group(1)):
        diff = float(int(pres.group(1)) - int(prev.group(1)))
        if "units_kwh" not in out:
            out["units_kwh"] = diff
        elif abs(out["units_kwh"] - diff) > 0.5:
            warnings.append(
                f"The printed units were read as {out['units_kwh']:g}, but the meter readings "
                f"give {diff:g}. Using {diff:g}; please check."
            )
            out["units_kwh"] = diff

    # --- sanctioned load
    m = _first([r"Load\s*(\d+\.?\d*)\s*KW", r"(\d+\.?\d*)\s*KW\s+\d+\.?\d*\s+\d+\.\d{2}"], text)
    if m:
        out["sanctioned_load_kw"] = _num(m.group(1))

    # --- bill amount = "Bill Amount (1-2)", i.e. before penalties/arrears
    m = _first([r"Am\w{2,4}\s*\(\s*\w\s*-\s*\w\s*\)\s*" + MONEY], text)
    if m:
        out["amount_billed"] = _num(m.group(1))
    else:
        st1 = _first([r"Sub-?\s*Total-?\s*1\D{0,10}" + MONEY], text)
        st2 = _first([r"Sub-?\s*Total-?\s*2\D{0,10}" + MONEY], text)
        if st1 and st2:
            out["amount_billed"] = round(_num(st1.group(1)) - _num(st2.group(1)), 2)
        elif st1:
            out["amount_billed"] = _num(st1.group(1))

    # --- recorded maximum demand (kW), shown in advice
    m = _first([r"Recorded\s*M\w{1,2}\D{0,4}(\d+\.?\d*)"], text)
    if m:
        out["recorded_md_kw"] = _num(m.group(1))

    # --- penalty (information only; not part of the check)
    m = _first([r"Load\W{0,3}\w{0,4}\W{0,2}P[ea]n\w*\s*" + MONEY], text)
    if m and _num(m.group(1)) > 0:
        out["md_penalty"] = _num(m.group(1))

    # --- subsidised units: "Eligible for subsidy" (OCR may misread "for"),
    #     then units minus "Units chargeable", then the monthly "Entitlement Units"
    m = _first([r"Eligible\s*\w{2,4}\s*subsid\w*\D{0,4}" + QTY], text)
    if m:
        out["subsidy_units"] = _num(m.group(1))
    else:
        c = _first([r"Un\w{2,3}\s*charge\w*\D{0,4}" + QTY], text)
        e = _first([r"Entit\S*\s*Un\w{2,3}\D{0,4}" + QTY], text)
        if c and "units_kwh" in out and _num(c.group(1)) <= out["units_kwh"]:
            out["subsidy_units"] = round(out["units_kwh"] - _num(c.group(1)), 2)
        elif e:
            ent = _num(e.group(1))
            days = out.get("billing_days")
            out["subsidy_units"] = round(ent * days / 30, 2) if days and days > MULTI_MONTH_DAYS else ent
        else:
            out["subsidy_units"] = 0.0

    out["warnings"] = warnings
    out["missing"] = [k for k in ("units_kwh", "sanctioned_load_kw", "amount_billed") if k not in out]
    return out
