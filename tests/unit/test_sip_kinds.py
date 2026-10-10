"""M2's twin of the /sip/ page's arithmetic (SPEC_SIP_WHAT_IF §4.3 to §4.5, §5.1.4).

`src/m2_fund/sip.py` computes the build's overview of kinds (`data/sip/kinds.json`);
`portfolio-math.js` computes the page's exact answer. Both are held to
`tests/fixtures/sip_cases.json` (`node --test tests/js/sip.test.mjs` loads it too) and
the twin also to `tests/fixtures/portfolio_cases.json`, so the overview and the page
cannot drift apart.

Worked by hand, the first case's fund A (₹1,000 on the 5th of Jan, Feb and Mar 2024,
NAVs 10, 8 and 12): stamp duty ₹0.05 each, so ₹999.95 buys 99.995, 124.994 and 83.329
units; 308.318 units at 12 are ₹3,699.82. On 5 Feb it held 224.989 units at 8,
₹1,799.91 against ₹2,000 put in: 10.0045% below, its lowest. Funds B (₹3,147.47) and C
(₹3,024.86) work the same way.

What this does not prove: the fixtures' selection rules (which funds are in a range,
the valuation date) are restated from the spec on both sides, so a misreading shared by
both would pass; the node tests check those rules on their own small cases. The
overview tests below build their expected middle with the twin's own `outcome`: they
prove the overview picks and scales the right fund, not the arithmetic again.
"""

from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from src.m2_fund import sip

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CASES = json.loads((FIXTURES / "sip_cases.json").read_text(encoding="utf-8"))["cases"]
PORTFOLIO = json.loads(
    (FIXTURES / "portfolio_cases.json").read_text(encoding="utf-8"))["cases"]
RATIO = Decimal("0.00000001")


def _prices(rows: list[list[str]]) -> sip.Prices:
    return sip.Prices([date.fromisoformat(d) for d, _ in rows],
                      [Decimal(v) for _, v in rows])


def _derive(case: dict[str, Any]) -> dict[str, Any]:
    funds = [f for f in case["funds"] if f.get("plan") != "regular"]
    prices = {f["id"]: _prices(f["navs"]) for f in funds if f["navs"]}
    valued = sip.valuation_date({fid: p.dates[-1] for fid, p in prices.items()})
    assert valued is not None
    buys = sip.window(case["mode"], Decimal(case["amount"]), valued.valued_on,
                      years=case.get("years"), start=case.get("from"), day=case["day"])
    pool = sip.pool([f["id"] for f in funds], prices, buys[0][0], valued.latest)
    outcomes = {fid: sip.outcome(buys, prices[fid], valued.valued_on)
                for fid in pool.in_range}
    ranked = sip.spread({fid: o.value for fid, o in outcomes.items()})
    return {
        "valued_on": valued.valued_on.isoformat(), "stale": sorted(valued.stale),
        "window": {"first": buys[0][0].isoformat(), "last": buys[-1][0].isoformat(),
                   "count": len(buys)},
        "in_range": pool.in_range, "out": [list(x) for x in pool.out],
        "put_in": str(sum((a for _, a in buys), Decimal(0))),
        "outcomes": {fid: {"value": str(o.value),
                           "xirr": None if o.xirr is None else f"{o.xirr:.8f}",
                           "low": f"{o.low.quantize(RATIO):.8f}",
                           "low_on": None if o.low_on is None else o.low_on.isoformat()}
                     for fid, o in outcomes.items()},
        "spread": {"n": len(ranked), "min": ranked[0], "middle": sip.middle(ranked),
                   "max": ranked[-1],
                   "below_ever": sum(o.low < 0 for o in outcomes.values())},
    }


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_each_sip_case_is_the_twins_answer(case: dict[str, Any]) -> None:
    assert _derive(case) == case["expect"]


def _portfolio_buys(case: dict[str, Any], today: date) -> list[tuple[date, Decimal]]:
    buys = [(date.fromisoformat(p["date"]), Decimal(p["amount"]))
            for p in case.get("purchases", [])]
    for s in case.get("sips", []):
        start = tuple(map(int, s["start"].split("-")))
        stop = (tuple(map(int, s["stop"].split("-"))) if s["stop"]
                else (today.year, today.month))
        buys += [(d, Decimal(s["amount"])) for d in sip.sip_dates(s["day"], start, stop)
                 if d <= today]
    return sorted(buys)


@pytest.mark.parametrize("case", PORTFOLIO, ids=[c["name"] for c in PORTFOLIO])
def test_each_portfolio_case_is_the_twins_answer(case: dict[str, Any]) -> None:
    """The twin's allotment and value are Your portfolio's, case for case (V1-82)."""
    prices = _prices(case["navs"])
    buys = _portfolio_buys(case, date.fromisoformat(case["today"]))
    lots = [sip.allot(a, d, prices) for d, a in buys]
    held = sip.position(buys, prices)
    assert [None if lot is None else {
        "nav_date": lot.nav_date.isoformat(), "nav": str(lot.nav),
        "stamp_duty": str(lot.duty), "units": str(lot.units)} for lot in lots
    ] == case["expect"]["lots"]
    assert str(held.units) == case["expect"]["units"]
    assert str(held.value) == case["expect"]["value"]
    assert held.value_date.isoformat() == case["expect"]["value_date"]
    assert (None if held.xirr is None else f"{held.xirr:.8f}") == case["expect"]["xirr"]


# --- the overview of kinds (§5.1) --------------------------------------------------

def _daily(first: date, last: date, start: Decimal, step: Decimal) -> sip.Prices:
    """A price on each weekday, moving by `step` a day (falling where it is negative,
    never below 1)."""
    dates, navs, nav, on = [], [], start, first
    while on <= last:
        if on.weekday() < 5:
            dates.append(on)
            navs.append(nav)
            nav = max(Decimal(1), nav + step)
        on += timedelta(days=1)
    return sip.Prices(dates, navs)


END = date(2026, 9, 25)
FUNDS: list[dict[str, Any]] = [
    {"id": "A1", "category": "equity/large_cap", "tracker": "IX", "size": "300"},
    {"id": "A2", "category": "equity/large_cap", "tracker": "IX", "size": "200"},
    {"id": "A3", "category": "equity/large_cap", "tracker": None, "size": None},
    {"id": "A4", "category": "equity/large_cap", "tracker": None, "size": "50"},
    {"id": "IX", "category": "other/index_funds", "tracker": None, "size": "10"},
    {"id": "B1", "category": "debt/liquid", "tracker": None, "size": "5"},
    {"id": "L1", "category": "debt/low_duration", "tracker": None, "size": "1"},
]
PRICES = {
    "A1": _daily(date(2012, 1, 2), END, Decimal(10), Decimal("0.01")),
    "A2": _daily(date(2012, 1, 2), END - timedelta(days=1), Decimal(20),
                 Decimal("0.005")),
    "A3": _daily(date(2020, 1, 1), END, Decimal(15), Decimal("-0.001")),
    "A4": _daily(date(2025, 1, 1), END, Decimal(10), Decimal("0.002")),   # 1 year only
    "IX": _daily(date(2015, 1, 1), END, Decimal(30), Decimal("0.004")),
    "B1": _daily(date(2012, 1, 2), END, Decimal(1000), Decimal("0.1")),
    "L1": _daily(date(2012, 1, 2), date(2022, 8, 5), Decimal(10), Decimal("0.001")),
}
KINDS = [
    {"key": "equity/large_cap", "name": "Large cap", "family": "equity",
     "about": "At least 80% in the 100 largest listed companies."},
    {"key": "debt/liquid", "name": "Liquid", "family": "debt", "about": "Up to 91 days."},
    {"key": "debt/low_duration", "name": "Low duration", "family": "debt", "about": "."},
]


def _overview() -> dict[str, Any]:
    return sip.overview(KINDS, FUNDS, PRICES)


def test_each_kind_is_valued_as_the_page_values_it_at_standard_amounts() -> None:
    """Each kind on its own date by the page's 7-day rule, so a kind's figure here is
    what choosing it on the page shows, scaled; the file's date is the earliest."""
    out = _overview()
    assert out["version"] == 1 and out["day"] == 5
    assert out["unit"] == {"sip": "1000.00", "once": "100000.00"}
    # A2 stops a day early, inside the 7 days: it sets large cap's date, not liquid's.
    assert [k["valued_on"] for k in out["kinds"]] == ["2026-09-24", "2026-09-25", None]
    assert out["valued_on"] == "2026-09-24"
    large = out["kinds"][0]
    assert (large["category"], large["name"], large["family"]) == (
        "equity/large_cap", "Large cap", "equity")
    assert large["funds"] == 4 and large["assets"] == "550"
    assert [k["category"] for k in out["kinds"]] == [
        "equity/large_cap", "debt/liquid", "debt/low_duration"]


def test_a_kind_whose_prices_stopped_has_no_range() -> None:
    """Its own rule would value Low duration (one fund, last priced 2022) in 2022;
    more than 7 days behind the newest price anywhere, it has no range instead."""
    out = _overview()
    assert out["valued_on"] == "2026-09-24"
    low = out["kinds"][2]
    assert low["valued_on"] is None
    assert low["funds"] == 1
    assert all(w is None for mode in ("sip", "once") for w in low[mode].values())


def test_a_window_is_the_range_with_its_middle_fund_and_index() -> None:
    w = _overview()["kinds"][0]["sip"]["5"]
    v = date(2026, 9, 24)
    buys = sip.window("sip", Decimal(1000), v, years=5, day=5)
    assert (w["first"], w["last"], w["count"]) == ("2021-10-05", "2026-09-05", 60)
    assert w["put_in"] == "60000.00"
    # A4 has a year of prices, so three of the four can take every instalment.
    worth = {fid: sip.outcome(buys, PRICES[fid], v) for fid in ("A1", "A2", "A3")}
    ranked = sorted(worth, key=lambda f: (worth[f].value, f))
    assert w["eligible"] == 3
    assert (w["min"], w["middle"], w["max"]) == tuple(
        str(worth[f].value) for f in ranked)
    middle = worth[ranked[1]]
    assert middle.xirr is not None
    assert w["middle_xirr"] == f"{middle.xirr:.4f}"
    assert w["middle_low"] == f"{middle.low:.4f}"
    assert w["below_ever"] == sum(o.low < 0 for o in worth.values())
    assert w["index"] == {"id": "IX",
                          "worth": str(sip.outcome(buys, PRICES["IX"], v).value)}


def test_a_window_too_few_funds_can_take_is_null() -> None:
    large = _overview()["kinds"][0]
    # Ten years back reaches before A3 and A4 began: two funds are not a range.
    assert large["sip"]["10"] is None and large["once"]["10"] is None
    assert large["sip"]["1"] is not None and large["sip"]["1"]["eligible"] == 4
    # One liquid fund: never a range.
    assert all(w is None for w in _overview()["kinds"][1]["sip"].values())


def test_a_once_window_starts_the_same_day_years_back() -> None:
    w = _overview()["kinds"][0]["once"]["3"]
    assert (w["first"], w["last"], w["count"], w["put_in"]) == (
        "2023-09-24", "2023-09-24", 1, "100000.00")


def test_the_29th_of_february_goes_back_to_the_28th() -> None:
    assert sip.window("once", Decimal(1), date(2028, 2, 29), years=1)[0][0] == date(
        2027, 2, 28)
    assert calendar.isleap(2028)
