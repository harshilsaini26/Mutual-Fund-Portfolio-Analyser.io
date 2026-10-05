"""`fund_growth`: "What would Rs 10,000 have become?". MODULE_6.md §8.2.

The picture a first-time reader understands without a glossary: one line for
the fund, one for its benchmark with dividends included, both starting at
Rs 10,000 on the same day. The period tabs refetch this panel alone.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.common.types import SchemeId
from src.m2_fund.paths import growth_path, price_history
from src.m2_fund.risk import confidence_from_obs
from src.m2_fund.windows import window_start
from src.m6_views.builder import Scope
from src.m6_views.builders.fund.common import (
    INDEX_PROXY,
    INDEX_WITHHELD,
    NO_FUND,
    FundQuality,
    points,
    rupees,
    tabs,
    thin,
    window_of,
    withholds_index,
)
from src.m6_views.builders.fund.nav import price_chart
from src.m6_views.compose import ok_envelope
from src.m6_views.deps import Deps
from src.m6_views.envelope import ViewEnvelope
from src.m6_views.format import format_date
from src.m6_views.registry import VIEW_DEFS, register
from src.m6_views.states import empty_envelope

VIEW_ID = "fund_growth"
#: The switch's two faces: the growth chart and the price chart.
SWITCH = ["What ₹10,000 became", "Price per unit"]


@register
class FundGrowthBuilder:
    view_id = VIEW_ID

    def __init__(self, deps: Deps) -> None:
        self.market = deps.market

    def build(self, scope: Scope, params: dict[str, Any]) -> ViewEnvelope:
        question = VIEW_DEFS[VIEW_ID].question
        if not scope.scope_id:
            return empty_envelope(VIEW_ID, question, scope, NO_FUND)
        scheme = SchemeId(scope.scope_id)
        navs, levels, index_id = price_history(self.market, scheme, scope.as_of)
        key = window_of(params)
        start = (
            date.min if key == "max" or not navs
            else window_start(navs[-1].nav_date, key)
        )
        path = growth_path(navs, levels, start)
        # Over the whole record a benchmark younger than the fund is dropped (the
        # two lines start on one day, or the fund is drawn alone), so a reader of
        # "All" never saw it. Start where the benchmark does instead; the price per
        # unit beside it keeps the whole record (UI/UX critique F-06).
        late = False
        if key == "max" and path is not None and levels and all(
                b is None for _, _, b in path.points):
            later = growth_path(navs, levels, min(levels))
            if later is not None and any(b is not None for _, _, b in later.points):
                path, late = later, True
        if path is None:
            return empty_envelope(
                VIEW_ID, question, scope,
                f"Fewer than two prices are on record for {scheme} in this "
                f"period. python -m jobs.backfill_scheme_nav --scheme {scheme} "
                f"loads its history.",
            )

        facts = self.market.scheme_facts(scheme)
        name = facts.name if facts else str(scheme)
        bench = facts.benchmark_name if facts else None
        end, fund_end, bench_end = path.points[-1]
        headline = (
            f"₹10,000 put into {name} on {format_date(path.start)} was worth "
            f"{rupees(fund_end)} on {format_date(end)}"
        )
        headline += (
            f"; the same ₹10,000 in the {bench} index, dividends included, "
            f"was worth {rupees(bench_end)}."
            if bench and bench_end is not None
            else "."
        )

        caveats: list[str] = []
        if late:
            caveats.append(
                f"Drawn from {format_date(path.start)}, the first day its benchmark "
                f"has prices; the price per unit goes back to "
                f"{format_date(navs[0].nav_date)}."
            )
        if key != "max" and path.start > start:
            caveats.append(
                f"Prices on record begin on {format_date(path.start)}, after "
                f"this period's start, so both lines begin there."
            )
        if withholds_index(self.market) and index_id is None:
            caveats.append(INDEX_WITHHELD)
        elif index_id is None:
            caveats.append(
                "No benchmark index is on record for this fund, so only the "
                "fund is drawn."
            )
        elif bench_end is None:
            caveats.append(
                f"{bench or index_id} is on record as its benchmark, but its "
                f"prices do not cover this period, so the fund is drawn alone."
                + ("" if withholds_index(self.market)
                   else " python -m jobs.fetch_index --held loads it.")
            )
        elif withholds_index(self.market):
            caveats.append(INDEX_PROXY)

        kept = thin(path.points)
        series = [
            {"name": name, "role": "fund",
             "points": points([(d, f) for d, f, _ in kept], rupees)},
        ]
        if bench and any(b is not None for _, _, b in kept):
            series.append(
                {"name": f"{bench} (with dividends)", "role": "benchmark",
                 "points": points([(d, b) for d, _, b in kept], rupees)}
            )
        # The published price per unit beside it, behind a switch: the page's
        # "Price history" drew the same line again (design review, 2026-10-04).
        price = price_chart(self.market, scheme, scope.as_of,
                            navs[0].nav_date if late else path.start)
        # `log`: a log-scale switch beside the periods, so a long record's early
        # years are not flattened under its later ones (F-06).
        charts = [{"kind": "line", "title": question, "y": "inr", "series": series,
                   "log": True}]
        prices: dict[date, Decimal] = {}
        if price is not None:
            chart, said, prices = price
            charts.append(chart)
            headline += " " + said
        rows = [
            {"date": d, "fund_value_inr": f, "benchmark_value_inr": b,
             "nav": prices.get(d)}
            for d, f, b in kept
        ]
        return ok_envelope(
            view_id=VIEW_ID,
            scope=scope,
            payload={
                "headline": headline,
                "tabs": tabs(VIEW_ID, str(scheme), key),
                "charts": charts,
                "switch": SWITCH if price is not None else None,
                "columns": [
                    {"key": "date", "label": "Date", "kind": "date"},
                    {"key": "fund_value_inr", "label": name, "kind": "inr"},
                    {"key": "benchmark_value_inr", "label": "Benchmark", "kind": "inr"},
                    {"key": "nav", "label": "NAV", "kind": "nav"},
                ],
                "rows": rows,
            },
            quality=FundQuality(
                (scope.as_of - end).days, confidence_from_obs((end - path.start).days)
            ),
            data_as_of=end,
            source_modules=["m2", "m0"],
            row_count=len(rows),
            params=params,
            extra_caveats=caveats,
        )


__all__ = ["FundGrowthBuilder"]
