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
from PIL import Image, ImageFilter, ImageOps

_WIN_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.name == "nt" and os.path.exists(_WIN_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = _WIN_TESSERACT

MULTI_MONTH_DAYS = 45  # keep in sync with tariff_engine.py


def ocr_image(data: bytes) -> str:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("L")  # fix phone rotation, grayscale
    if img.width < 1600:  # small photos read better when enlarged
        scale = 1600 / img.width
        img = img.resize((1600, int(img.height * scale)), Image.Resampling.LANCZOS)
    elif img.width > 2400:
        scale = 2200 / img.width
        img = img.resize((2200, int(img.height * scale)), Image.Resampling.LANCZOS)
    # Autocontrast / histogram stretch to make faint dot matrix ink pop out
    img = ImageOps.autocontrast(img, cutoff=2)
    # Mild sharpen filter to clarify faint dot-matrix print
    img = img.filter(ImageFilter.SHARPEN)
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
    m = _first([
        r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\D{1,6}(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
        r"Bill\s*P[ae]riod\D{0,8}(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\D{1,6}(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})"
    ], text)
    if m:
        out["billing_start"], out["billing_end"] = m.group(1), m.group(2)
        try:
            sep = "/" if "/" in m.group(1) else ("-" if "-" in m.group(1) else ".")
            d1 = dt.datetime.strptime(m.group(1), f"%d{sep}%m{sep}%Y").date()
            d2 = dt.datetime.strptime(m.group(2), f"%d{sep}%m{sep}%Y").date()
            if d2 > d1:
                out["billing_days"] = (d2 - d1).days
        except Exception:
            pass

    days_m = _first([r"(?:Billing\s*Days?|No\.?\s*(?:of)?\s*Days?|Bill\s*Days?)\D{0,6}(\d{1,3})\b"], text)
    if days_m and "billing_days" not in out:
        out["billing_days"] = int(days_m.group(1))

    # --- units, cross-checked with the meter readings
    m = _first([
        r"(?:Total\s*|Net\s*|Billed\s*|Actual\s*)?Consumption\s*(?:\(?Units?\)?|\(kWh\)|Units?|kWh)?\D{0,10}" + QTY,
        r"(?:Units?\s*(?:Consumed|Billed|Recorded)|kWh\s*Consumed)\D{0,10}" + QTY,
        r"\bUnits\s*:\s*" + QTY,
        r"Billed\s*kWh\D{0,8}" + QTY
    ], text)
    if m:
        out["units_kwh"] = _num(m.group(1))

    pres = _first([
        r"Pres(?:ent|\.)?\s*(?:Rdg|Reading|Aily|Rdy)?\D{0,8}(\d{3,7}(?:\.\d+)?)",
        r"Cur(?:r|\.|\s*rent)?\s*(?:Rdg|Reading)?\D{0,8}(\d{3,7}(?:\.\d+)?)"
    ], text)
    prev = _first([
        r"Pr[eo]v(?:ious|\.)?\s*(?:Rdg|Reading|Rdy)?\D{0,8}(\d{3,7}(?:\.\d+)?)",
        r"Past\s*(?:Rdg|Reading)?\D{0,8}(\d{3,7}(?:\.\d+)?)"
    ], text)
    const = _first([r"Constant\D{0,4}(\d+(?:\.\d+)?)", r"MF\D{0,4}(\d+(?:\.\d+)?)" ], text)
    mf = float(const.group(1)) if const else 1.0

    if pres and prev:
        p_val, pr_val = float(pres.group(1)), float(prev.group(1))
        if p_val > pr_val:
            diff = float(p_val - pr_val) * mf
            if "units_kwh" not in out:
                out["units_kwh"] = diff
            elif abs(out["units_kwh"] - diff) > 0.5:
                warnings.append(
                    f"The printed units were read as {out['units_kwh']:g}, but the meter readings "
                    f"give {diff:g}. Using {diff:g}; please check."
                )
                out["units_kwh"] = diff

    # --- sanctioned load
    m = _first([
        r"(?:Sanctioned|Sanc\.?|Connected|Conn\.?|Contract)?\s*Load\s*(\d+(?:\.\d+)?)\s*(?:KW|HP)\b",
        r"Load\s*(\d+\.?\d*)\s*KW",
        r"(\d+\.?\d*)\s*KW\s+\d+\.?\d*\s+\d+\.\d{2}",
        r"(\d+(?:\.\d+)?)\s*KW\b"
    ], text)
    if m:
        out["sanctioned_load_kw"] = _num(m.group(1))

    # --- bill amount = "Bill Amount (1-2)", i.e. before penalties/arrears
    m = _first([
        r"Am\w{2,4}\s*\(\s*\w\s*-\s*\w\s*\)\s*" + MONEY,
        r"(?:Cur\.?\s*Demand|Current\s*Demand|Cur\.?\s*Dem)\s*(?:Payable)?\D{0,8}" + MONEY,
        r"(?:Net\s*Amount|Net\s*Payable|Bill\s*Amount|Amount\s*Payable|Total\s*Payable)\D{0,8}" + MONEY,
    ], text)
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
    m = _first([
        r"(?:Recorded\s*M\w{1,2}|Recorded\s*Demand|Max(?:imum)?\s*Demand|RMD)\D{0,6}(\d+(?:\.\d+)?)"
    ], text)
    if m:
        out["recorded_md_kw"] = _num(m.group(1))

    # --- penalty (information only; not part of the check)
    m = _first([
        r"Load\W{0,3}\w{0,4}\W{0,2}P[ea]n\w*\s*" + MONEY,
        r"(?:Ex(?:cess)?\.?\s*Load\s*Penalty|MD\s*Penalty|Penalty)\D{0,6}" + MONEY
    ], text)
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

    # Subsidy sanity check (Gruha Jyothi caps at 200 units/mo)
    # If OCR missed a decimal point (e.g. 1444 -> 144.4 or 1440 -> 144.0)
    sub = out.get("subsidy_units", 0.0)
    if sub > 400:
        if (sub / 10) <= 200:
            out["subsidy_units"] = round(sub / 10, 2)
        else:
            out["subsidy_units"] = 0.0

    # Collect candidate numbers for user suggestions
    candidates = []
    seen = set()
    for cm in re.finditer(r"\b(\d+(?:\.\d{1,2})?)\b", text):
        val = float(cm.group(1))
        if 0 < val < 50000 and val not in seen:
            seen.add(val)
            candidates.append(val)
    out["candidates"] = candidates[:15]

    out["warnings"] = warnings
    out["missing"] = [k for k in ("units_kwh", "sanctioned_load_kw", "amount_billed") if k not in out]
    return out
