"""What a SIP would have become, in `Decimal`. SPEC_SIP_WHAT_IF §4.3 to §4.5, §5.1.

The /sip/ page works out its exact answer in the browser (`portfolio-math.js`:
`windowOf`, `valuationDate`, `poolOf`, `outcome`, `spread`, `indexFor`). This is the
same arithmetic for the build's overview of kinds, `data/sip/kinds.json`: every
ranked kind, for ₹1,000 a month and ₹1,00,000 once, over the four standard periods,
which the page scales to the visitor's amount. The two are pinned to each other by
`tests/fixtures/sip_cases.json`, and this to Your portfolio's arithmetic by
`tests/fixtures/portfolio_cases.json` (`tests/unit/test_sip_kinds.py`).

Rounding is the ledger's: stamp duty to the paisa, units to the thousandth, worth to
the paisa, each half up.
"""

from __future__ import annotations

import calendar
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.m1_ledger.returns import xirr

DUTY_FROM = date(2020, 7, 1)     # stamp duty on purchases from this date
DUTY_RATE = Decimal("0.00005")
PAISA, MILLI = Decimal("0.01"), Decimal("0.001")
STALE_DAYS = 7                   # a fund this far behind the newest price is left out
SIP_DAY = 5
UNIT = {"sip": Decimal("1000.00"), "once": Decimal("100000.00")}
PERIODS = (1, 3, 5, 10)
MIN_RANGE = 3                    # fewer funds than this is not a range (§4.6)
VERSION = 1

Buy = tuple[date, Decimal]


@dataclass(frozen=True)
class Prices:
    """One fund's NAVs, oldest first, as its file on the site has them."""

    dates: list[date]
    navs: list[Decimal]


@dataclass(frozen=True)
class Lot:
    on: date
    amount: Decimal
    nav_date: date
    nav: Decimal
    duty: Decimal
    units: Decimal


@dataclass(frozen=True)
class Position:
    lots: list[Lot]
    units: Decimal
    value: Decimal
    value_date: date
    xirr: Decimal | None


@dataclass(frozen=True)
class Outcome:
    value: Decimal
    put_in: Decimal
    xirr: Decimal | None
    low: Decimal            # the most it stood below what had been put in, or 0
    low_on: date | None


@dataclass(frozen=True)
class Valued:
    valued_on: date
    latest: date
    stale: list[str]


@dataclass(frozen=True)
class Pool:
    in_range: list[str]
    out: list[tuple[str, str]]    # (fund, "load" | "stale" | "later")


def allot(amount: Decimal, on: date, prices: Prices) -> Lot | None:
    """A purchase on `on` at the first NAV on or after it; None if there is none."""
    i = bisect_left(prices.dates, on)
    if i == len(prices.dates):
        return None
    nav = prices.navs[i]
    duty = ((amount * DUTY_RATE).quantize(PAISA, ROUND_HALF_UP)
            if on >= DUTY_FROM else Decimal("0.00"))
    units = ((amount - duty) / nav).quantize(MILLI, ROUND_HALF_UP)
    return Lot(on, amount, prices.dates[i], nav, duty, units)


def _worth(lots: list[Lot], nav: Decimal) -> Decimal:
    return (sum((lot.units for lot in lots), Decimal(0)) * nav).quantize(
        PAISA, ROUND_HALF_UP)


def _priced(buys: list[Buy], prices: Prices) -> list[Lot]:
    return [lot for on, amount in buys if (lot := allot(amount, on, prices)) is not None]


def position(buys: list[Buy], prices: Prices) -> Position:
    """The priced purchases, valued at the last NAV, with their XIRR."""
    lots = _priced(buys, prices)
    value = _worth(lots, prices.navs[-1])
    rate = xirr([(lot.on, -lot.amount) for lot in lots] + [(prices.dates[-1], value)])
    return Position(lots, sum((lot.units for lot in lots), Decimal(0)), value,
                    prices.dates[-1], rate)


def cut(prices: Prices, until: date) -> Prices:
    """The NAVs dated on or before `until`: a range is valued on one date, never later."""
    i = bisect_right(prices.dates, until)
    return Prices(prices.dates[:i], prices.navs[:i])


def _falls(lots: list[Lot], prices: Prices) -> Iterator[tuple[date, Decimal]]:
    """Each day's worth against what had been put in by then, as a fraction of it,
    from the day after the first purchase is priced: on that day only its stamp duty
    is off, which no fund could avoid."""
    held = sorted(lots, key=lambda lot: lot.nav_date)
    if not held:
        return
    k, units, paid = 0, Decimal(0), Decimal(0)
    for i in range(bisect_right(prices.dates, held[0].nav_date), len(prices.dates)):
        on = prices.dates[i]
        while k < len(held) and held[k].nav_date <= on:
            units += held[k].units
            paid += held[k].amount
            k += 1
        worth = (units * prices.navs[i]).quantize(PAISA, ROUND_HALF_UP)
        yield on, (worth - paid) / paid


def outcome(buys: list[Buy], prices: Prices, valued_on: date) -> Outcome:
    """One fund on one window, valued on `valued_on`, with its lowest point."""
    priced = cut(prices, valued_on)
    held = position(buys, priced)
    low, low_on = Decimal(0), None
    for on, fall in _falls(held.lots, priced):
        if fall < low:
            low, low_on = fall, on
    return Outcome(held.value, sum((lot.amount for lot in held.lots), Decimal(0)),
                   held.xirr, low, low_on)


def valuation_date(lasts: Mapping[str, date]) -> Valued | None:
    """§4.3: the earliest last price among funds priced within 7 days of the newest."""
    if not lasts:
        return None
    latest = max(lasts.values())
    floor = latest - timedelta(days=STALE_DAYS)
    return Valued(min(d for d in lasts.values() if d >= floor), latest,
                  sorted(fid for fid, d in lasts.items() if d < floor))


def _month_back(y: int, m: int, n: int) -> tuple[int, int]:
    total = y * 12 + (m - 1) - n
    return total // 12, total % 12 + 1


def _on(y: int, m: int, day: int) -> date:
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def sip_dates(day: int, start: tuple[int, ...], end: tuple[int, ...]) -> list[date]:
    """An instalment on `day` (or the month's last day) of every month, start to end."""
    (y, m), out = start, []
    while (y, m) <= end:
        out.append(_on(y, m, day))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def window(mode: str, amount: Decimal, valued_on: date, *, years: int | None = None,
           start: str | None = None, day: int = SIP_DAY) -> list[Buy]:
    """§4.3. Once: on `start`, or `years` before the valuation date. Monthly: the last
    instalment in the valuation date's month if its day has come, else the month
    before, and 12 a year of them, or from the month `start`."""
    if mode == "once":
        on = (date.fromisoformat(start) if start
              else _on(valued_on.year - (years or 0), valued_on.month, valued_on.day))
        if on >= valued_on:
            raise ValueError(f"{on} is not before the valuation date {valued_on}")
        return [(on, amount)]
    end = (valued_on.year, valued_on.month)
    if _on(*end, day) > valued_on:
        end = _month_back(*end, 1)
    first = (tuple(map(int, start.split("-"))) if start
             else _month_back(*end, 12 * (years or 0) - 1))
    return [(on, amount) for on in sip_dates(day, first, end)]


def pool(ids: list[str], prices: Mapping[str, Prices], first: date, latest: date) -> Pool:
    """§4.4: every fund in the range or out of it with one reason, in this order of
    precedence: its prices did not load, it has no recent price, it started later."""
    floor = latest - timedelta(days=STALE_DAYS)
    in_range, out = [], []
    for fid in ids:
        p = prices.get(fid)
        reason = ("load" if p is None or not p.dates else "stale" if p.dates[-1] < floor
                  else "later" if p.dates[0] > first else None)
        if reason:
            out.append((fid, reason))
        else:
            in_range.append(fid)
    return Pool(in_range, out)


def spread(values: Mapping[str, Decimal]) -> list[str]:
    """The funds by worth, lowest first, ties by id."""
    return sorted(values, key=lambda fid: (values[fid], fid))


def middle(ranked: list[str]) -> str:
    """The lower middle: never a fund that is not there."""
    return ranked[(len(ranked) - 1) // 2]


def index_for(funds: list[dict[str, Any]], category: str) -> str | None:
    """The index fund most of the kind are benchmarked to; ties to the longer
    history, then the id."""
    ids = {f["id"]: f for f in funds}
    named = Counter(f["tracker"] for f in funds
                    if f["category"] == category and f.get("tracker") in ids)
    if not named:
        return None
    best: str = min(named, key=lambda fid: (
        -named[fid], ids[fid].get("prices_from") or "9", fid))
    return best


def _range(ids: list[str], index: str | None, prices: Mapping[str, Prices],
           buys: list[Buy], valued_on: date, latest: date) -> dict[str, Any] | None:
    first = buys[0][0]
    eligible = pool(ids, prices, first, latest).in_range
    if len(eligible) < MIN_RANGE:
        return None
    priced = {fid: cut(prices[fid], valued_on) for fid in eligible}
    lots = {fid: _priced(buys, p) for fid, p in priced.items()}
    values = {fid: _worth(lots[fid], priced[fid].navs[-1]) for fid in eligible}
    ranked = spread(values)
    mid = outcome(buys, prices[middle(ranked)], valued_on)
    idx = None
    if index is not None:
        both = max(latest, prices[index].dates[-1]) if index in prices else latest
        if pool([index], prices, first, both).in_range:
            worth = outcome(buys, prices[index], valued_on).value
            idx = {"id": index, "worth": str(worth)}
    return {
        "first": first.isoformat(), "last": buys[-1][0].isoformat(), "count": len(buys),
        "eligible": len(eligible), "put_in": str(sum((a for _, a in buys), Decimal(0))),
        "min": str(values[ranked[0]]), "middle": str(mid.value),
        "max": str(values[ranked[-1]]),
        "middle_xirr": None if mid.xirr is None else f"{mid.xirr:.4f}",
        "middle_low": f"{mid.low:.4f}",
        # Only whether each fund ever stood below: the first fall answers it.
        "below_ever": sum(any(f < 0 for _, f in _falls(lots[fid], priced[fid]))
                          for fid in eligible),
        "index": idx,
    }


def overview(kinds: list[dict[str, str]], funds: list[dict[str, Any]],
             prices: Mapping[str, Prices]) -> dict[str, Any]:
    """`data/sip/kinds.json` (§5.1.2). `kinds` in the page's order, each with `key`,
    `name`, `family` and `about`; `funds` the Direct funds with `id`, `category`,
    `tracker` and `size`; `prices` each fund's NAVs (a fund without is "load").

    Each kind is valued on its own date by the page's rule (§4.3), so a kind's
    figure here is what choosing it on the page shows, scaled; live kinds land a
    day or so apart. One date for all (the spec's "per kind, then the earliest")
    put the overview's row for the kind on the page ₹300 in ₹73,754 off the exact
    answer above it, and let a kind whose funds had stopped (Low duration, one
    fund, last priced 2022) move every kind back years. A kind more than 7 days
    behind the newest price anywhere has no range."""
    members = {k["key"]: [f["id"] for f in funds if f["category"] == k["key"]]
               for k in kinds}
    lasts = {key: {fid: prices[fid].dates[-1] for fid in ids
                   if fid in prices and prices[fid].dates}
             for key, ids in members.items()}
    newest = max((d for one in lasts.values() for d in one.values()), default=None)
    out: list[dict[str, Any]] = []
    for k in kinds:
        key, ids = k["key"], members[k["key"]]
        v = valuation_date(lasts[key])
        if v is not None and newest is not None and (
                v.latest < newest - timedelta(days=STALE_DAYS)):
            v = None
        sizes = [Decimal(f["size"]) for f in funds
                 if f["category"] == key and f.get("size")]
        index = index_for(funds, key)
        windows: dict[str, dict[str, Any]] = {}
        for mode in ("sip", "once"):
            windows[mode] = {
                str(years): None if v is None else _range(
                    ids, index, prices,
                    window(mode, UNIT[mode], v.valued_on, years=years),
                    v.valued_on, v.latest)
                for years in PERIODS}
        out.append({"category": key, "name": k["name"], "family": k["family"],
                    "about": k["about"], "funds": len(ids),
                    "assets": str(sum(sizes, Decimal(0))) if sizes else None,
                    "valued_on": None if v is None else v.valued_on.isoformat(),
                    **windows})
    dates: list[str] = [k["valued_on"] for k in out if k["valued_on"]]
    return {"version": VERSION, "valued_on": min(dates) if dates else None,
            "day": SIP_DAY, "unit": {m: str(a) for m, a in UNIT.items()}, "kinds": out}
