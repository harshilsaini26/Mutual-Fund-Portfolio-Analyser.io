"""What a SIP would have become, by the ledger's own rules (SPEC_SIP_WHAT_IF §4.5).

`tests/fixtures/sip_cases.json` is what `node --test tests/js/sip.test.mjs` holds the
/sip/ page's JavaScript to. This derives every expected figure again here, with
`Decimal`, the ledger's rounding (`test_portfolio_cases._allot`) and M1's `xirr`, so
the file is the ledger's answer and not numbers written to match the JavaScript.

Worked by hand, the first case's fund A (₹1,000 on the 5th of Jan, Feb and Mar 2024,
NAVs 10, 8 and 12): stamp duty ₹0.05 each, so ₹999.95 buys 99.995, 124.994 and 83.329
units; 308.318 units at 12 are ₹3,699.82. On 5 Feb it held 224.989 units at 8,
₹1,799.91 against ₹2,000 put in: 10.0045% below, its lowest. Funds B (₹3,147.47) and C
(₹3,024.86) work the same way.

What this does not prove: the selection rules (which funds are in the range, the
valuation date) are restated here from the spec, so a misreading shared by both
sides would pass. The node tests check those rules on their own small cases.
"""

from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest
from src.m1_ledger.returns import xirr

from tests.unit.test_portfolio_cases import _allot

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "sip_cases.json")
    .read_text(encoding="utf-8")
)["cases"]
PAISA, RATIO = Decimal("0.01"), Decimal("0.00000001")
STALE_DAYS = 7


def _months_back(y: int, m: int, n: int) -> tuple[int, int]:
    total = y * 12 + (m - 1) - n
    return total // 12, total % 12 + 1


def _window(case: dict[str, Any], valued_on: date) -> list[tuple[date, Decimal]]:
    amount = Decimal(case["amount"])
    if case["mode"] == "once":
        if case.get("from"):
            on = date.fromisoformat(case["from"])
        else:
            y = valued_on.year - case["years"]
            on = date(y, valued_on.month,
                      min(valued_on.day, calendar.monthrange(y, valued_on.month)[1]))
        return [(on, amount)]
    day = case["day"]
    end = (valued_on.year, valued_on.month)
    if min(day, calendar.monthrange(*end)[1]) > valued_on.day:
        end = _months_back(*end, 1)
    start = (tuple(map(int, case["from"].split("-"))) if case.get("from")
             else _months_back(*end, 12 * case["years"] - 1))
    y, m = start
    out = []
    while (y, m) <= end:
        out.append((date(y, m, min(day, calendar.monthrange(y, m)[1])), amount))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _outcome(buys: list[tuple[date, Decimal]], navs: list[tuple[date, Decimal]],
             valued_on: date) -> dict[str, Any]:
    navs = [(d, v) for d, v in navs if d <= valued_on]
    # In a range every purchase is priced, so each lot is there.
    lots = [(d, a, lot) for d, a in buys if (lot := _allot(a, d, navs)) is not None]
    units = sum((Decimal(lot["units"]) for _, _, lot in lots), Decimal(0))
    last_date, last_nav = navs[-1]
    value = (units * last_nav).quantize(PAISA, ROUND_HALF_UP)
    put_in = sum((a for _, a, _ in lots), Decimal(0))
    rate = xirr([(d, -a) for d, a, _ in lots] + [(last_date, value)])
    # The lowest point, from the day after the first purchase is priced: on that day
    # only its stamp duty is off it, which no fund could avoid (a ruling on §4.5).
    first = date.fromisoformat(lots[0][2]["nav_date"])
    low, low_on = Decimal(0), None
    for d, nav in navs:
        if d <= first:
            continue
        held = [(a, lot) for _, a, lot in lots
                if date.fromisoformat(lot["nav_date"]) <= d]
        paid = sum((a for a, _ in held), Decimal(0))
        worth = (sum((Decimal(lot["units"]) for _, lot in held), Decimal(0)) * nav
                 ).quantize(PAISA, ROUND_HALF_UP)
        fall = (worth - paid) / paid
        if fall < low:
            low, low_on = fall, d
    return {"value": str(value), "put_in": str(put_in),
            "xirr": None if rate is None else f"{rate:.8f}",
            "low": f"{low.quantize(RATIO, ROUND_HALF_UP):.8f}",
            "low_on": None if low_on is None else low_on.isoformat()}


def _derive(case: dict[str, Any]) -> dict[str, Any]:
    funds = [f for f in case["funds"] if f.get("plan") != "regular"]
    navs = {f["id"]: [(date.fromisoformat(d), Decimal(v)) for d, v in f["navs"]]
            for f in funds if f["navs"]}
    lasts = {fid: n[-1][0] for fid, n in navs.items()}
    latest = max(lasts.values())
    floor = latest - timedelta(days=STALE_DAYS)
    stale = sorted(fid for fid, d in lasts.items() if d < floor)
    valued_on = min(d for d in lasts.values() if d >= floor)
    buys = _window(case, valued_on)
    first = buys[0][0]
    in_range, out = [], []
    for f in funds:
        fid = f["id"]
        reason = ("load" if fid not in navs else "stale" if fid in stale
                  else "later" if navs[fid][0][0] > first else None)
        if reason:
            out.append([fid, reason])
        else:
            in_range.append(fid)
    outcomes = {fid: _outcome(buys, navs[fid], valued_on) for fid in in_range}
    ranked = sorted(in_range, key=lambda fid: (Decimal(outcomes[fid]["value"]), fid))
    put_in = {o.pop("put_in") for o in outcomes.values()}
    return {
        "valued_on": valued_on.isoformat(), "stale": stale,
        "window": {"first": first.isoformat(), "last": buys[-1][0].isoformat(),
                   "count": len(buys)},
        "in_range": in_range, "out": out,
        "put_in": put_in.pop(),
        "outcomes": outcomes,
        "spread": {"n": len(ranked), "min": ranked[0],
                   "middle": ranked[(len(ranked) - 1) // 2], "max": ranked[-1],
                   "below_ever": sum(Decimal(o["low"]) < 0 for o in outcomes.values())},
    }


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_each_case_is_the_ledgers_own_answer(case: dict[str, Any]) -> None:
    assert _derive(case) == case["expect"]
