"""The portfolio page's arithmetic, by the ledger's own rules. DECISIONS V1-82.

`tests/fixtures/portfolio_cases.json` is what `node --test tests/js/` holds the
page's JavaScript to. This derives every expected figure again here, with
`Decimal` and M1's `xirr`, so the file is the ledger's answer and not numbers
written to match the JavaScript.
"""

from __future__ import annotations

import calendar
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest
from src.m1_ledger.returns import xirr

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "portfolio_cases.json")
    .read_text(encoding="utf-8")
)["cases"]
DUTY_FROM = date(2020, 7, 1)
PAISA, MILLI = Decimal("0.01"), Decimal("0.001")


def _allot(
    amount: Decimal, on: date, navs: list[tuple[date, Decimal]]
) -> dict[str, str] | None:
    found = next(((d, v) for d, v in navs if d >= on), None)
    if found is None:
        return None
    nav_date, nav = found
    duty = ((amount * Decimal("0.00005")).quantize(PAISA, ROUND_HALF_UP)
            if on >= DUTY_FROM else Decimal("0.00"))
    units = ((amount - duty) / nav).quantize(MILLI, ROUND_HALF_UP)
    return {"nav_date": nav_date.isoformat(), "nav": str(nav),
            "stamp_duty": str(duty), "units": str(units)}


def _sip_dates(day: int, start: str, stop: str | None, today: date) -> list[date]:
    y, m = map(int, start.split("-"))
    end = tuple(map(int, stop.split("-"))) if stop else (today.year, today.month)
    out = []
    while (y, m) <= end:
        on = date(y, m, min(day, calendar.monthrange(y, m)[1]))
        if on <= today:
            out.append(on)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _derive(case: dict[str, Any]) -> dict[str, Any]:
    navs = [(date.fromisoformat(d), Decimal(v)) for d, v in case["navs"]]
    today = date.fromisoformat(case["today"])
    buys = [(date.fromisoformat(p["date"]), Decimal(p["amount"]))
            for p in case.get("purchases", [])]
    for s in case.get("sips", []):
        buys += [(d, Decimal(s["amount"]))
                 for d in _sip_dates(s["day"], s["start"], s["stop"], today)]
    buys.sort()
    lots = [_allot(a, d, navs) for d, a in buys]
    priced = [(b, lot) for b, lot in zip(buys, lots, strict=True) if lot]
    units = sum((Decimal(lot["units"]) for _, lot in priced), Decimal(0))
    last_date, last_nav = navs[-1]
    value = (units * last_nav).quantize(PAISA, ROUND_HALF_UP)
    rate = xirr([(d, -a) for (d, a), _ in priced] + [(last_date, value)])
    return {"lots": lots, "units": str(units), "value": str(value),
            "value_date": last_date.isoformat(),
            "xirr": None if rate is None else f"{rate:.8f}"}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_each_case_is_the_ledgers_own_answer(case: dict[str, Any]) -> None:
    assert _derive(case) == case["expect"]
