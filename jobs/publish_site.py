"""Build the public fund explorer: a static copy of the fund pages, served by Vercel.

    python -m jobs.publish_site                  # build into site/; nothing leaves
    python -m jobs.publish_site --base ""        # a copy to preview locally
    python -m jobs.publish_site --push           # build, then publish to gh-pages

DECISIONS V1-72. The repository is public, so the site is too, and Pages serves
only files: no Python, no database, no response headers. So every fund page is
rendered here, by the same builders, macro and templates as the server's
(`pages.fund_context`), and written out as HTML beside its CSVs.

What it carries is decided, not incidental:

- **Fund prices and fund houses' own disclosures.** AMFI's NAVs are published
  for programmatic use, and portfolio disclosures are mandated public documents.
- **An aggregator's page, marked.** Holdings read from Groww's pages are
  published with a caveat naming the source (V1-79; V1-72 withheld them). Groww's
  terms of use apply to republishing them.
- **Not NSE's index levels.** They are licensed for personal use (PLAN.md §5.3
  separates that from redistribution), so the market data here withholds them
  (`PublicMarket`). Where an index fund declares the same benchmark as a fund
  (both from their Groww pages), that index fund's own price stands in for the
  index, named as such (V1-81); otherwise the fund is drawn alone, saying why.
- **Never the portfolio.** The ledger here is an empty in-memory database; the
  personal ledger file is not opened, and a test holds that.

`--push` publishes from this machine; the nightly build (`jobs.build_site`,
V1-75) is the other thing that does.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.common.contracts.market import IndexPoint
from src.common.decimals import connect
from src.common.types import IndexId, SchemeId, UserId
from src.m0_data.categories import FAMILIES, category_of
from src.m0_data.config import REPO_ROOT, warehouse_path
from src.m0_data.normalise.index_id import index_key
from src.m0_data.providers.warehouse import SchemeFacts, WarehouseMarketDataProvider
from src.m0_data.store import save as save_navs
from src.m0_data.universe import ISIN, Fund, live_funds, regular_twins
from src.m1_ledger.db import apply_ledger_schema, connect_ledger
from src.m1_ledger.providers.position import SqlitePositionProvider
from src.m2_fund.windows import spans, window_start
from src.m3_lookthrough.providers.sqlite import SqliteLookThroughProvider
from src.m6_views.api.pages import STATIC, fund_context, templates
from src.m6_views.builder import Scope
from src.m6_views.builders import portfolio  # noqa: F401  — registers the builders
from src.m6_views.deps import Deps
from src.m6_views.envelope import ViewEnvelope
from src.m6_views.export.csv import ENCODING, to_csv
from src.m6_views.format import (
    DASH,
    format_date,
    format_fraction,
    format_inr,
    format_pct,
    format_return,
)
from src.m6_views.learn import load as load_learn
from src.m6_views.learn import stale
from src.m6_views.registry import VIEW_DEFS, VIEW_REGISTRY
from src.m6_views.render import range_bars
from src.m6_views.states import empty_envelope, error_envelope

from jobs.fetch_groww import declared_benchmarks
from jobs.landing import landing_candidate, landing_example, landing_pair
from jobs.share_image import fund_card, icon_png, site_card

#: The build's own ceiling. Vercel's Hobby plan states no limit on a static
#: deployment's output (V1-92), but every byte is pushed to gh-pages and deployed
#: each night; past this the page profile needs lightening, not the ceiling raising.
SITE_BUDGET_BYTES = 900 * 1024 * 1024
#: About a year of trading days: below this a fund page is mostly empty panels.
MIN_PRICES = 250
PUBLIC_USER = UserId("PUBLIC")
#: What the public pages load.
STATIC_FILES = (
    "app.css", "app.js", "charts.js", "settings.js", "sections.js", "lenis.css",
    "vendor/echarts.v6.1.0.min.js", "vendor/lenis.v1.3.26.min.js",
    "fonts/rubik-latin-wght-normal.woff2",
    "fonts/terminess-Regular.woff2", "fonts/terminess-Bold.woff2",
    "portfolio-math.js", "kit.js", "portfolio.js", "compare.js", "sip.js",
    "fonts/atkinson-hyperlegible-latin-400-normal.woff2",
    "fonts/atkinson-hyperlegible-latin-700-normal.woff2",
    "favicon.svg",
    # The Learn guides' screenshots (UI/UX critique L-03).
    *sorted(f"learn/{png.name}" for png in (STATIC / "learn").glob("*.png")),
)
#: Where the site is served: a shared link's preview needs a whole address
#: (Open Graph), not a path (UI/UX critique G-11; V1-92).
SITE_URL = "https://didmysipwork.vercel.app"
#: The web manifest's icons, drawn at build time (`share_image.icon_png`).
ICONS = (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180))
#: A file only this job writes, so a rebuild can tell its own output from a
#: directory it must not delete. Named for GitHub Pages, which served the site
#: until V1-92; it means nothing to Vercel and is kept only as this marker.
MARKER = ".nojekyll"
#: How Vercel serves the site (V1-92): it deploys the gh-pages branch as it is,
#: with no build. Pages are linked as folders (/fund/<id>/), so a path without its
#: slash is redirected to it; a file with an extension never is (Vercel's rule).
VERCEL_CONFIG = {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "trailingSlash": True,
}

NOT_BUILT = "This picture could not be built for the public copy."
#: The holdings panel's empty state on the public site. The local app's names
#: commands to run; a public reader has none to run, so they get the reason.
NO_PORTFOLIO = (
    "No portfolio is loaded for this fund yet. This site reads Kotak's and ICICI "
    "Prudential's own monthly disclosures and, for other funds, one aggregator "
    "page per fund, about 100 a night. This fund's turn has not come yet, or its "
    "page lists no holdings this site can match to companies."
)

RETURN_WINDOWS = ("1y", "3y", "5y")
#: The front page's category cards (DECISIONS V1-80, after MF Zone's): the six
#: equity categories most funds sit in, each with its five highest 3-year returns.
LEADER_CATEGORIES = (
    "equity/flexi_cap", "equity/large_cap", "equity/mid_cap",
    "equity/small_cap", "equity/large_mid_cap", "equity/elss",
)
LEADERS_PER_CARD = 5


class SiteTooLarge(RuntimeError):
    """The site has outgrown the build's ceiling (`SITE_BUDGET_BYTES`)."""


#: The id a proxied benchmark carries: never an index id, so nothing can take
#: an index fund's price for the index's own level.
PROXY = "proxy:"
_TRI = re.compile(r"\s*[-(]?\s*(total returns? index|tri)\)?\s*$", re.I)


def trackers(warehouse: Any, declared: dict[str, str]) -> dict[str, list[str]]:
    """Each benchmark (by `index_key`) and the index funds and ETFs that declare
    it, longest price record first: the first is its proxy."""
    kinds = {f.scheme_id: category_of(f.category).key for f in live_funds(warehouse)}
    ids = [s for s in declared if kinds.get(s, "").startswith(("index/", "etf/"))]
    first = dict(warehouse.execute(
        f"SELECT scheme_id, min(nav_date) FROM nav_daily WHERE scheme_id IN"
        f" ({','.join('?' * len(ids))}) GROUP BY scheme_id", ids).fetchall())
    out: dict[str, list[str]] = defaultdict(list)
    for sid in sorted((s for s in ids if s in first), key=lambda s: (str(first[s]), s)):
        out[index_key(declared[sid])].append(sid)
    return out


#: Words a fund's name adds after the index it tracks ("... Nifty 50 Index Fund").
_FUND_TAIL = {"INDEX", "FUND", "FUNDS", "ETF", "FOF", "OF", "EXCHANGE", "TRADED",
              "DIRECT", "PLAN", "GROWTH", "OPTION"}


def named_index(name: str, keys: set[str]) -> str | None:
    """The index an index fund's own name says it tracks, as an `index_key`: the
    longest tail of the name, fund words dropped, that is exactly an index some
    fund declares. Exact, so "Nifty 50 Equal Weight" never borrows "Nifty 50"."""
    words = re.sub(r"[^A-Z0-9]+", " ", name.upper()).split()
    while words and words[-1] in _FUND_TAIL:
        words.pop()
    tails = (index_key(" ".join(words[i:])) for i in range(len(words)))
    return next((key for key in tails if key in keys), None)


def named_benchmarks(
    warehouse: Any, declared: dict[str, str], tracked: dict[str, list[str]]
) -> dict[str, str]:
    """Each index fund or ETF the crawl has not read yet, and the index its name
    names (external audit, 2026-10-04: until then it showed no benchmark)."""
    keys = set(tracked)
    found: dict[str, str] = {}
    for fund in live_funds(warehouse):
        if fund.scheme_id in declared:
            continue
        if not category_of(fund.category).key.startswith(("index/", "etf/")):
            continue
        key = named_index(fund.name, keys)
        if key is not None:
            found[fund.scheme_id] = key
    return found


class PublicMarket(WarehouseMarketDataProvider):
    """The warehouse's market data with every index level withheld (V1-72), and
    an index fund's price in place of each benchmark one tracks (V1-81).

    `index_levels_withheld` is what the fund builders read to say "left out of
    this public copy" rather than "none on record" (`builders/fund/common.py`);
    a fund with a proxy is told apart by its `proxy:` benchmark id.
    """

    index_levels_withheld = True

    def __init__(self, conn: Any, declared: dict[str, str] | None = None) -> None:
        super().__init__(conn)
        self.declared = declared or {}
        self.trackers = trackers(conn, self.declared) if self.declared else {}
        self.named = (named_benchmarks(conn, self.declared, self.trackers)
                      if self.trackers else {})

    def proxy(self, scheme_id: str) -> str | None:
        """The index fund standing in for this fund's benchmark: never itself.
        The benchmark is the one the fund declares, else the one its name names."""
        name = self.declared.get(scheme_id)
        key = index_key(name) if name else self.named.get(scheme_id)
        found = self.trackers.get(key, []) if key else []
        return next((s for s in found if s != scheme_id), None)

    def benchmark_for(self, scheme_id: SchemeId) -> IndexId | None:
        proxy = self.proxy(str(scheme_id))
        return IndexId(PROXY + proxy) if proxy else None

    def index_series(
        self, index_id: IndexId, start: date, end: date
    ) -> list[IndexPoint]:
        if not index_id.startswith(PROXY):
            return []
        return [IndexPoint(index_id, p.nav_date, p.nav) for p in
                self.nav_series(SchemeId(index_id[len(PROXY):]), start, end)]

    def index_level(self, index_id: IndexId, on: date) -> Decimal | None:
        found = self.index_series(index_id, on, on)
        return found[0].level if found else None

    def scheme_facts(self, scheme_id: SchemeId) -> SchemeFacts | None:
        facts = super().scheme_facts(scheme_id)
        proxy = self.proxy(str(scheme_id))
        tracker = super().scheme_facts(SchemeId(proxy)) if proxy else None
        if facts is None or tracker is None:
            return facts
        named = self.declared.get(str(scheme_id)) or self.declared[str(proxy)]
        index = _TRI.sub("", named)
        return replace(facts, benchmark_id=PROXY + str(proxy),
                       benchmark_name=f"{index} (via {tracker.name})")


def public_deps(warehouse: Any, declared: dict[str, str] | None = None) -> Deps:
    """The providers the public pages may read: never a personal ledger.
    `declared` is each fund's benchmark as its Groww page names it."""
    ledger = connect_ledger(":memory:", allow_unencrypted=True)
    apply_ledger_schema(ledger)
    return Deps(
        lookthrough=SqliteLookThroughProvider(ledger, warehouse),
        positions=SqlitePositionProvider(ledger),
        market=PublicMarket(warehouse, declared),
    )


def funds_to_publish(warehouse: Any) -> list[dict[str, str]]:
    """One page per live fund with a year of prices, as its Direct share class.

    The funds are `m0_data.universe.live_funds`, the same set the history
    backfill loads and the peer groups rank (DECISIONS V1-75). ISIN-keyed only: a
    scheme AMFI lists without one is keyed `AMFI:<code>:...`, which is no folder
    name on Windows and no clean URL.
    """
    priced = {
        str(sid) for sid, n in warehouse.execute(
            "SELECT scheme_id, count(*) FROM nav_daily GROUP BY scheme_id"
        )
        if n >= MIN_PRICES
    }
    return [
        {
            "scheme_id": fund.scheme_id,
            "name": fund.name,
            "category": fund.category,
            "amfi_code": fund.amfi_code or "",
            # The site's own category name, not AMFI's heading ("Solution
            # Oriented Schemes ** - Retirement Fund"; UI/UX critique G-05).
            "detail": " · ".join(
                str(x).title() if x in (fund.plan, fund.option) else str(x)
                for x in (category_of(fund.category).name, fund.plan, fund.option)
                if x and x != "unknown"
            ),
        }
        for fund in live_funds(warehouse)
        if fund.scheme_id in priced and ISIN.fullmatch(fund.scheme_id)
    ]


def _return_cell(value: Any) -> dict[str, Any]:
    """One return in the front page's table: the figure as the reader sees it,
    the value it sorts on, and its direction as a symbol as well as a colour
    (§10.3). A window with too little history is a dash, never a zero."""
    if value is None:
        return {"value": "", "label": DASH, "tone": None, "symbol": None}
    number = Decimal(str(value))
    tone = "gain" if number > 0 else "loss" if number < 0 else None
    return {
        "value": str(number),
        "label": format_pct(number * 100, precision=1, signed=True),
        "tone": tone,
        "symbol": {"gain": "▲", "loss": "▼"}.get(tone or ""),
    }


def explorer_row(
    fund: dict[str, str], facts: Any, detail: ViewEnvelope | None,
    peers: ViewEnvelope | None = None,
) -> dict[str, Any]:
    """One fund's row in the front page's table (DECISIONS V1-74).

    Nothing new is computed: the returns are the fund page's own "every figure"
    rows (`fund_xray_header`), the rank is its peer panel's (`fund_peers`), and
    the size, cost and house are the scheme facts its header already shows.
    They are formatted here, in Python (§16.4).
    """
    windows: dict[str, Any] = {}
    if detail is not None and detail.state.value == "ok":
        # A column headed "5 years" shows only a window the prices span (`spans`).
        windows = {
            row["window_key"]: row.get("return_ann")
            for row in detail.payload.get("rows", [])
            if row["window_key"] in RETURN_WINDOWS
            and row.get("obs_days") is not None
            and spans(int(row["obs_days"]), row["window_key"])
        }
    size = facts.aum_inr if facts is not None else None
    ter = facts.ter if facts is not None else None
    category = category_of(fund["category"])
    rank: dict[str, Any] = {}
    if peers is not None and peers.state.value == "ok":
        rank = peers.payload.get("rank_3y") or {}
    return {
        **fund,
        "family": category.family,
        # The canonical name (DECISIONS V1-76), not whichever of AMFI's two
        # spellings this fund house happens to use.
        "category_short": category.name,
        "category_key": category.key,
        "house": (facts.amc_name if facts is not None else None) or "",
        "size_value": str(size) if size is not None else "",
        "size_label": format_inr(size, precision=0) if size is not None else DASH,
        "ter_value": str(ter) if ter is not None else "",
        "ter_label": format_pct(ter, precision=2) if ter is not None else DASH,
        "returns": [_return_cell(windows.get(key)) for key in RETURN_WINDOWS],
        # Sorted by quarter: a rank means something only within its category.
        "rank_value": str(rank["quartile"]) if rank.get("quartile") else "",
        "rank_label": rank.get("label") or DASH,
        "rank_quarter": rank.get("quarter") or "",
    }


#: Explore funds draws this many rows; app.js draws the rest from funds/rows.json
#: (UI/UX critique E-01: all 1,662 at once were 1.88 MB and 31,170 nodes).
EXPLORE_FIRST = 50
#: Its columns: key, heading, the term its `?` explains, figure (right-aligned),
#: and the name a phone's two-line row gives the figure (E-07). The three
#: measures of risk start hidden; the column chooser shows them (E-05).
EXPLORE_COLUMNS = (
    ("name", "Fund", None, False, ""),
    ("cat", "Category", None, False, ""),
    ("size", "Fund size", "aum", True, "Size"),
    ("ter", "Expense ratio", "expense_ratio", True, "Expense ratio"),
    ("r1", "1 year", "annualised_return", True, "1-year return"),
    ("r3", "3 years", "annualised_return", True, "3-year return"),
    ("r5", "5 years", "annualised_return", True, "5-year return"),
    ("rank", "Rank in category, 3 years", "category_rank", True, "Rank"),
    ("vol3", "Volatility, 3 years", "volatility", True, "Volatility"),
    ("fall3", "Deepest fall, 3 years", "max_drawdown", True, "Deepest fall"),
    ("sharpe3", "Sharpe ratio, 3 years", "sharpe", True, "Sharpe"),
)
EXPLORE_HIDDEN = "vol3 fall3 sharpe3"


def explore_row(row: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """One fund in Explore funds' data: its table row's cells as [value, label,
    ...], the value what a column sorts on ("" for none), the label formatted here
    (§16.4). The page draws the first rows from these and app.js the rest, so the
    two are one markup."""
    returns = dict(zip(("r1", "r3", "r5"), row["returns"], strict=True))
    labels = record["labels"]
    return {
        "id": row["scheme_id"], "name": row["name"], "house": row["house"],
        "family": row["family"], "cat": row["category_key"],
        "cat_name": row["category_short"],
        "c": {
            "size": [row["size_value"], row["size_label"]],
            "ter": [row["ter_value"], row["ter_label"]],
            **{key: [r["value"], r["label"], r["tone"] or "", r["symbol"] or ""]
               for key, r in returns.items()},
            "rank": [row["rank_value"], row["rank_label"], row["rank_quarter"]],
            **{key: [record[key] or "", labels[key] or DASH]
               for key in ("vol3", "fall3", "sharpe3")},
        },
    }


def largest_first(explore: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Explore funds' first view (E-02): the largest fund first, a fund with no
    size last; compared as Decimals here, never as text in SQL."""
    return sorted(explore, key=lambda r: (r["c"]["size"][0] == "",
                                          -Decimal(r["c"]["size"][0] or 0)))


def fund_record(
    row: dict[str, Any], detail: ViewEnvelope | None, prices_from: str | None,
    benchmark: str | None = None, tracker: str | None = None,
) -> dict[str, Any]:
    """One fund for the portfolio page's picker and alternatives (V1-82) and the
    compare page (V1-85). `tracker` is the index fund standing in for its
    benchmark (`PublicMarket.proxy`): Your portfolio's reference (UI/UX critique P-01).

    The same figures the `/funds/` table shows, as text: the pages compare and
    sort on them, and never re-derive them. `labels` are those figures as a
    reader sees them, formatted here (§16.4), so the compare page formats none.
    """
    windows: dict[str, dict[str, Any]] = {}
    if detail is not None and detail.state.value == "ok":
        windows = {
            r["window_key"]: r for r in detail.payload.get("rows", [])
            if r["window_key"] in RETURN_WINDOWS and r.get("obs_days") is not None
            and spans(int(r["obs_days"]), r["window_key"])
        }

    def text(value: Any) -> str | None:
        return None if value in (None, "") else str(value)

    three = windows.get("3y", {})

    def shown(value: str | None, fmt: Any) -> str | None:
        return None if value is None else str(fmt(Decimal(value)))

    record = {
        "id": row["scheme_id"],
        "amfi": row["amfi_code"],
        "name": row["name"],
        "category": row["category_key"],
        "category_name": row["category_short"],
        "prices_from": prices_from,
        "ter": text(row["ter_value"]),
        "size": text(row["size_value"]),
        "r1": text(windows.get("1y", {}).get("return_ann")),
        "r3": text(three.get("return_ann")),
        "r5": text(windows.get("5y", {}).get("return_ann")),
        "vol3": text(three.get("volatility_ann")),
        "fall3": text(three.get("max_dd")),
        "house": row["house"] or None,
        "benchmark": benchmark,
        "tracker": tracker,
        "sharpe3": text(three.get("sharpe")),
        "rank3": None if row["rank_label"] in (None, "", DASH) else row["rank_label"],
    }
    record["labels"] = {
        "size": None if row["size_label"] in (None, "", DASH) else row["size_label"],
        "ter": shown(record["ter"], lambda v: format_pct(v, precision=2)),
        "r1": shown(record["r1"], lambda v: format_return(v, True)),
        "r3": shown(record["r3"], lambda v: format_return(v, True)),
        "r5": shown(record["r5"], lambda v: format_return(v, True)),
        "vol3": shown(record["vol3"], format_fraction),
        "fall3": shown(record["fall3"], format_fraction),
        "sharpe3": shown(record["sharpe3"], lambda v: f"{v:.2f}"),
        "prices_from": None if prices_from is None
        else format_date(date.fromisoformat(prices_from)),
    }
    # A heading of unlike funds (categories.yaml `ranked: false`): no ranks on
    # its pages, and no suggestions beside it on the portfolio page.
    if not category_of(row.get("category")).ranked:
        record["mixed"] = True
    return record


def regular_record(
    direct: dict[str, Any], twin: Fund, prices_from: str, ter: Any = None
) -> dict[str, Any]:
    """A Regular plan for Your portfolio's picker (external audit, 2026-10-04):
    its own prices and cost; its Direct plan's category, holdings and page,
    since the two share one portfolio. `plan` keeps it out of Explore, Compare
    and the suggestions, which compare Direct plans only (MODULE_2 §11.2)."""
    record: dict[str, Any] = {
        "id": twin.scheme_id, "amfi": twin.amfi_code,
        "name": f"{direct['name']} (Regular)",
        "plan": "regular", "direct": direct["id"], "category": direct["category"],
        "category_name": direct["category_name"], "house": direct.get("house"),
        "tracker": direct.get("tracker"), "prices_from": prices_from,
        "ter": None if ter is None else str(ter.total),
    }
    if direct.get("mixed"):
        record["mixed"] = True
    return record


def share_card(out: Path, record: dict[str, Any], detail: str, market: Any, scheme: str,
               today: date) -> None:
    """The fund's preview for a shared link (UI/UX critique G-11): its three-year
    return (else its one-year), its rank, and three years of its price."""
    figure = None
    for key, words in (("r3", "a year over 3 years"), ("r1", "over 1 year")):
        if record.get(key):
            figure = f"{format_return(Decimal(record[key]), False)} {words}"
            break
    rank = (f"{record['rank3']} in its category over 3 years"
            if record.get("rank3") else None)
    navs = market.nav_series(SchemeId(scheme), window_start(today, "3y"), today,
                             adjusted=True)
    step = max(1, len(navs) // 160)
    fund_card(out, record["name"], detail, figure, rank, [p.nav for p in navs[::step]])


def manifest(out: Path, base: str) -> None:
    """The web manifest and its icons: a name and a mark for a home screen."""
    for name, size in ICONS:
        icon_png(out / "static" / name, size)
    (out / "static" / "site.webmanifest").write_text(json.dumps({
        "name": "Look-through: Did my SIP work?", "short_name": "Look-through",
        "start_url": f"{base}/", "display": "browser",
        "theme_color": "#134585", "background_color": "#f5f7fb",
        "icons": [{"src": name, "sizes": f"{size}x{size}", "type": "image/png"}
                  for name, size in ICONS if name.startswith("icon-")],
    }, indent=2) + "\n", encoding="utf-8")


def lookthrough_file(lookthrough: Any, scheme: str, today: date) -> dict[str, Any] | None:
    """What one fund holds, for the portfolio page's look-through (V1-82): the
    figures its own `fund_portfolio` panel draws, by issuer id so the page can
    add a company up across funds. None when no disclosure is loaded."""
    found = lookthrough.fund_composition(SchemeId(scheme), today)
    if found is None:
        return None
    fund, disclosed, tier = found
    return {
        "as_of": disclosed.isoformat(),
        "aggregator": tier == "aggregator",
        "holdings": [
            [str(h.issuer_id), lookthrough.issuer_name(h.issuer_id),
             h.instrument_class, str(h.weight)]
            for h in fund.holdings
        ],
        "mix": [[k, str(v)] for k, v in fund.by_class],
        "sectors": [[k, str(v)] for k, v in fund.by_sector],
        "sizes": [[t.dimension_value, str(t.exposure_pct)] for t in fund.size],
    }


def category_leaders(
    rows: list[dict[str, Any]], keys: tuple[str, ...] = LEADER_CATEGORIES,
    top: int = LEADERS_PER_CARD,
) -> list[dict[str, Any]]:
    """Each category's funds with the highest 3-year return, for the front page.

    Sorted here, on the Decimal behind each figure, never in SQL (CLAUDE.md
    invariant 1). A fund without three years of prices is not in a card, and the
    card says how many funds the category has in all.
    """
    three = RETURN_WINDOWS.index("3y")
    cards = []
    for key in keys:
        members = [r for r in rows if r.get("category_key") == key]
        ranked = sorted(
            (r for r in members if r["returns"][three]["value"]),
            key=lambda r: Decimal(r["returns"][three]["value"]),
            reverse=True,
        )[:top]
        if ranked:
            cards.append({"key": key, "name": members[0]["category_short"],
                          "count": len(members), "funds": ranked})
    return cards


def sip_kinds(funds: list[dict[str, str]]) -> list[dict[str, Any]]:
    """/sip/'s list of kinds (SPEC_SIP_WHAT_IF §4.2): each family in the site's
    order, its ranked categories by name, each with SEBI's one line on it and its
    count of published (Direct) funds. A heading of unlike funds is never a kind:
    a range across it would set unlike funds side by side."""
    counts: dict[str, int] = defaultdict(int)
    found = {}
    for fund in funds:
        category = category_of(fund["category"])
        if category.ranked:
            counts[category.key] += 1
            found[category.key] = category
    families = []
    for key, name, _ in FAMILIES:
        kinds = sorted((c for c in found.values() if c.family == key),
                       key=lambda c: c.name.lower())
        if kinds:
            families.append({"name": name, "kinds": [
                {"key": c.key, "name": c.name, "about": c.about or "",
                 "count": counts[c.key]}
                for c in kinds]})
    return families


def sip_opening(funds: list[dict[str, str]],
                kinds: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    """The kind /sip/ opens on (large cap, else the first it offers) and the AMFI
    codes of its funds, whose NAV files the page fetches while it loads (§4.10)."""
    keys = [k["key"] for family in kinds for k in family["kinds"]]
    if not keys:
        return None, []
    key = "equity/large_cap" if "equity/large_cap" in keys else keys[0]
    return key, sorted(f["amfi_code"] for f in funds
                       if f["amfi_code"] and category_of(f["category"]).key == key)


def fund_map(funds: list[dict[str, str]]) -> list[dict[str, Any]]:
    """The front page's map (V1-81): each family, in SEBI's order, then its
    categories with what SEBI's rules say they hold and how many funds they have
    here, largest first. Headings that mix funds doing different jobs (never
    ranked: AMFI's older catch-alls among them) come last, in `mixed`, which the
    page folds away (UI/UX critique H-03)."""
    counts: dict[str, int] = defaultdict(int)
    found = {}
    for fund in funds:
        category = category_of(fund["category"])
        counts[category.key] += 1
        found[category.key] = category
    families = []
    for key, name, hint in FAMILIES:
        members = sorted((c for c in found.values() if c.family == key),
                         key=lambda c: (-counts[c.key], c.name))
        if members:
            def entry(c: Any) -> dict[str, Any]:
                return {"key": c.key, "name": c.name, "about": c.about,
                        "count": counts[c.key]}
            families.append({
                "key": key, "name": name, "hint": hint,
                "count": sum(counts[c.key] for c in members),
                "categories": [entry(c) for c in members if c.ranked],
                "mixed": [entry(c) for c in members if not c.ranked],
            })
    return families


def _build(
    deps: Deps, view_id: str, scope: Scope, params: dict[str, Any]
) -> ViewEnvelope:
    """`app.build_view`'s boundary, without the server: a builder that raises
    degrades its own panel, never the page."""
    try:
        return VIEW_REGISTRY[view_id](deps).build(scope, params)
    except Exception as exc:
        return error_envelope(view_id, VIEW_DEFS[view_id].question, scope, exc)


def _adapter(folder: Path, url: str, scope: Scope) -> Any:
    """What the public copy changes in each panel before it is drawn: no period
    tabs (no server to fetch them from), the export link pointing at a CSV
    written beside the page, and what it withholds."""

    def adapt(env: ViewEnvelope) -> ViewEnvelope:
        if env.state.value == "error":
            # An exception's text is for the person running the build, not for
            # the public page.
            print(f"  ! {scope.scope_id} {env.view_id}: {env.state_reason}")
            env = empty_envelope(env.view_id, env.question, scope, NOT_BUILT)
        elif env.view_id == "fund_portfolio" and env.state.value == "empty":
            env = empty_envelope(env.view_id, env.question, scope, NO_PORTFOLIO)
        name = f"{env.view_id}.csv"
        env = replace(
            env,
            payload={k: v for k, v in env.payload.items() if k != "tabs"},
            export_url=f"{url}{name}",
        )
        (folder / name).write_text(to_csv(env), encoding=ENCODING, newline="")
        return env

    return adapt


def build_site(
    warehouse: Any, out: Path, base: str, today: date | None = None,
    declared: dict[str, str] | None = None, site_url: str = SITE_URL,
) -> dict[str, int]:
    """Render every public fund page, the index and the search list into `out`.
    `declared` is each fund's benchmark by ISIN, from the Groww crawl's map."""
    today = today or date.today()
    if out.exists():
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise RuntimeError(
                f"{out} holds files this job did not write; refusing to replace it."
            )
        shutil.rmtree(out)
    out.mkdir(parents=True)

    deps = public_deps(warehouse, declared)
    market = deps.market
    assert isinstance(market, PublicMarket)
    engine = templates(root=base, static=True)
    engine.env.globals["site_url"] = site_url   # for a shared link's preview (G-11)
    shell = {"catalogue": [], "health": {}, "qs": "", "active": "", "built": today}
    funds = funds_to_publish(warehouse)
    firsts = {
        str(sid): str(first)[:10] for sid, first in warehouse.execute(
            "SELECT scheme_id, min(nav_date) FROM nav_daily GROUP BY scheme_id")
    }
    records: list[dict[str, Any]] = []
    (out / "data" / "lookthrough").mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []  # the landing page's example (V1-89)
    houses: set[str] = set()
    with_holdings = 0
    disclosed: Counter[date] = Counter()   # the dates portfolios were disclosed for
    prices_to: date | None = None
    for n, fund in enumerate(funds, start=1):
        sid = fund["scheme_id"]
        folder = out / "fund" / sid
        folder.mkdir(parents=True)
        scope = Scope(PUBLIC_USER, today, "scheme", sid)
        context = fund_context(
            lambda v, s, p: _build(deps, v, s, p), scope, "max", base,
            _adapter(folder, f"{base}/fund/{sid}/", scope),
        )
        # /sip/ opens on this fund's kind with the fund added (SPEC_SIP_WHAT_IF §4.8):
        # only a ranked kind is one /sip/ offers.
        kind = category_of(fund["category"])
        (folder / "index.html").write_text(
            engine.get_template("fund.html").render(
                {**shell, **context, "sip_category": kind.key if kind.ranked else None}),
            encoding="utf-8",
        )
        # The front page's table and counts, from what this page just drew.
        facts = deps.market.scheme_facts(SchemeId(sid))
        panels = {p["env"].view_id: p["env"] for p in context["panels"]}
        rows.append(explorer_row(fund, facts, context["detail"]["env"],
                                 panels.get("fund_peers")))
        records.append(fund_record(rows[-1], context["detail"]["env"], firsts.get(sid),
                                   facts.benchmark_name if facts else None,
                                   market.proxy(sid)))
        share_card(folder / "share.png", records[-1], rows[-1]["detail"], deps.market,
                   sid, today)
        held = lookthrough_file(deps.lookthrough, sid, today)
        if rows[-1]["family"] == "equity":
            peers = panels.get("fund_peers")
            ok = peers is not None and peers.state.value == "ok"
            ranged = range_bars(peers) if ok and peers is not None else []
            candidates.append(landing_candidate(rows[-1], ranged, held))
        if held is not None:
            (out / "data" / "lookthrough" / f"{sid}.json").write_text(
                json.dumps(held, ensure_ascii=False), encoding="utf-8")
        if facts is not None and facts.amc_name:
            houses.add(facts.amc_name)
        for panel in context["panels"]:
            env = panel["env"]
            if env.state.value != "ok":
                continue
            if env.view_id == "fund_portfolio":
                with_holdings += 1
                disclosed[env.data_as_of] += 1
            if env.view_id == "fund_header":
                prices_to = max(prices_to or env.data_as_of, env.data_as_of)
        if n % 50 == 0:
            print(f"  {n:,} of {len(funds):,} fund pages")

    by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    for fund in funds:
        by_category[category_of(fund["category"]).name].append(fund)
    counted: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        counted[row["family"]] += 1
    families = [
        {"key": key, "name": name, "hint": hint, "count": counted[key]}
        for key, name, hint in FAMILIES
        if counted[key]
    ]
    stats = {
        "houses": len(houses),
        "holdings": with_holdings,
        # The date most portfolios were disclosed for (UI/UX critique H-07); ties
        # go to the later.
        "holdings_as_of": max(disclosed, key=lambda d: (disclosed[d], d), default=None),
        "prices_to": prices_to,
        "categories": len({r["category_key"] for r in rows}),
    }
    example = landing_example(candidates)
    (out / "index.html").write_text(
        engine.get_template("home.html").render({
            **shell, "count": len(funds), "stats": stats, "fund_map": fund_map(funds),
            "example": example,
            "pair": landing_pair(example["scheme_id"], candidates) if example else None,
        }),
        encoding="utf-8",
    )
    (out / "funds").mkdir(exist_ok=True)
    explore = largest_first([explore_row(r, rec) for r, rec in zip(rows, records,
                                                                   strict=True)])
    (out / "funds" / "rows.json").write_text(
        json.dumps(explore, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "funds" / "index.html").write_text(
        engine.get_template("explorer.html").render({
            **shell,
            "active": "funds",
            "categories": sorted(by_category.items()),
            "category_options": sorted(
                {(r["category_key"], r["category_short"]) for r in rows},
                key=lambda kv: kv[1].lower(),
            ),
            "count": len(funds),
            "explore": explore[:EXPLORE_FIRST],
            "columns": EXPLORE_COLUMNS,
            "hidden": EXPLORE_HIDDEN,
            "first": EXPLORE_FIRST,
            "families": families,
            "stats": stats,
            "leaders": category_leaders(rows),
        }),
        encoding="utf-8",
    )
    (out / "404.html").write_text(
        engine.get_template("notfound.html").render(shell), encoding="utf-8"
    )
    (out / "portfolio").mkdir()
    (out / "portfolio" / "index.html").write_text(
        engine.get_template("portfolio.html").render({**shell, "active": "portfolio"}),
        encoding="utf-8",
    )
    (out / "compare").mkdir()
    (out / "compare" / "index.html").write_text(
        engine.get_template("compare.html").render({**shell, "active": "compare"}),
        encoding="utf-8",
    )
    (out / "sip").mkdir()
    kinds = sip_kinds(funds)
    opens_on, opening_navs = sip_opening(funds, kinds)
    (out / "sip" / "index.html").write_text(
        engine.get_template("sip.html").render(
            {**shell, "active": "sip", "sip_kinds": kinds, "sip_opens_on": opens_on,
             "sip_opening_navs": opening_navs}),
        encoding="utf-8",
    )
    learn = load_learn()
    learn_page = {**shell, "active": "learn"}
    (out / "learn" / "glossary").mkdir(parents=True)
    (out / "learn" / "index.html").write_text(
        engine.get_template("learn.html").render(learn_page), encoding="utf-8")
    (out / "learn" / "glossary" / "index.html").write_text(
        engine.get_template("learn_glossary.html").render(learn_page), encoding="utf-8")
    for guide in learn.guides:
        (out / "learn" / guide.slug).mkdir()
        (out / "learn" / guide.slug / "index.html").write_text(
            engine.get_template("learn_guide.html").render(
                {**learn_page, "guide": guide}),
            encoding="utf-8",
        )
    for line in stale(learn, today):
        print(f"  ! learn source not checked for a year: {line}")
    (out / "search.json").write_text(
        json.dumps(
            [{"name": f["name"], "detail": f["detail"],
              "url": f"{base}/fund/{f['scheme_id']}/"} for f in funds]
            + [{"name": t.title, "detail": "Glossary",
                "url": f"{base}/learn/glossary/#{t.key}"} for t in learn.terms.values()]
            + [{"name": g.title, "detail": "Guide",
                "url": f"{base}/learn/{g.slug}/"} for g in learn.guides]
            + [{"name": "What would a SIP have become?", "detail": "Page",
                "url": f"{base}/sip/"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    live = live_funds(warehouse)
    twins = regular_twins(warehouse, live)
    published = {r["id"]: r for r in records}
    records.extend(
        regular_record(published[direct], twin, firsts[twin.scheme_id],
                       deps.market.ters([twin.scheme_id], today).get(twin.scheme_id))
        for direct, twin in twins.items()
        if direct in published and twin.scheme_id in firsts
    )
    (out / "funds.json").write_text(
        json.dumps(records, ensure_ascii=False), encoding="utf-8")
    nav_files = save_navs(warehouse, out, [*live, *twins.values()])
    for name in STATIC_FILES:
        target = out / "static" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(STATIC / name, target)
    site_card(out / "static" / "share.png", len(funds))
    manifest(out, base)
    (out / MARKER).write_text("", encoding="utf-8")
    (out / "vercel.json").write_text(json.dumps(VERCEL_CONFIG, indent=2) + "\n",
                                     encoding="utf-8")

    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    check_budget(size)
    return {"funds": len(funds), "bytes": size, "nav_files": nav_files}


def check_budget(size: int, budget: int = SITE_BUDGET_BYTES) -> None:
    if size > budget:
        raise SiteTooLarge(
            f"the site is {size / 1e6:,.0f} MB and the build stops at"
            f" {budget / 1e6:,.0f} MB, its own ceiling for a nightly push and"
            f" deploy (V1-92). A lighter page profile "
            f"is the fix (DECISIONS V1-72)."
        )


class GitFailed(RuntimeError):
    """A git command failed; its own message is kept, since a bare exit status
    left a failed publish unexplained."""


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        # The arguments are not echoed: in CI the push URL carries a token.
        raise GitFailed(
            f"git {args[0]} exited {done.returncode}: {done.stderr.strip()[-600:]}"
        )
    return done.stdout.strip()


def push(out: Path) -> None:
    """Publish `out` as the only commit on `gh-pages`, replacing the last.

    An orphan commit force-pushed, so the branch never accumulates history and
    the repository does not grow with every rebuild. From this machine, the
    user's own git identity and credentials. In GitHub Actions the workflow hands
    in `SITE_PUSH_URL` with its short-lived token, because this commit is made in
    a new repository that does not inherit the checkout's credentials.

    Pushed twice at most: one 250 MB push failed once for no reason git gave.
    """
    remote = os.environ.get("SITE_PUSH_URL") or _git("remote", "get-url", "origin")
    author = [f"user.name={_git('config', 'user.name')}",
              f"user.email={_git('config', 'user.email')}"]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(out, work, dirs_exist_ok=True)
        _git("init", "-q", "-b", "gh-pages", cwd=work)
        # No automatic packing (V1-90). A commit this size is far past git's
        # loose-object threshold, so it started `gc --auto` detached, still
        # writing into `.git` as the directory was removed: the push had gone
        # through and the build failed on "Directory not empty".
        _git("config", "gc.auto", "0", cwd=work)
        _git("config", "maintenance.auto", "false", cwd=work)
        _git("add", "-A", cwd=work)
        _git(*[a for pair in author for a in ("-c", pair)], "commit", "-q", "-m",
             f"Public fund explorer, built {date.today().isoformat()}", cwd=work)
        try:
            _git("push", "-q", "--force", remote, "gh-pages", cwd=work)
        except GitFailed as first:
            print(f"  ! push failed, trying once more: {first}")
            _git("push", "-q", "--force", remote, "gh-pages", cwd=work)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "site")
    parser.add_argument("--base", default="",
                        help="URL prefix; default none: Vercel serves the site from"
                        " its address's root (V1-92)")
    parser.add_argument("--push", action="store_true",
                        help="publish to the gh-pages branch after building")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    warehouse = connect(str(warehouse_path()))
    # The public copy reads; it never writes. SQLite enforces it from here on.
    warehouse.execute("PRAGMA query_only = ON")
    print(f"building the public copy into {args.out} (links under {base or '/'})")
    summary = build_site(warehouse, args.out, base,
                         declared=declared_benchmarks(REPO_ROOT / "data" / "groww.csv"))
    print(f"{summary['funds']:,} fund pages, {summary['bytes'] / 1e6:,.1f} MB")
    if args.push:
        push(args.out)
        print("published to gh-pages, which Vercel deploys (README section 6).")
    else:
        print("not published: add --push to publish it.")
    sys.exit(0)


if __name__ == "__main__":
    main()
