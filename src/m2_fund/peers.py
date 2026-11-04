"""A fund among the funds that do the same job. DECISIONS V1-77; MODULE_2 §11.

**Peers** are the live funds (`m0_data.universe`) in the same canonical category
(`config/categories.yaml`, V1-76) -- which already makes them Direct plan only,
as §11.2 rule 1 requires, and one share class per fund. For a window, only the
funds whose prices span it are ranked: four years of history is not a five-year
record, whatever the window is called.

**Ranks** use the figures `m2_fund.stats` stored for every fund, so a page reads
its category once instead of every peer's history. The spec's rules, and where
they were silent or wrong:
- each metric has a direction (§11.2 rule 4). Worst fall is stored as a negative
  depth, so the smaller fall is the *higher* number; the spec's `lower_better`
  would rank the deepest fall first. The expense ratio (V1-78) ranks the
  cheapest first, and is read from `scheme_ter` rather than the stored windows.
- ties share a rank, 1, 2, 2, 4 (the spec gave no tie rule);
- fewer than `MIN_PEERS` ranked funds is no rank at all, with the reason (the spec
  set no minimum);
- every rank carries how many were ranked of how many are in the category
  (§11.2 rule 3);
- wound-up funds are not included -- nothing records them yet -- so §11.2 rule 2
  (survivorship) is unmet, and each page says so;
- an index fund's peers are the funds that track the same index, read from the
  name after the fund house's ("UTI Nifty 50 Index Fund"), whichever heading AMFI
  filed them under, when there are `MIN_PEERS` of them (design critique,
  2026-11-04: 456 of 550 index funds had no rank, most under AMFI's undivided
  heading, so no page said which Nifty 50 fund did best).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from typing import Any

from src.m0_data.categories import Category, category_of
from src.m0_data.universe import Fund

#: Below this many ranked funds a rank says more about the gaps than the fund.
MIN_PEERS = 5
#: Why a fund in a `ranked: false` category (categories.yaml) has no ranks.
MIXED = ("not ranked: this heading holds funds that do different jobs, so a rank "
         "against them would mean little")
SURVIVORSHIP_CAVEAT = (
    "Ranks compare the funds open today; funds that closed or merged are not "
    "included, which tends to flatter the category's middle."
)


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    window: str
    field: str
    #: True when the higher stored number ranks first.
    higher_first: bool


METRICS = (
    Metric("return_1y", "Return, 1 year", "1y", "return_ann", True),
    Metric("return_3y", "Return, 3 years", "3y", "return_ann", True),
    Metric("return_5y", "Return, 5 years", "5y", "return_ann", True),
    Metric("volatility_3y", "Volatility, 3 years", "3y", "volatility_ann", False),
    # A negative depth: -0.12 is a smaller fall than -0.35, and ranks first.
    Metric("worst_fall_3y", "Deepest fall, 3 years", "3y", "max_dd", True),
    Metric("sharpe_3y", "Return for the risk, 3 years (Sharpe)", "3y", "sharpe", True),
    # Not a window: the newest total TER on record, percent a year.
    Metric("ter", "Expense ratio (TER)", "", "ter", False),
)


@dataclass(frozen=True)
class Rank:
    metric: Metric
    value: Decimal | None
    rank: int | None
    ranked: int
    quartile: int | None
    #: Why there is no rank, when there is none.
    reason: str | None = None
    #: The category's lowest and highest figure among the ranked funds, when
    #: ranked: the ends of the fund page's "compared to peers" bars (V1-80).
    low: Decimal | None = None
    high: Decimal | None = None


@dataclass(frozen=True)
class Point:
    scheme_id: str
    name: str
    volatility: Decimal
    return_ann: Decimal
    #: Fund size in rupees, for the bubble's area (V1-80); None when not on record.
    aum: Decimal | None = None


@dataclass(frozen=True)
class PeerContext:
    scheme_id: str
    category: Category
    in_category: int
    ranks: list[Rank]
    #: Every peer with three years of prices: the category's risk and return.
    points: list[Point]


def competition_rank(value: Decimal, others: list[Decimal], higher_first: bool) -> int:
    """1 + how many are strictly better: ties share a rank (1, 2, 2, 4)."""
    better = sum(1 for o in others if (o > value if higher_first else o < value))
    return better + 1


def quartile(rank: int, ranked: int) -> int:
    """1 for the first quarter of the ranked funds, 4 for the last."""
    return (rank * 4 + ranked - 1) // ranked


@cache
def tracked_index(fund: Fund) -> tuple[str, str] | None:
    """(key, name) of the index an index fund tracks: its name after the fund
    house's, without "Index Fund" ("Nifty 50"), and that with only its letters
    and digits, lower-cased, to match spellings ("NIFTY50"). None for other funds."""
    if not category_of(fund.category).key.startswith("index/"):
        return None
    words, house = fund.name.split(), fund.amc_id.split("_")
    i = 0
    while i < min(len(words), len(house)) and words[i].lower() == house[i]:
        i += 1
    name = re.sub(r"\b(index|fund)\b", " ", " ".join(words[i:]), flags=re.I)
    name = re.sub(r"\s+", " ", re.sub(r"[()]|\s-(?=\s|$)", " ", name)).strip(" -")
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return (key, name) if key else None


def _peers(fund: Fund, funds: list[Fund]) -> tuple[Category, list[Fund]]:
    """Its category and the funds in it: for an index fund with enough others
    tracking its index, those funds; otherwise its canonical category's."""
    tracks = tracked_index(fund)
    if tracks is not None:
        same = [f for f in funds if (t := tracked_index(f)) and t[0] == tracks[0]]
        if len(same) >= MIN_PEERS:
            # The group's commonest spelling, so every page names it alike.
            spelt = Counter(t[1] for f in same if (t := tracked_index(f)))
            name = max(sorted(spelt), key=lambda n: spelt[n])
            return Category(key=f"index/tracks/{tracks[0]}",
                            name=f"{name} index funds", family="other"), same
    category = category_of(fund.category)
    return category, [f for f in funds if category_of(f.category).key == category.key]


def peer_context(market: Any, scheme_id: str) -> PeerContext | None:
    """This fund's category, its ranks in it, and its category's points.

    None when the fund is not a live fund with a Direct plan: there is no peer
    group to place a Regular-only or closed fund in.
    """
    funds = market.live_funds()
    fund = next((f for f in funds if f.scheme_id == scheme_id), None)
    if fund is None:
        return None
    category, same = _peers(fund, funds)
    members = {f.scheme_id: f for f in same}
    stats = {(s.scheme_id, s.window_key): s
             for s in market.window_stats(sorted(members))}
    ters = {sid: t.total for sid, t in market.ters(sorted(members), date.max).items()}

    ranks: list[Rank] = []
    for metric in METRICS:
        values = ters if metric.field == "ter" else {
            sid: getattr(stat, metric.field)
            for sid in members
            if (stat := stats.get((sid, metric.window))) is not None
            and stat.spans and getattr(stat, metric.field) is not None
        }
        own = values.get(scheme_id)
        if not category.ranked:
            ranks.append(Rank(metric, own, None, len(values), None, MIXED))
        elif own is None:
            ranks.append(Rank(metric, None, None, len(values), None,
                              "no expense ratio on record" if metric.field == "ter"
                              else "too little price history for the period"))
        elif len(values) < MIN_PEERS:
            ranks.append(Rank(metric, own, None, len(values), None,
                              f"only {len(values)} of its category's funds"
                              f" {'has' if len(values) == 1 else 'have'} it"))
        else:
            others = [v for sid, v in values.items() if sid != scheme_id]
            position = competition_rank(own, others, metric.higher_first)
            ranks.append(Rank(metric, own, position, len(values),
                              quartile(position, len(values)),
                              low=min(values.values()), high=max(values.values())))

    sizes = market.fund_sizes(sorted(members))
    points = [
        Point(sid, members[sid].name, vol, ret, sizes.get(sid))
        for sid in sorted(members)
        if (stat := stats.get((sid, "3y"))) is not None and stat.spans
        and (vol := stat.volatility_ann) is not None
        and (ret := stat.return_ann) is not None
    ]
    return PeerContext(scheme_id, category, len(members), ranks, points)


__all__ = ["METRICS", "MIN_PEERS", "SURVIVORSHIP_CAVEAT", "Metric", "PeerContext",
           "Point", "Rank", "competition_rank", "peer_context", "quartile",
           "tracked_index"]
