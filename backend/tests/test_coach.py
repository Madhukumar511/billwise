from pathlib import Path

from app.services.coach import build_coach
from app.services.tariff_engine import Tariff

T = Tariff.from_file(Path(__file__).resolve().parents[2] / "tariffs" / "sample_domestic.json")
SEG = [(236.15, 0.02), (98.85, 0.32)]


def titles(c):
    return " | ".join(t["title"] for t in c["tips"])


def test_bill1_free_limit_tip():
    c = build_coach(T, 94, 3, 67, billing_days=31)
    assert c["net"] == 173.94 and c["gross"] == 1055.55 and c["subsidy"] == 881.61
    assert 6.3 < c["marginal_cost_per_unit"] < 6.6  # 5.80 - 0.23 + 0.35 + tax
    tip = c["tips"][0]
    assert "free limit" in tip["title"] and tip["saving_inr"] == 173.94
    assert "27 units over" in tip["text"]


def test_bill2_has_penalty_and_multimonth_tips():
    c = build_coach(T, 335, 2, 272.47, 61, SEG, md_penalty=337.5, recorded_md_kw=2.75)
    t = titles(c)
    assert "Peak-demand penalty" in t and "multi-month" in t and "free limit" in t
    assert "2.75 kW" in " ".join(x["text"] for x in c["tips"])


def test_inside_free_limit():
    c = build_coach(T, 60, 3, 67, billing_days=30)
    assert c["net"] == 0.0 and "inside your free limit" in titles(c)


def test_no_subsidy_gets_ten_percent_tip():
    c = build_coach(T, 200, 3, 0, billing_days=30)
    assert "10% cut" in titles(c) and c["tips"][0]["saving_inr"] > 0


def test_flagged_bill_tells_user_what_to_do():
    c = build_coach(T, 94, 3, 67, billing_days=31, flagged=True, variance=86.06)
    assert c["tips"][0]["title"] == "Your bill may be wrong"
