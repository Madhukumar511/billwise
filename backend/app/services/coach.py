"""Savings coach: turns the engine's numbers into plain-language advice.

Rule-based on purpose: every figure comes from the tariff engine, so nothing is
invented. (An LLM can later REPHRASE these facts, but never calculate them.)
"""
from __future__ import annotations

from .tariff_engine import Tariff, compute_net_bill

# Approximate grid emission factor, for illustration only.
CO2_KG_PER_KWH = 0.71
# Typical power draw, for "what does this mean in daily life" comparisons.
APPLIANCES = [("a 1.5-ton AC", 1.5), ("a water heater", 2.0)]


def _rs(x: float) -> str:
    return f"Rs {x:,.2f}"


def build_coach(
    tariff: Tariff,
    units: float,
    load_kw: float,
    subsidy_units: float = 0.0,
    billing_days: int | None = None,
    fppca_segments=None,
    flagged: bool = False,
    variance: float = 0.0,
    md_penalty: float | None = None,
    recorded_md_kw: float | None = None,
) -> dict:
    kw = dict(billing_days=billing_days, fppca_segments=fppca_segments)

    def net_at(u: float) -> float:
        return float(compute_net_bill(tariff, u, load_kw, subsidy_units, **kw).net)

    now = compute_net_bill(tariff, units, load_kw, subsidy_units, **kw)
    net = float(now.net)
    gross = float(now.gross.total)
    sub = float(now.subsidy.total) if now.subsidy else 0.0
    days = billing_days or 30
    per_day = units / days
    marginal = net_at(units + 1) - net

    # ---------- plain-language explanation
    summary = [f"You used {units:g} units in {days} days (about {per_day:.1f} units a day)."]
    if subsidy_units > 0:
        covered = min(units, subsidy_units)
        summary.append(
            f"{covered:g} of those units were covered by the Gruha Jyothi subsidy, "
            f"so you were charged for {max(units - covered, 0):g}."
        )
        summary.append(
            f"The full bill would have been {_rs(gross)}. The subsidy took off {_rs(sub)}, "
            f"leaving {_rs(net)}."
        )
    else:
        summary.append(f"No subsidy applies to this bill, so you pay {_rs(net)}.")
    if marginal > 0:
        summary.append(
            f"Each extra unit costs you about {_rs(marginal)} (energy, surcharges and tax together)."
        )

    tips: list[dict] = []

    # ---------- if the check failed
    if flagged:
        tips.append({
            "title": "Your bill may be wrong",
            "text": (
                f"Your bill differs from our calculation by {_rs(abs(variance))}. Ask your BESCOM "
                "section office for the itemised calculation and meter-reading history, and confirm "
                "that your tariff category and sanctioned load are correct."
            ),
        })

    # ---------- free-limit tip (Gruha Jyothi)
    if subsidy_units > 0 and units > subsidy_units:
        over = units - subsidy_units
        saving = net - net_at(subsidy_units)
        over_per_day = over / days
        allowance = subsidy_units / days
        comparisons = " or ".join(
            f"{over_per_day / kwh * 60:.0f} minutes of {name}" for name, kwh in APPLIANCES
        )
        tips.append({
            "title": f"Stay within your free limit to save up to {_rs(saving)}",
            "text": (
                f"Your free allowance is about {allowance:.1f} units a day and you averaged "
                f"{per_day:.1f}. You went {over:g} units over. Cutting {over_per_day:.1f} units a day "
                f"is roughly {comparisons} less each day. That would also avoid about "
                f"{over * CO2_KG_PER_KWH:.0f} kg of CO2 (approximate grid average)."
            ),
            "saving_inr": round(saving, 2),
        })
    elif subsidy_units > 0:
        tips.append({
            "title": "You are inside your free limit",
            "text": (
                f"You used {units:g} of {subsidy_units:g} free units. Keep usage below the limit "
                "to keep the electricity charge at zero."
            ),
        })
    elif units > 0:
        cut = units * 0.10
        saving = net - net_at(units - cut)
        tips.append({
            "title": f"A 10% cut would save about {_rs(saving)}",
            "text": (
                f"Cutting {cut:.0f} units (10%) saves roughly {_rs(saving)} and about "
                f"{cut * CO2_KG_PER_KWH:.0f} kg of CO2. Start with the biggest users: AC, water "
                "heater, refrigerator age and standby devices."
            ),
            "saving_inr": round(saving, 2),
        })

    # ---------- peak-demand penalty
    if md_penalty and md_penalty > 0:
        peak = (
            f"The meter recorded a peak of {recorded_md_kw:g} kW, above your sanctioned load of "
            f"{load_kw:g} kW. " if recorded_md_kw and recorded_md_kw > load_kw else ""
        )
        tips.append({
            "title": f"Peak-demand penalty of {_rs(md_penalty)}",
            "text": (
                f"This bill includes a penalty of {_rs(md_penalty)}. {peak}Avoid running several heavy "
                "appliances (AC, water heater, motor) at the same time, and ask your BESCOM office "
                "whether raising the sanctioned load would cost less than repeating this penalty."
            ),
            "saving_inr": round(md_penalty, 2),
        })

    # ---------- multi-month note
    if billing_days and billing_days > 45:
        tips.append({
            "title": "This is a multi-month bill",
            "text": (
                f"It covers {billing_days} days, so the fixed charge and your free units are scaled "
                "up. Ask BESCOM to read your meter every month so one big bill does not hide "
                "unusual usage."
            ),
        })

    return {
        "summary": summary,
        "tips": tips,
        "marginal_cost_per_unit": round(marginal, 2),
        "gross": round(gross, 2),
        "subsidy": round(sub, 2),
        "net": round(net, 2),
    }
