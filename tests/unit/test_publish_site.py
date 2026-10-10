"""The public fund explorer: `jobs/publish_site.py`. DECISIONS V1-72.

A public website built from the same warehouse as the private app, so every
test here is about what must NOT reach it -- index levels, the portfolio --
what must reach it only marked (an aggregator's holdings), and about the links
working both from the root of an address (Vercel, V1-92) and from a folder
(`--base`).
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import jobs.publish_site as publish
import pytest
from PIL import Image
from src.common.contracts.market import NavPoint
from src.common.decimals import connect
from src.common.types import IndexId, SchemeId
from src.m0_data.categories import category_of
from src.m6_views.api.pages import templates
from src.m6_views.builders.fund.common import INDEX_WITHHELD
from src.m6_views.format import DASH, format_date

from tests.conftest import migrated

TODAY = date(2026, 9, 24)
BASE = "/Repo"
DIRECT, REGULAR, AGGREGATED, SHORT = (
    "INF000T01011", "INF000T01029", "INF000T01037", "INF000T01045",
)


def _prices(c: sqlite3.Connection, scheme: str, days: int) -> None:
    c.executemany(
        "INSERT INTO nav_daily (scheme_id, nav_date, nav, nav_adj) VALUES (?,?,?,?)",
        [
            (scheme, TODAY - timedelta(days=days - t), Decimal(100 + t), Decimal(100 + t))
            for t in range(days)
        ],
    )


def _disclose(c: sqlite3.Connection, scheme: str, tier: str) -> None:
    c.execute(
        "INSERT INTO holding_disclosure (scheme_id, as_of_date, revision,"
        " source_file_id, row_count, unresolved_mv_pct, total_mv,"
        " validation_status, ingested_at, is_current, source_tier)"
        " VALUES (?, '2026-08-31', 1, 'f1', 1, 0, 100, 'ok', '2026-09-01', 1, ?)",
        (scheme, tier),
    )
    c.execute(
        "INSERT INTO holding (scheme_id, as_of_date, revision, row_number,"
        " issuer_id, instrument_raw_name, market_value, pct_normalised,"
        " instrument_class, resolution_method, source_file_id, ingested_at,"
        " is_current) VALUES (?, '2026-08-31', 1, 1, 'ACME', 'Acme', 1, 100,"
        " 'equity', 'isin', 'f1', '2026-09-01', 1)",
        (scheme,),
    )


@pytest.fixture
def warehouse(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "w.db"
    migrated(db)
    c: sqlite3.Connection = connect(str(db))
    c.execute(
        "INSERT INTO benchmark_index (index_id, index_name, is_total_return)"
        " VALUES ('NSE:TEST_TRI', 'Test 50', 1)"
    )
    for sid, plan, family, code in (
        (DIRECT, "direct", "fund one", "900001"),
        (REGULAR, "regular", "fund one", "900002"),  # one fund, two share classes
        (AGGREGATED, "direct", "fund two", "900003"),
        (SHORT, "direct", "fund three", "900004"),
    ):
        c.execute(
            "INSERT INTO scheme (scheme_id, amfi_code, scheme_name, fund_name, plan,"
            " option, amc_id, scheme_family, sebi_category, benchmark_id, status,"
            " last_seen) VALUES (?,?,?,?,?,'growth','amc1',?,"
            "'Equity Scheme - Flexi Cap Fund','NSE:TEST_TRI','active',?)",
            (sid, code, family.title(), family.title(), plan, family, TODAY),
        )
    for sid in (DIRECT, REGULAR, AGGREGATED):
        _prices(c, sid, 300)
    _prices(c, SHORT, 20)  # too little history for a page
    c.executemany(
        "INSERT INTO index_level (index_id, level_date, level) VALUES (?,?,?)",
        [("NSE:TEST_TRI", TODAY - timedelta(days=t), Decimal(5000 + t))
         for t in range(300)],
    )
    c.execute(
        "INSERT INTO raw_file (file_id, source_id, fetched_at, storage_path, byte_size)"
        " VALUES ('f1', 'S5', '2026-09-01', '/x', 0)"
    )
    c.execute("INSERT INTO issuer (issuer_id, canonical_name) VALUES ('ACME', 'Acme')")
    _disclose(c, DIRECT, "amc_direct")
    _disclose(c, AGGREGATED, "aggregator")
    c.commit()
    return c


@pytest.fixture
def site(
    warehouse: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """The site, built with the personal ledger made impossible to open."""
    import src.m1_ledger.db as ledger_db

    opened: list[str] = []
    real = ledger_db.connect_ledger

    def spy(path: str, **kw: object) -> sqlite3.Connection:
        opened.append(path)
        return real(path, **kw)  # type: ignore[arg-type]

    def forbidden() -> Path:
        raise AssertionError("the public build asked for the personal ledger")

    monkeypatch.setattr(publish, "connect_ledger", spy)
    monkeypatch.setattr(ledger_db, "ledger_path", forbidden)
    out = tmp_path / "site"
    summary = publish.build_site(warehouse, out, BASE, TODAY)
    assert summary["funds"] == 2
    assert set(opened) == {":memory:"}
    return out


def _page(site: Path, scheme: str) -> str:
    return (site / "fund" / scheme / "index.html").read_text(encoding="utf-8")


def test_one_page_per_fund_with_a_year_of_prices(site: Path) -> None:
    pages = {p.parent.name for p in (site / "fund").glob("*/index.html")}
    # The Direct plan stands for its fund; the Regular one and a fund with
    # twenty days of prices get no page.
    assert pages == {DIRECT, AGGREGATED}
    listed = json.loads((site / "search.json").read_text(encoding="utf-8"))
    # The list also carries the learn pages (V1-87); this is about the funds.
    assert {h["url"] for h in listed if "/fund/" in h["url"]} == {
        f"{BASE}/fund/{DIRECT}/", f"{BASE}/fund/{AGGREGATED}/"
    }


def test_every_link_works_from_the_project_subdirectory(site: Path) -> None:
    for html in site.rglob("*.html"):
        text = html.read_text(encoding="utf-8")
        for link in re.findall(r'(?<![\w-])(?:href|src|action)="([^"]*)"', text):
            # A same-page anchor (the fund page's section navigator) works anywhere.
            assert link.startswith((BASE, "https://", "#")), f"{html.name}: {link}"
        assert f'data-index="{BASE}/search.json"' in text  # the search box's list
        assert "/api/" not in text and "/view/" not in text and "/fragment/" not in text


def test_a_panels_figures_are_linked_not_inlined(site: Path) -> None:
    """Phase 2, lean pages: §10.4's table equivalent is the CSV beside the page,
    so a public page links it; inline, the tables were ~3/4 of every page."""
    page = (site / "fund" / DIRECT / "index.html").read_text(encoding="utf-8")
    assert '<details class="chart-table">' not in page
    assert f'href="{BASE}/fund/{DIRECT}/fund_growth.csv">The same figures' in page
    assert (site / "fund" / DIRECT / "fund_growth.csv").exists()


def test_no_index_level_reaches_the_public_copy(site: Path) -> None:
    page = _page(site, DIRECT)
    block = re.search(
        r'<script type="application/json" class="echart-data">(.*?)</script>',
        page, re.S,
    )
    assert block is not None
    charts = json.loads(block.group(1))["charts"]
    assert all(s["role"] == "fund" for s in charts[0]["series"])
    assert INDEX_WITHHELD in page
    growth = (site / "fund" / DIRECT / "fund_growth.csv").read_text(
        encoding="utf-8-sig"
    )
    # The benchmark column is there and empty (read by name: the NAV column
    # follows it since the price chart joined this panel).
    table = [r for r in csv.reader(growth.splitlines()) if r and not r[0].startswith("#")]
    at = table[0].index("benchmark_value_inr")
    assert all(row[at] == "" for row in table[-3:])


def test_the_site_says_where_its_portfolios_come_from(site: Path) -> None:
    """External audit, 2026-10-04: the banner and the hero said "fund houses'
    disclosures" and the footer "an archived source file", while most
    portfolios are read from an aggregator's pages and no page is kept."""
    home = (site / "index.html").read_text(encoding="utf-8")
    for text in (home, _page(site, DIRECT)):
        assert "fund houses' disclosures" not in text
        assert "fund houses'\n  disclosures" not in text
        assert "archived source file" not in text
        assert "an aggregator" in text
    assert "own disclosures" not in home


def test_a_fund_under_a_mixed_heading_is_marked_for_the_pages() -> None:
    """External audit, 2026-10-04: the portfolio page's alternatives and the
    fund pages' ranks follow one rule, categories.yaml's `ranked: false`."""
    row = {"scheme_id": "X", "amfi_code": "1", "name": "X",
           "category": "Other Scheme - Index Funds",
           "category_key": "index/undivided", "category_short": "Index funds",
           "ter_value": "", "size_value": "", "size_label": DASH, "house": "",
           "rank_label": DASH}
    assert publish.fund_record(row, None, None)["mixed"] is True
    flexi = {**row, "category": "Equity Scheme - Flexi Cap Fund",
             "category_key": "equity/flexi_cap"}
    assert "mixed" not in publish.fund_record(flexi, None, None)


def test_without_a_benchmark_the_page_does_not_promise_one(site: Path) -> None:
    """V1-94: neither question asks about a benchmark the public copy cannot
    show (test_m6_fund_page has the rows left out)."""
    page = _page(site, DIRECT)
    assert "How has it done for the risk taken?" in page
    assert "How much has it returned?" in page
    assert "against its benchmark" not in page


def test_a_shared_link_shows_what_it_leads_to(site: Path) -> None:
    """UI/UX critique G-11 (2026-10-04): no favicon, manifest, theme colour,
    description or preview, so a link shared on WhatsApp looked broken. A fund
    page's preview is its own picture; every other page's is the site's."""
    page = _page(site, DIRECT)
    image = f'content="{publish.SITE_URL}{BASE}/fund/{DIRECT}/share.png"'
    assert f'<meta property="og:image" {image}>' in page
    assert '<meta name="twitter:card" content="summary_large_image">' in page
    assert re.search(r'<meta name="description" content="Fund One[^"]*">', page)
    with Image.open(site / "fund" / DIRECT / "share.png") as img:
        assert img.size == (1200, 630)
    home = (site / "index.html").read_text(encoding="utf-8")
    assert f'content="{publish.SITE_URL}{BASE}/static/share.png"' in home
    assert (site / "static" / "share.png").is_file()
    for head in (page, home):
        icon = f'<link rel="icon" href="{BASE}/static/favicon.svg" type="image/svg+xml">'
        assert icon in head
        assert f'<link rel="manifest" href="{BASE}/static/site.webmanifest">' in head
        assert '<meta name="theme-color"' in head
    manifest = json.loads(
        (site / "static" / "site.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"]
    assert {i["sizes"] for i in manifest["icons"]} >= {"192x192", "512x512"}
    for icon in manifest["icons"]:
        assert (site / "static" / icon["src"]).is_file(), icon["src"]


def test_the_footer_is_a_way_around_and_says_what_this_is(site: Path) -> None:
    """UI/UX critique G-10 (2026-10-04): one tiny line, no links, no "not advice"."""
    page = _page(site, DIRECT)
    foot = page[page.index('<footer class="colophon">'):]
    foot = foot[:foot.index("</footer>")]   # each section has a footer of its own
    for heading in ("Product", "Data", "About"):
        assert f">{heading}</h2>" in foot, heading
    for href in (f"{BASE}/funds/", f"{BASE}/compare/", f"{BASE}/portfolio/",
                 f"{BASE}/learn/", f"{BASE}/#about", f"{BASE}/learn/reading-a-fund-page/",
                 f"{BASE}/#privacy",
                 "/issues"):
        assert href in foot, href
    assert "Descriptive, not advice" in foot
    # Once: the line under the columns repeated the code's link, at a larger size.
    repo = "https://github.com/harshilsaini26/Mutual-Fund-Portfolio-Analyser.io\""
    assert foot.count(repo) == 1


def test_every_table_on_the_public_pages_is_a_named_region(site: Path) -> None:
    """G-17: the fund pages and Explore funds, whose table scrolls on a phone."""
    from tests.unit.test_m6_fund_page import assert_tables_are_named_regions

    assert_tables_are_named_regions(_page(site, DIRECT))
    explore = (site / "funds" / "index.html").read_text(encoding="utf-8")
    assert_tables_are_named_regions(explore)


def test_the_recently_viewed_list_can_be_cleared(site: Path) -> None:
    """G-21: Settings clears the funds viewed lately, as the privacy text says."""
    page = _page(site, DIRECT)
    assert re.search(
        r"<button[^>]*data-recent-clear[^>]*>Clear recently viewed</button>", page)
    script = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
              / "app.js").read_text(encoding="utf-8")
    clear = script[script.index("data-recent-clear"):][:600]
    assert "removeItem(RECENT)" in clear


def test_the_header_says_what_its_controls_do(site: Path) -> None:
    """UI/UX critique G-06-G-08 (2026-10-04): the settings button looked like a
    light/dark switch (a sun); the search placeholder was cut short on a phone;
    the home page had two search boxes on its first screen."""
    page = _page(site, DIRECT)
    button = page[page.index("data-settings-open"):]
    button = button[:button.index("</button>")]
    assert ">Display<" in button and 'aria-label="Display settings"' in button
    assert '<circle cx="12" cy="12" r="3"/>' not in button      # the sun
    assert 'id="q"' in page and 'placeholder="Search funds"' in page
    home = (site / "index.html").read_text(encoding="utf-8")
    assert 'id="q"' not in home and 'id="q-hero"' in home


def test_categories_are_named_as_the_site_names_them(site: Path) -> None:
    """UI/UX critique G-05 (2026-10-04): AMFI's raw headings ("Solution Oriented
    Schemes ** - Retirement Fund") leaked into search and the grouped list."""
    found = json.loads((site / "search.json").read_text(encoding="utf-8"))
    fund = next(f for f in found if f["url"].endswith(f"/fund/{DIRECT}/"))
    assert fund["detail"] == "Flexi cap · Direct · Growth"
    listing = (site / "funds" / "index.html").read_text(encoding="utf-8")
    assert "Equity Scheme - Flexi Cap Fund" not in listing


def test_compare_lines_each_funds_column_up_on_one_edge() -> None:
    """Design review, 2026-10-04: a fund's column held left-aligned text and
    rank under right-aligned figures. Every value and the heading align right."""
    static = Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
    script = (static / "compare.js").read_text(encoding="utf-8")
    # Every table there, the facts too, is Kit.table with each fund's column numeric.
    body = script[script.index("function table(caption, head, rows)"):]
    body = body[:body.index("\n  }\n")]
    assert "numeric: head.map(function (h, i) { return i > 0; })" in body
    assert 'fill(box, table("Key facts and returns"' in script
    css = (static / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\.cmp__table thead th \+ th\s*\{[^}]*text-align:\s*right", css)


def test_the_confidence_tag_says_what_it_means(site: Path) -> None:
    """External audit, 2026-10-04: "Confidence: medium" without saying what
    drives it. Each tag links to the guide's paragraph on it (V1-94)."""
    anchor = "dates-sources-confidence-and-gaps"
    page = _page(site, DIRECT)
    assert f'href="{BASE}/learn/reading-a-fund-page/#{anchor}" class="badge' in page
    guide = (site / "learn" / "reading-a-fund-page" / "index.html").read_text(
        encoding="utf-8")
    assert f'id="{anchor}"' in guide
    assert "High means" in guide and "Low means" in guide


def test_your_portfolio_can_hold_a_regular_plan(site: Path) -> None:
    """External audit, 2026-10-04: most money sits in Regular plans, and entering
    one as its Direct twin read about 1% a year too high. funds.json lists each
    published fund's Regular plan for Your portfolio, marked so Explore and
    Compare leave it out, with its own prices; holdings and the fund page are
    its Direct plan's (one portfolio, two share classes)."""
    funds = json.loads((site / "funds.json").read_text(encoding="utf-8"))
    regular = next(f for f in funds if f["id"] == REGULAR)
    assert regular["plan"] == "regular" and regular["direct"] == DIRECT
    assert regular["amfi"] == "900002" and regular["name"].endswith("(Regular)")
    assert regular["prices_from"] == (TODAY - timedelta(days=300)).isoformat()
    # Its fund house, as its Direct plan's: the picker finds a fund by its house (C-01).
    direct = next(f for f in funds if f["id"] == DIRECT)
    assert regular["house"] == direct["house"]
    assert (site / "data" / "nav" / "900002.csv.gz").exists()
    assert not (site / "fund" / REGULAR).exists()


def test_your_portfolio_says_what_it_can_hold(site: Path) -> None:
    """Regular plans and sales are entered as such now (audit, 2026-10-04); the
    note says so, and what is still not modelled."""
    page = _flat((site / "portfolio" / "index.html").read_text(encoding="utf-8"))
    assert "Direct and Regular plans are listed" in page
    assert "Enter a sale as the amount you received" in page
    assert "Direct version" not in page


def test_funds_json_lists_every_published_fund_for_the_portfolio_page(site: Path) -> None:
    funds = json.loads((site / "funds.json").read_text(encoding="utf-8"))
    assert {f["id"] for f in funds if f.get("plan") != "regular"} == {DIRECT, AGGREGATED}
    one = next(f for f in funds if f["id"] == DIRECT)
    assert set(one) == {"id", "amfi", "name", "category", "category_name",
                        "prices_from", "ter", "size", "r1", "r3", "r5",
                        "vol3", "fall3",
                        # for the compare page (V1-85)
                        "house", "benchmark", "sharpe3", "rank3", "labels",
                        # Your portfolio's reference (UI/UX critique P-01)
                        "tracker"}
    assert one["amfi"] == "900001"
    assert one["category"] == "equity/flexi_cap"
    assert one["prices_from"] == (TODAY - timedelta(days=300)).isoformat()
    assert one["r1"] is None or isinstance(one["r1"], str)  # Decimal as text


def test_each_fund_with_a_disclosure_has_a_look_through_file(site: Path) -> None:
    mine = json.loads((site / "data" / "lookthrough" / f"{DIRECT}.json")
                      .read_text(encoding="utf-8"))
    assert mine["as_of"] == "2026-08-31" and mine["aggregator"] is False
    assert mine["holdings"] == [["ACME", "Acme", "equity", "100"]]
    assert sum(Decimal(w) for _, _, _, w in mine["holdings"]) == 100
    theirs = json.loads((site / "data" / "lookthrough" / f"{AGGREGATED}.json")
                        .read_text(encoding="utf-8"))
    assert theirs["aggregator"] is True


def test_the_prices_the_page_reads_are_published_with_the_site(site: Path) -> None:
    assert (site / "data" / "nav" / "900001.csv.gz").is_file()


def test_the_portfolio_page_is_published_and_runs_only_from_this_site(site: Path) -> None:
    page = (site / "portfolio" / "index.html").read_text(encoding="utf-8")
    assert f'src="{BASE}/static/portfolio-math.js"' in page
    assert f'src="{BASE}/static/portfolio.js"' in page
    assert f'src="{BASE}/static/kit.js"' in page
    assert f'data-root="{BASE}"' in page
    assert "nothing you enter is sent anywhere" in page
    assert "default-src 'self'" in page  # the CSP meta tag is unchanged
    assert (site / "static" / "portfolio.js").is_file()
    assert (site / "static" / "portfolio-math.js").is_file()
    home = (site / "index.html").read_text(encoding="utf-8")
    assert f'href="{BASE}/portfolio/"' in home


def test_the_settings_travel_with_the_site(site: Path) -> None:
    for name in ("settings.js", "fonts/atkinson-hyperlegible-latin-400-normal.woff2",
                 "fonts/atkinson-hyperlegible-latin-700-normal.woff2"):
        assert (site / "static" / name).is_file(), name
    assert not (site / "static" / "theme.js").exists()
    assert '<dialog id="settings"' in _page(site, DIRECT)


def test_the_zoom_row_is_reserved_before_scripts_run(site: Path) -> None:
    page = _page(site, DIRECT)
    growth = page[page.index('data-view-id="fund_growth"'):]
    assert growth.index("data-zoom-slot") < growth.index("echart__canvas")


def test_the_public_fund_page_has_its_navigator(site: Path) -> None:
    page = _page(site, DIRECT)
    assert '<nav class="sections"' in page and 'href="#fund_peers"' in page
    assert (site / "static" / "sections.js").is_file()


def test_funds_json_carries_what_the_compare_page_shows(site: Path) -> None:
    funds = json.loads((site / "funds.json").read_text(encoding="utf-8"))
    one = next(f for f in funds if f["id"] == DIRECT)
    assert {"house", "benchmark", "sharpe3", "rank3", "labels"} <= set(one)
    assert set(one["labels"]) == {"size", "ter", "r1", "r3", "r5", "vol3", "fall3",
                                  "sharpe3", "prices_from"}
    assert one["labels"]["prices_from"] == format_date(TODAY - timedelta(days=300))
    assert one["labels"]["r5"] is None and one["r5"] is None  # no five years yet


def test_an_index_funds_price_stands_in_for_the_benchmark_it_declares(
    warehouse: sqlite3.Connection,
) -> None:
    tracker, younger = "INF000T01052", "INF000T01060"
    for sid, name, days in ((tracker, "Test 50 Index Fund", 400),
                            (younger, "Young 50 Index Fund", 300)):
        warehouse.execute(
            "INSERT INTO scheme (scheme_id, scheme_name, fund_name, plan, option,"
            " amc_id, scheme_family, sebi_category, status, last_seen) VALUES"
            " (?,?,?,'direct','growth','amc1',?,'Index Funds - Equity Funds',"
            " 'active',?)", (sid, name, name, name, TODAY))
        _prices(warehouse, sid, days)
    declared = {DIRECT: "Test 50 Total Return Index", tracker: "TEST 50 TRI",
                younger: "Test 50 Total Return Index"}
    market = publish.PublicMarket(warehouse, declared)

    # The longest record stands in; a tracker is never its own benchmark.
    assert market.benchmark_for(SchemeId(DIRECT)) == f"proxy:{tracker}"
    assert market.benchmark_for(SchemeId(tracker)) == f"proxy:{younger}"
    assert market.benchmark_for(SchemeId(AGGREGATED)) is None  # declares nothing
    facts = market.scheme_facts(SchemeId(DIRECT))
    assert facts is not None
    assert facts.benchmark_name == "Test 50 (via Test 50 Index Fund)"
    series = market.index_series(IndexId(f"proxy:{tracker}"),
                                 TODAY - timedelta(days=2), TODAY)
    assert [p.level for p in series] == [Decimal(498), Decimal(499)]  # to yesterday
    # The index's own levels stay withheld.
    assert market.index_series(IndexId("NSE:TEST_TRI"),
                               TODAY - timedelta(days=9), TODAY) == []


def test_funds_json_names_the_index_fund_on_each_funds_benchmark(
    warehouse: sqlite3.Connection, tmp_path: Path,
) -> None:
    """UI/UX critique P-01: Your portfolio sets each holding beside the same money
    in the index fund standing in for its benchmark -- the one its page draws
    (`tracker`), a Regular plan its Direct plan's -- and None where there is none."""
    tracker = "INF000T01052"
    warehouse.execute(
        "INSERT INTO scheme (scheme_id, scheme_name, fund_name, plan, option,"
        " amc_id, scheme_family, sebi_category, status, last_seen) VALUES"
        " (?,?,?,'direct','growth','amc1',?,'Index Funds - Equity Funds',"
        " 'active',?)", (tracker, "Test 50 Index Fund", "Test 50 Index Fund",
                         "Test 50 Index Fund", TODAY))
    _prices(warehouse, tracker, 400)
    declared = {DIRECT: "Test 50 Total Return Index", tracker: "TEST 50 TRI"}
    out = tmp_path / "site"
    publish.build_site(warehouse, out, BASE, TODAY, declared)
    listed = json.loads((out / "funds.json").read_text(encoding="utf-8"))
    funds = {f["id"]: f for f in listed}
    assert funds[DIRECT]["tracker"] == tracker
    assert funds[REGULAR]["tracker"] == tracker
    assert funds[AGGREGATED]["tracker"] is None


def test_the_growth_chart_starts_where_its_benchmark_does(
    warehouse: sqlite3.Connection,
) -> None:
    """UI/UX critique F-06: over the fund's whole record ("All", the page's view) a
    benchmark younger than the fund was dropped, so a reader never saw it. The
    growth chart starts on the benchmark's first day instead, both lines drawn,
    and the price per unit beside it keeps the fund's whole record."""
    from src.m6_views.builder import Scope

    tracker = "INF000T01052"
    warehouse.execute(
        "INSERT INTO scheme (scheme_id, scheme_name, fund_name, plan, option,"
        " amc_id, scheme_family, sebi_category, status, last_seen) VALUES"
        " (?,?,?,'direct','growth','amc1',?,'Index Funds - Equity Funds',"
        " 'active',?)", (tracker, "Test 50 Index Fund", "Test 50 Index Fund",
                         "Test 50 Index Fund", TODAY))
    _prices(warehouse, tracker, 200)   # the fund has 300 days
    deps = publish.public_deps(warehouse, {DIRECT: "Test 50 Total Return Index",
                                           tracker: "TEST 50 TRI"})
    scope = Scope(user_id=publish.PUBLIC_USER, as_of=TODAY, scope_type="scheme",
                  scope_id=DIRECT)
    env = publish._build(deps, "fund_growth", scope, {"window": "max"})
    growth, price = env.payload["charts"]
    assert [s["role"] for s in growth["series"]] == ["fund", "benchmark"]
    begins = (TODAY - timedelta(days=200)).isoformat()
    assert growth["series"][0]["points"][0][0] == begins
    assert price["series"][0]["points"][0][0] == (TODAY - timedelta(days=300)).isoformat()
    assert any("the first day its benchmark has prices" in c for c in env.caveats)
    assert growth.get("log") is True   # a log scale on offer, for long records


def test_an_index_fund_whose_page_is_not_read_yet_names_its_index_itself(
    warehouse: sqlite3.Connection,
) -> None:
    """External audit, 2026-10-04: an index fund showed benchmark "—" until the
    aggregator crawl reached its page (100 a night). Its own name says which
    index it tracks; only an exact match with an index another fund declares
    counts, the longest first, so "Test 50 Equal Weight" never borrows "Test 50"."""
    tracker, unread, weighted = "INF000T01052", "INF000T01078", "INF000T01086"
    for sid, name in ((tracker, "Acme Test 50 Index Fund"),
                      (unread, "Other House Test 50 Index Fund"),
                      (weighted, "Third Test 50 Equal Weight Index Fund")):
        warehouse.execute(
            "INSERT INTO scheme (scheme_id, scheme_name, fund_name, plan, option,"
            " amc_id, scheme_family, sebi_category, status, last_seen) VALUES"
            " (?,?,?,'direct','growth','amc1',?,'Index Funds - Equity Funds',"
            " 'active',?)", (sid, name, name, name, TODAY))
        _prices(warehouse, sid, 400)
    market = publish.PublicMarket(warehouse, {tracker: "TEST 50 TRI"})
    assert market.benchmark_for(SchemeId(unread)) == f"proxy:{tracker}"
    facts = market.scheme_facts(SchemeId(unread))
    assert facts is not None
    assert facts.benchmark_name == "TEST 50 (via Acme Test 50 Index Fund)"
    assert market.benchmark_for(SchemeId(weighted)) is None
    assert market.benchmark_for(SchemeId(AGGREGATED)) is None  # not an index fund


def test_an_aggregators_holdings_are_published_and_say_whose_they_are(
    site: Path,
) -> None:
    """V1-79 (reversing V1-72's withholding): drawn, with the source named."""
    page = _page(site, AGGREGATED)
    assert "Largest holdings" in page
    assert "comes from Groww&#39;s page for the fund, an aggregator" in page
    # Marked where it is always read, not only in the notes, which start closed;
    # and never badged "current, complete, and resolved".
    assert "holdings in the portfolio shown on Groww&#39;s page for" in page
    owns = page[page.index("What does this fund own?"):]
    assert 'badge--medium' in owns[:600]
    assert "Groww&#39;s page" not in _page(site, DIRECT)


def test_the_policy_travels_in_the_page(site: Path) -> None:
    """Pages cannot send headers, so the CSP is a <meta> tag, and the page
    names what it is and what it leaves out."""
    page = _page(site, DIRECT)
    assert '<meta http-equiv="Content-Security-Policy"' in page
    assert "script-src 'self'" in page
    assert "Descriptive, not advice." in page
    # The local app's portfolio views stay out (V1-72); the public page that
    # builds one in the browser is linked instead (V1-82).
    assert "/view/" not in page and "sidenav" not in page
    assert f'href="{BASE}/portfolio/"' in page
    assert f'href="{BASE}/fund/{DIRECT}/fund_growth.csv"' in page


def test_a_directory_it_did_not_write_is_not_deleted(
    warehouse: sqlite3.Connection, tmp_path: Path
) -> None:
    precious = tmp_path / "notes"
    precious.mkdir()
    (precious / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(RuntimeError, match="did not write"):
        publish.build_site(warehouse, precious, BASE, TODAY)
    assert (precious / "keep.txt").exists()


def test_a_site_too_large_for_pages_stops_the_build() -> None:
    publish.check_budget(100, budget=100)
    with pytest.raises(publish.SiteTooLarge):
        publish.check_budget(101, budget=100)


def test_every_fund_is_listed_in_one_table_on_its_own_page(site: Path) -> None:
    """DECISIONS V1-74, moved to /funds/ in V1-80: a table of every published
    fund, sortable and narrowed by family or category in the browser, and the
    grouped lists beneath for no script."""
    index = (site / "funds" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<table data-filterable data-rows="[^"]+"', index)
    flexi = '<tr data-family="equity" data-category="equity/flexi_cap">'
    assert index.count(flexi) == 2
    assert '<option value="equity/flexi_cap">Flexi cap</option>' in index
    assert f'href="{BASE}/fund/{DIRECT}/"' in index
    assert 'class="explorer__group"' in index
    for name in publish.STATIC_FILES:
        assert (site / "static" / name).exists(), name
    # Three hundred days of prices span no fixed window: every return is a
    # dash, never a figure for a period the history does not cover. The
    # fixture has no fund size, expense ratio (V1-78) or peers (V1-77) either:
    # three dashes more.
    row = re.search(r'<tr data-family="equity"[^>]*>(.*?)</tr>', index, re.S)
    assert row is not None and "data-value=\"0." not in row.group(1)
    # Volatility, deepest fall and Sharpe too (E-05), shown when chosen: nine.
    assert row.group(1).count("—") == 9


def test_explore_draws_fifty_funds_and_publishes_every_row(site: Path) -> None:
    """UI/UX critique E-01, E-02, E-04: all 1,662 rows were drawn at once (1.88 MB,
    31,170 nodes), alphabetically, and the no-script lists showed beneath for
    everyone. The page draws the largest 50; every fund's cells, formatted here,
    are in funds/rows.json for app.js to filter, sort and show 50 more; the
    grouped lists are inside <noscript>."""
    index = (site / "funds" / "index.html").read_text(encoding="utf-8")
    rows = json.loads((site / "funds" / "rows.json").read_text(encoding="utf-8"))
    assert {r["id"] for r in rows} == {DIRECT, AGGREGATED}
    one = next(r for r in rows if r["id"] == DIRECT)
    assert {"id", "name", "house", "family", "cat", "cat_name", "c"} <= set(one)
    assert set(one["c"]) == {"size", "ter", "r1", "r3", "r5", "rank",
                             "vol3", "fall3", "sharpe3"}
    assert one["c"]["r3"] == ["", DASH, "", ""]   # three hundred days: no 3 years
    assert f'data-rows="{BASE}/funds/rows.json"' in index
    assert publish.EXPLORE_FIRST == 50
    assert index.count("<tr data-family=") <= publish.EXPLORE_FIRST
    # Largest first, and the heading says so.
    largest = r'<th scope="col"[^>]*data-col="size"[^>]*aria-sort="descending"'
    assert re.search(largest, index)
    after = index[index.index('id="funds"'):]
    fold = re.search(r"<noscript>(.*?)</noscript>", after, re.S)
    assert fold and 'class="explorer__group"' in fold.group(1)
    assert index.count('class="explorer__group"') == fold.group(1).count(
        'class="explorer__group"')


def test_explore_says_when_nothing_matches_and_offers_more(site: Path) -> None:
    """E-03: a filter matching nothing left "0 of 1662 funds" in small type. The
    page says so and offers to clear the filters; past fifty, "Show 50 more";
    E-05: a chooser for the columns, the three measures of risk off at first."""
    index = _flat((site / "funds" / "index.html").read_text(encoding="utf-8"))
    raw = (site / "funds" / "index.html").read_text(encoding="utf-8")
    assert "No funds match these filters." in index and "Clear filters" in index
    assert re.search(r"<div class=\"table-empty\" data-empty hidden>", raw)
    assert re.search(r'<button type="button"[^>]*data-more>Show 50 more</button>', raw)
    chooser = re.search(r'<details class="columns" data-columns hidden>(.*?)</details>',
                        raw, re.S)
    assert chooser
    for key in ("vol3", "fall3", "sharpe3", "r1", "ter"):
        assert f'value="{key}"' in chooser.group(1), key
    assert 'data-hide="vol3 fall3 sharpe3"' in raw


PRIVACY = (
    "Nothing you enter leaves your browser",
    # The funds viewed lately too (UI/UX critique G-21, 2026-10-04): a key the
    # page kept and did not mention.
    "Your portfolio, your settings and the funds you viewed lately are kept in this"
    " browser's own storage, on this device. Nothing you enter is sent anywhere or kept"
    " on any server. You can clear them at any time: More, then Remove everything, on"
    " Your portfolio; Reset to"
    " defaults and Clear recently viewed in Settings.",
    "No accounts, no cookies, no analytics.",
    "The page loads nothing from any other site: its content security policy allows"
    " only this one.",
    "Like any web host, Vercel keeps ordinary request logs (the address and the page"
    " asked for), never what you type into a page.",
)
SECTIONS = (("lookup", "Look up a fund"), ("categories", "Understand funds"),
            ("portfolio", "See your portfolio"), ("privacy", "Your data stays yours"),
            ("about", "About the data"))


def _flat(html: str) -> str:
    """The page's text with tags dropped and whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split()).replace("&#39;", "'")


def test_the_front_page_is_a_way_in_not_a_list(site: Path) -> None:
    """V1-89: a hero with three equal doors, then one section per door, each named
    by its door; the fund map is kept as "Understand funds"."""
    index = (site / "index.html").read_text(encoding="utf-8")
    assert len(re.findall(r"<h1[\s>]", index)) == 1
    # External audit, 2026-10-04: the address asks "Did my SIP work?", so the page
    # leads with it, and its first door is Your portfolio.
    assert re.search(r"<h1[^>]*>\s*Did my SIP work\?", index)
    first = index[index.index('class="lp-door'):]
    first = first[:first.index("</li>")]
    assert "Did my SIP work?" in first and 'href="/Repo/portfolio/"' in first
    # The doors once, not again at the foot of the page (design review).
    assert 'class="lp-end"' not in index
    assert re.search(r'<a[^>]*href="#privacy"[^>]*>[^<]*Nothing you enter leaves your'
                     r' browser', index)
    hero = index[index.index('class="lp-hero"'):index.index('id="lookup"')]
    assert len(re.findall(r'<li class="lp-door[ "]', hero)) == 3
    assert 'data-index="/Repo/search.json"' in hero
    assert 'href="/Repo/portfolio/"' in hero
    # SPEC_SIP_WHAT_IF §5.2: the second door is /sip/; "Understand funds" folds
    # into its sub-line as a way into Learn.
    second = re.findall(r'<li class="lp-door[^"]*">(.*?)</li>', hero, re.S)[1]
    assert "What would a SIP have become?" in second
    assert 'href="/Repo/sip/"' in second
    assert "Choose an amount and a kind of fund. No fund names needed." in _flat(second)
    assert re.search(r'<a href="/Repo/learn/start-here/">New to funds\? Start here</a>',
                     second)
    assert "Understand funds" not in _flat(hero)
    assert ("company by company. Or see what a SIP in any kind of fund would have"
            " become.") in _flat(hero)
    at = [index.index(f'id="{key}"') for key, _ in SECTIONS]
    assert at == sorted(at)
    for (key, eyebrow), here, after in zip(SECTIONS, at, [*at[1:], len(index)],
                                           strict=True):
        part = index[here:after]
        assert eyebrow in part and "<h2" in part, key
    assert "Chapter" not in index and "data-island" not in index
    assert "Flexi cap <span>2</span>" in index
    assert "At least 65% in shares, of any size, in any mix." in index
    assert f'href="{BASE}/funds/#category=equity/flexi_cap">See its 2 funds' in index
    levels = [int(n) for n in re.findall(r"<h([1-6])[\s>]", index)]
    assert all(b <= a + 1 for a, b in pairwise(levels)), levels
    assert len(index.encode("utf-8")) < 200_000


def test_the_privacy_promise_is_word_for_word(site: Path) -> None:
    text = _flat((site / "index.html").read_text(encoding="utf-8"))
    for sentence in PRIVACY:
        assert sentence in text, sentence


def test_the_front_page_is_built_without_an_example_when_none_qualifies(
    site: Path,
) -> None:
    """The fixture's funds have 300 days of prices, so none has a five-year return:
    the page says so where the example would be, and the build still succeeds."""
    index = (site / "index.html").read_text(encoding="utf-8")
    assert "No example tonight" in index and 'class="lp-fund"' not in index


def test_every_picture_says_what_it_shows(site: Path) -> None:
    """On the fixture's page (no example) and on one with the example and the pair,
    whose asset mix and range bars are the pictures that carry figures."""
    pages = [(site / "index.html").read_text(encoding="utf-8"), _home(EXAMPLE, PAIR)]
    for index in pages:
        main = index[index.index('<main'):index.index('</main>')]
        svgs = re.findall(r"<svg\b[^>]*>", main)
        assert svgs
        for tag in svgs:
            labelled = 'role="img"' in tag and re.search(r'aria-label="[^"]+"', tag)
            assert labelled or 'aria-hidden="true"' in tag, tag
    assert 'class="lp-mix"' in pages[1] and 'class="lp-range__bar"' in pages[1]


EXAMPLE = {
    "scheme_id": DIRECT, "name": "Fund One Flexi Cap",
    "detail": "Flexi Cap · Direct · Growth",
    "category": "Flexi cap", "ter_label": "0.75%", "as_of_label": "31 Aug 2026",
    "aggregator": False,
    "mix": [{"label": "Shares", "pct_label": "92.0%", "x": "0.00", "width": "92.00"},
            {"label": "Cash and equivalents", "pct_label": "8.0%", "x": "92.00",
             "width": "8.00"}],
    "top": [{"name": f"Company {n}", "weight_label": f"{9 - n}.0%",
             "width": f"{9 - n}.00"} for n in range(1, 6)],
    "ranges": [{"label": p, "low_label": "1.0%", "high_label": "20.0%",
                "value_label": "12.0%", "pos": "57.89"}
               for p in ("1 year", "3 years", "5 years")],
}
PAIR = {
    "funds": [
        {"scheme_id": DIRECT, "name": "Fund One Flexi Cap", "category": "Flexi cap",
         "top": [{"name": "Company 1", "weight_label": "8.0%", "shared": True},
                 {"name": "Company 2", "weight_label": "7.0%", "shared": False}]},
        {"scheme_id": AGGREGATED, "name": "Fund Two Mid Cap", "category": "Mid cap",
         "top": [{"name": "Company 1", "weight_label": "6.0%", "shared": True}]},
    ],
    "common": 2, "overlap_label": "11.0%",
    "lead": {"name": "Company 1", "share_label": "7.0%"},
}


def _home(example: object, pair: object) -> str:
    return templates(root=BASE, static=True).get_template("home.html").render({
        "catalogue": [], "health": {}, "qs": "", "active": "", "built": TODAY,
        "count": 2, "stats": {"houses": 1, "categories": 1, "prices_to": TODAY},
        "fund_map": [], "example": example, "pair": pair})


def test_the_example_and_pair_render() -> None:
    page = _home(EXAMPLE, PAIR)
    text = _flat(page)
    assert f'href="{BASE}/fund/{DIRECT}/"' in page and 'class="lp-fund"' in page
    # Not always the largest now: a mostly identified portfolio comes first (audit).
    assert ("An example: the largest flexi cap fund whose portfolio we could"
            " identify.") in text
    assert "Fund One Flexi Cap within its category, Flexi cap" in text
    for n in range(1, 6):
        assert f"Company {n}" in text
    for period in ("1 year", "3 years", "5 years"):
        assert period in text
    assert "2 companies in both" in text
    # Audit, 2026-10-04: "with ₹1 in each, Company 1 is 7.0% of what you own"
    # took a second read.
    assert "put ₹1 in each fund and Company 1 is 7.0% of your ₹2" in text
    assert "of the two portfolios is the same" in text
    assert 'width="57.89"' in page  # the fill runs to the fund's position
    none = _flat(_home(EXAMPLE, {**PAIR, "common": 0, "lead": None}))
    assert "No companies in both" in none and "0 companies" not in none
    alone = _flat(_home(EXAMPLE, None))
    assert "No example tonight" in alone


#: Explore funds' table, empty: what explorer.html needs beside the leaders.
EXPLORE_EMPTY = {"explore": [], "columns": publish.EXPLORE_COLUMNS,
                 "hidden": publish.EXPLORE_HIDDEN, "first": publish.EXPLORE_FIRST}


def test_the_leader_tables_live_on_the_funds_page(site: Path) -> None:
    """V1-89: the front page tells the story; each category's highest three-year
    returns sit on /funds/, folded above the table. The fixture's funds have no
    three-year figure, so there is no card and no fold; a rendered card checks the
    fold itself."""
    funds = (site / "funds" / "index.html").read_text(encoding="utf-8")
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'class="leader"' not in index and 'class="leader"' not in funds
    assert "leaders-fold" not in funds
    card = {"key": "equity/flexi_cap", "name": "Flexi cap", "count": 7, "funds": [{
        "scheme_id": DIRECT, "name": "Fund One", "size_label": "₹1,000 Cr",
        "size_value": "1000", "returns": [
            {"label": "10.0%", "value": "0.1", "tone": "gain", "symbol": "▲"}] * 3}]}
    engine = templates(root=BASE, static=True)
    page = engine.get_template("explorer.html").render({
        "catalogue": [], "health": {}, "qs": "", "active": "funds", "built": TODAY,
        "categories": [], "category_options": [], "count": 0, **EXPLORE_EMPTY,
        "families": [], "stats": {"houses": 0, "categories": 0, "prices_to": None},
        "leaders": [card]})
    fold = (r'<details class="leaders-fold">\s*<summary>Highest three-year returns'
            r' in six categories</summary>')
    assert re.search(fold, page)
    assert 'class="leader"' in page and f"{BASE}/fund/{DIRECT}/" in page
    assert "data-island" not in page
    levels = [int(n) for n in re.findall(r"<h([1-6])[\s>]", page)]
    assert all(b <= a + 1 for a, b in pairwise(levels)), levels


def _leader_row(sid: str, key: str, three: str | None) -> dict[str, object]:
    cell = {"value": three or "", "label": three or "—"}
    return {"scheme_id": sid, "name": sid, "category_key": key,
            "category_short": key.split("/")[1], "returns": [cell, cell, cell]}


def test_category_cards_hold_the_highest_three_year_returns_in_order() -> None:
    rows = [_leader_row(f"F{i}", "equity/flexi_cap", v)
            for i, v in enumerate(["0.12", "0.3", "0.05", None, "0.21", "0.09", "0.18"])]
    rows.append(_leader_row("M0", "equity/mid_cap", None))
    cards = publish.category_leaders(rows)
    assert [c["key"] for c in cards] == ["equity/flexi_cap"]  # no 3-year figure: no card
    flexi = cards[0]
    # Decimal order, not text order ("0.3" > "0.21"), five of them, of seven.
    assert [f["scheme_id"] for f in flexi["funds"]] == ["F1", "F4", "F6", "F0", "F5"]
    assert flexi["count"] == 7


@pytest.mark.parametrize(("category", "family"), [
    ("Equity Scheme - Flexi Cap Fund", "equity"),
    ("Equity Schemes - Thematic Fund", "equity"),
    ("Growth", "equity"),
    ("ELSS", "equity"),
    ("Debt Scheme - Gilt Fund", "debt"),
    ("Income/Debt Oriented Schemes - Liquid Fund", "debt"),
    ("Income", "debt"),
    ("Hybrid Schemes - Arbitrage Fund", "hybrid"),
    ("Solution Oriented Schemes ** - Retirement Fund", "solution"),
    ("Other Scheme - Index Funds", "other"),
    ("Exchange Traded Funds (ETFs) - Equity ETF", "other"),
    ("Overseas Fund of Funds - Fund of Funds investing overseas", "other"),
])
def test_every_generation_of_category_name_finds_its_family(
    category: str, family: str
) -> None:
    """AMFI's list mixes naming generations; the tiles must count them all, or a
    legacy "Income" fund is filed under index funds and ETFs."""
    assert category_of(category).family == family


def test_the_compare_page_is_published_and_linked(site: Path) -> None:
    page = (site / "compare" / "index.html").read_text(encoding="utf-8")
    for script in ("portfolio-math.js", "kit.js", "charts.js", "compare.js"):
        assert f'src="{BASE}/static/{script}"' in page, script
    assert "needs JavaScript" in page and 'id="cmp-pick"' in page
    assert (site / "static" / "compare.js").is_file()
    assert f'href="{BASE}/compare/"' in _page(site, DIRECT)
    assert f'href="{BASE}/compare/#f={DIRECT}"' in _page(site, DIRECT)


LEARN_NOTE = ("This explains how things work. "
              "It is not advice about what to buy, sell or hold.")


def test_the_learn_pages_are_published(site: Path) -> None:
    from markupsafe import escape
    from src.m6_views.learn import load

    learn = load()
    assert LEARN_NOTE in (site / "learn" / "index.html").read_text(encoding="utf-8")
    for guide in learn.guides:
        page = (site / "learn" / guide.slug / "index.html").read_text(encoding="utf-8")
        assert LEARN_NOTE in page and str(escape(guide.title)) in page, guide.slug
        for ref in guide.sources:
            assert ref.url in page and format_date(ref.checked) in page, ref.url
    glossary = (site / "learn" / "glossary" / "index.html").read_text(encoding="utf-8")
    assert LEARN_NOTE in glossary
    for key in learn.terms:
        assert f'id="{key}"' in glossary, key


def test_the_top_bar_links_learn(site: Path) -> None:
    assert f'href="{BASE}/learn/"' in _page(site, DIRECT)


def test_search_finds_terms_and_guides(site: Path) -> None:
    from src.m6_views.learn import load

    entries = json.loads((site / "search.json").read_text(encoding="utf-8"))
    assert {"name": "Expense ratio (TER)", "detail": "Glossary",
            "url": f"{BASE}/learn/glossary/#expense_ratio"} in entries
    guides = {e["url"] for e in entries if e["detail"] == "Guide"}
    assert guides == {f"{BASE}/learn/{g.slug}/" for g in load().guides}


def test_the_public_copy_says_why_a_fund_has_no_portfolio(tmp_path: Path) -> None:
    """The public page is read by people with no command line: it gets the reason
    in words, not the local app's commands."""
    from src.m6_views.builder import Scope
    from src.m6_views.states import empty_envelope

    scope = Scope(user_id=publish.PUBLIC_USER, as_of=date(2026, 10, 2),
                  scope_type="scheme", scope_id=DIRECT)
    local = empty_envelope("fund_portfolio", "What does this fund own?", scope,
                           "No portfolio. Run python -m jobs.fetch_groww.")
    shown = publish._adapter(tmp_path, f"{BASE}/fund/{DIRECT}/", scope)(local)
    assert shown.state_reason == publish.NO_PORTFOLIO
    assert "python -m" not in shown.state_reason
    assert "about 100 a night" in shown.state_reason


# --- the top bar, skip link and chrome (UX audit, V1-88) ------------------------


def _published(site: Path) -> dict[str, str]:
    pages = {"front": "index.html", "funds": "funds/index.html",
             "learn": "learn/index.html",
             "compare": "compare/index.html", "fund": f"fund/{DIRECT}/index.html"}
    return {k: (site / v).read_text(encoding="utf-8") for k, v in pages.items()}


def test_every_page_starts_with_a_skip_link(site: Path) -> None:
    for name, html in _published(site).items():
        body = html[html.index("<body"):]
        first = re.search(r">\s*(<[a-z]+[^>]*>)", body)
        assert first and 'class="skip-link"' in first.group(1), name
        assert 'href="#content"' in first.group(1) and '<main id="content"' in html, name


def test_the_public_menu_holds_every_link(site: Path) -> None:
    """One nav, shown inline on wide screens and as a native popover below 1180px,
    opened by a "Menu" button (V1-88): no script needed to open or close it."""
    html = _published(site)["funds"]
    menu = r'<button[^>]*class="topmenu__summary"[^>]*popovertarget="topnav"[^>]*>\s*Menu'
    assert re.search(menu, html)
    nav = re.search(r'<nav class="topnav" id="topnav" popover[^>]*>(.*?)</nav>',
                    html, re.S)
    assert nav
    links = re.findall(r'class="topnav__link"[^>]*>([^<]+)<', nav.group(1))
    assert [x.strip() for x in links] == ["Explore funds", "Compare", "What if",
                                         "Your portfolio", "Learn", "Categories",
                                         "About the data"]
    current = re.search(r'aria-current="page"[^>]*>([^<]+)<', nav.group(1))
    assert current and current.group(1).strip() == "Explore funds"


def test_the_top_bar_has_no_repository_link_and_the_footer_does(site: Path) -> None:
    html = _published(site)["front"]
    bar = re.search(r'<header class="topbar topbar--public">(.*?)</header>', html, re.S)
    assert bar and "github.com" not in bar.group(1)
    foot = re.search(r"<footer[^>]*>(.*?)</footer>", html, re.S)
    assert foot and "github.com" in foot.group(1)


def test_the_public_note_is_one_line(site: Path) -> None:
    html = _published(site)["fund"]
    note = re.search(r'<div class="public-note">(.*?)</div>', html, re.S)
    assert note and "Descriptive, not advice." in note.group(1)
    assert f'href="{BASE}/#about"' in note.group(1) and "<details" not in note.group(1)


def test_no_figure_counts_up_and_no_headline_blurs_in(site: Path) -> None:
    """Every figure shows its real value from the first frame (V1-88)."""
    for name, html in _published(site).items():
        assert 'data-island="count-up"' not in html, name
        assert 'data-island="blur-text"' not in html, name


# --- the fund card, badge and copy (design review, V1-88) -----------------------


def test_the_fund_card_does_not_repeat_its_facts(site: Path) -> None:
    """The chips carry the plan, the option and the ISIN; fund house and category
    are said once, in the facts grid (V1-88)."""
    page = _page(site, DIRECT)
    chips = re.search(r'<ul class="fundcard__chips">(.*?)</ul>', page, re.S)
    assert chips
    shown = re.findall(r"<li[^>]*>([^<]+)</li>", chips.group(1))
    assert shown == ["Direct", "Growth", DIRECT]
    facts = re.search(r'<dl class="facts facts--grid">(.*?)</dl>', page, re.S)
    assert facts
    category = re.search(r"<dt>Category.*?</dt>\s*<dd>([^<]+)</dd>", facts.group(1), re.S)
    assert category and category.group(1).strip() == "Flexi cap"


def test_the_badge_says_what_it_is(site: Path) -> None:
    badges = re.findall(r'class="badge badge--\w+"[^>]*>([^<]+)<', _page(site, DIRECT))
    assert badges and all(b.strip().startswith("Confidence: ") for b in badges), badges


def test_counts_agree_with_their_nouns() -> None:
    """Every count on the front page that is followed by "fund" picks the plural
    by the number, so a family of one reads "1 fund"."""
    home = (publish.TEMPLATES if hasattr(publish, "TEMPLATES") else
            Path(__file__).resolve().parents[2] / "src" / "m6_views" / "templates")
    text = (Path(home) / "home.html").read_text(encoding="utf-8")
    for m in re.finditer(r"\{\{ ([^}]*?)(?: \| fmt_count)? \}\} funds?\b", text):
        tail = text[m.end():m.end() + 40]
        assert tail.startswith("{{ '' if"), m.group(0)


def test_older_category_names_say_what_they_are() -> None:
    config = Path(__file__).resolve().parents[2] / "config" / "categories.yaml"
    yaml_text = config.read_text(encoding="utf-8")
    assert "(older naming)" not in yaml_text
    assert "(earlier AMFI heading)" in yaml_text
    import yaml
    earlier = [c for c in yaml.safe_load(yaml_text)["categories"]
               if c["name"].endswith("(earlier AMFI heading)")]
    assert len(earlier) == 10
    for c in earlier:
        assert re.search(r"AMFI has since (renamed|split|replaced)", c["about"]), c["key"]
        assert "(earlier AMFI heading)" not in c["about"], c["key"]
        for text in (c["about"], c.get("note", "")):
            assert not re.search(r"\b(19|20)\d\d\b", text), c["key"]


def test_headings_carry_only_their_words(site: Path) -> None:
    """A "?" inside an <h2> becomes part of the heading's name, and of the section
    it labels (V1-88); it sits just after the heading instead."""
    for page in ("compare/index.html", "portfolio/index.html"):
        html = (site / page).read_text(encoding="utf-8")
        for heading in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S):
            assert 'class="term"' not in heading, page
        assert re.search(r"</h2>\s*<button[^>]*class=\"term\"", html), page


def test_the_fund_pickers_are_search_fields(site: Path) -> None:
    """Compare's and Your portfolio's fund box reads like the top bar's search: a
    magnifier beside it (V1-93). Its list is Kit.picker's combobox, which finds a
    fund by its house or ISIN too, not the browser's <datalist> of 1,662 names
    matched only on a run of letters (UI/UX critique C-01)."""
    static = Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
    for page, pick, script in (("compare/index.html", "cmp-pick", "compare.js"),
                               ("portfolio/index.html", "pf-pick", "portfolio.js")):
        html = (site / page).read_text(encoding="utf-8")
        box = re.search(r'<div class="field-search">(.*?)</div>', html, re.S)
        assert box and 'class="icon field-search__icon"' in box.group(1), page
        assert f'id="{pick}"' in box.group(1), page
        assert " list=" not in box.group(1) and "<datalist" not in html, page
        code = (static / script).read_text(encoding="utf-8")
        assert f'K.picker(document.getElementById("{pick}")' in code, script
    css = (static / "app.css").read_text(encoding="utf-8")
    # The active option, chosen with the arrows while focus stays in the box, is
    # ringed: a tint alone is about 1.05:1.
    active = r'\.picker \[aria-selected="true"\]\s*\{[^}]*outline: 2px solid'
    assert re.search(active, css)


def test_icon_buttons_say_what_they_do() -> None:
    """The bin and the cross on Your portfolio carry no word, so each has a name
    that a screen reader reads and a pointer shows (V1-93)."""
    script = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
              / "portfolio.js").read_text(encoding="utf-8")
    calls = re.findall(r'el\("button", \{[^}]*button--icon[^}]*\}', script)
    assert calls
    for call in calls:
        assert '"aria-label"' in call and "title:" in call, call


def test_row_errors_are_tied_to_their_fields() -> None:
    """A row's error marks its fields invalid, points them at the message, and is
    announced; clearing it undoes all three (V1-88)."""
    script = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
              / "portfolio.js").read_text(encoding="utf-8")
    body = script[script.index("function showRowError"):]
    body = body[:body.index("\n  }\n") + 4]
    needles = ('"aria-invalid"', '"aria-describedby"', "removeAttribute")
    for needle in needles:
        assert needle in body, needle
    # A live region inserted already filled is often not read out: every row gets
    # an empty polite one when it is drawn, and errors only change its text.
    slot = script[script.index("function errorSlot"):]
    slot = slot[:slot.index("\n  }\n") + 4]
    assert '"aria-live": "polite"' in slot
    assert ".remove()" not in body
    card = script[script.index("function holdingCard"):]
    card = card[:card.index("\n  }\n") + 4]
    # Purchases, SIPs and (since the audit of 2026-10-04) sales: one slot each,
    # from the one row builder all three use (UI/UX critique P-05).
    assert card.count("errorSlot()") == 1 and 'err && el("p"' not in card
    assert card.count('return row("') == 3
    css = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
           / "app.css").read_text(encoding="utf-8")
    # Empty, it leaves the row's flex flow (a flex line's gap would remain) but
    # stays in the accessibility tree, as display: none would not.
    assert re.search(r"\.pf__error:empty\s*\{[^}]*position:\s*absolute", css)


def test_the_islands_are_gone() -> None:
    """V1-89 retired the React islands with the front page that used them: no bundle,
    no build folder, no script tag, no styles, and one checksum per vendored file."""
    repo = Path(__file__).resolve().parents[2]
    static = repo / "src" / "m6_views" / "static"
    assert not (repo / "ui").exists()
    assert not (static / "vendor" / "islands.v1.js").exists()
    assert not any("islands" in name for name in publish.STATIC_FILES)
    sums = (static / "vendor" / "SHA256SUMS").read_text(encoding="utf-8")
    assert "islands" not in sums
    listed = re.findall(r"(?m)^[0-9a-f]{64}  (\S+)$", sums)
    assert sorted(listed) == sorted(set(listed))
    assert sorted(listed) == sorted(p.name for p in (static / "vendor").glob("*.js"))
    templates_dir = repo / "src" / "m6_views" / "templates"
    for page in templates_dir.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "data-island" not in text and "islands.v1.js" not in text, page.name
    css = (static / "app.css").read_text(encoding="utf-8")
    for gone in ("aurora", "blur-text", "card-spotlight", "count-up"):
        assert gone not in css, gone


def test_a_public_search_is_never_sent_to_the_server(site: Path) -> None:
    """V1-89 final review: "Nothing you enter leaves your browser". A form field with a
    name is sent in the address (`/funds/?q=…`) and lands in the host's request log, so
    the public search boxes have none; app.js carries a submitted search in the
    fragment (`/funds/#q=…`), which browsers never send."""
    for page in sorted(site.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        for tag in re.findall(r"<input\b[^>]*data-index=[^>]*>", html):
            assert " name=" not in tag, (page.name, tag)
    script = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
              / "app.js").read_text(encoding="utf-8")
    handler = script[script.index('addEventListener("submit"'):][:400]
    assert "preventDefault" in handler and "searchTarget(" in handler


def test_each_fallback_gives_its_real_reason() -> None:
    """With no example fund the pair has none to start from; say so, and name every
    condition the example must meet (V1-89 final review)."""
    text = _flat(_home(None, None))
    assert ("No example tonight: no flexi cap fund has holdings, five years of prices,"
            " a cost figure and its category's ranges in this build.") in text
    assert "No example tonight: there is no example fund above to pair with." in text
    assert "no second equity fund" not in text
    alone = _flat(_home(EXAMPLE, None))
    no_pair = "No example tonight: no second equity fund with holdings in this build."
    assert no_pair in alone


def test_the_hero_reads_in_the_order_it_shows() -> None:
    """On a phone the hero shows its words, then the doors, then the example; the
    page's order is the same, so Tab and a screen reader follow what is seen."""
    page = _home(EXAMPLE, PAIR)
    hero = page[page.index('class="lp-hero"'):page.index('id="lookup"')]
    assert hero.index('class="lp-hero__text"') < hero.index('class="lp-doors') \
        < hero.index('class="lp-fund"')


def test_the_example_card_says_what_its_list_is() -> None:
    page = _home(EXAMPLE, PAIR)
    assert 'aria-label="Its largest holdings"' in page and "five largest" not in page


def test_the_pair_count_is_formatted() -> None:
    text = _flat(_home(EXAMPLE, {**PAIR, "common": 1234}))
    assert "1,234 companies in both" in text
    one = _flat(_home(EXAMPLE, {**PAIR, "common": 1}))
    assert "1 company in both" in one


def test_push_publishes_and_leaves_nothing_writing_into_its_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V1-90: a 400 MB commit is far past git's loose-object threshold, so `git
    commit` started `gc --auto` detached, still writing into `.git` while the
    temporary directory was removed ("Directory not empty: '.git'"): the push
    had gone through and the build failed anyway. Automatic packing and
    maintenance are off in the throwaway repository before it commits."""
    import subprocess

    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    site = tmp_path / "site"
    (site / "fund").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    (site / "fund" / "a.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SITE_PUSH_URL", str(remote))

    calls: list[tuple[str, ...]] = []
    real = publish._git

    def spy(*args: str, cwd: Path | None = None) -> str:
        calls.append(args)
        if args[:1] == ("config",) and args[1] in ("user.name", "user.email"):
            return "Test"  # the runner's identity; not every machine has one set
        return real(*args) if cwd is None else real(*args, cwd=cwd)

    monkeypatch.setattr(publish, "_git", spy)
    publish.push(site)

    shown = subprocess.run(["git", "--git-dir", str(remote), "show", "--stat",
                            "gh-pages"], capture_output=True, text=True, check=True)
    assert "index.html" in shown.stdout and "fund/a.json" in shown.stdout
    commit = next(i for i, a in enumerate(calls) if "commit" in a)
    before = calls[:commit]
    assert ("config", "gc.auto", "0") in before
    assert ("config", "maintenance.auto", "false") in before


def test_every_labelled_figure_with_a_glossary_entry_explains_itself() -> None:
    """V1-91: the NAV box and the leader tables' Size and year columns gain the
    `?` (and so the hover explanation) their glossary entries already have; the
    explanation's id is unique although the six leader tables repeat."""
    engine = templates(root=BASE, static=True)
    card = {"key": "equity/flexi_cap", "name": "Flexi cap", "count": 7, "funds": []}
    page = engine.get_template("explorer.html").render({
        "catalogue": [], "health": {}, "qs": "", "active": "funds", "built": TODAY,
        "categories": [], "category_options": [], "count": 0, **EXPLORE_EMPTY,
        "families": [], "stats": {"houses": 0, "categories": 0, "prices_to": None},
        "leaders": [card, {**card, "key": "equity/mid_cap", "name": "Mid cap"}]})
    fold = page[page.index('class="leaders-fold"'):page.index('id="funds"')]
    keys = re.findall(r'class="term" popovertarget="[^"]+" data-key="([^"]+)"', fold)
    assert keys.count("aum") == 2 and keys.count("annualised_return") == 6, keys
    ids = re.findall(r'\bid="([^"]+)"', page)
    assert len(ids) == len(set(ids)), sorted(i for i in ids if ids.count(i) > 1)


def test_the_nav_box_explains_nav(site: Path) -> None:
    html = _page(site, DIRECT)
    box = html[html.index('class="fundcard__nav"'):]
    box = box[:box.index("</div>")]
    assert 'data-key="nav"' in box


def test_the_site_tells_vercel_how_to_serve_it(site: Path) -> None:
    """V1-92: the site is hosted on Vercel from the gh-pages branch, with no build
    there. Pages are linked as folders (/fund/<id>/), so a path without its slash
    is redirected to it; files with an extension are not (Vercel's rule)."""
    config = json.loads((site / "vercel.json").read_text(encoding="utf-8"))
    assert config["trailingSlash"] is True


def test_vercel_deploys_the_built_site_and_never_the_source() -> None:
    """main holds the source; deploying it publishes a 404. Only gh-pages, which
    the nightly build pushes, is deployed; and that build links from the root,
    since a vercel.app site is served from /."""
    repo = Path(__file__).resolve().parents[2]
    config = json.loads((repo / "vercel.json").read_text(encoding="utf-8"))
    assert config["git"]["deploymentEnabled"] == {"main": False}
    workflow = (repo / ".github" / "workflows" / "site.yml").read_text(encoding="utf-8")
    assert re.search(r'python -m jobs\.build_site [^\n]*--base ""', workflow)


def test_links_start_at_the_root_unless_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V1-92: Vercel serves the site from its address's root, so a build run by
    hand without --base must not link under /<repository> as GitHub Pages did."""
    import sys

    import jobs.build_site as build_site

    seen: dict[str, str] = {}
    monkeypatch.setattr(publish, "build_site",
                        lambda w, out, base, **kw: seen.update(publish=base) or
                        {"funds": 0, "bytes": 0})
    monkeypatch.setattr(publish, "warehouse_path", lambda: tmp_path / "w.db")
    monkeypatch.setattr(sys, "argv", ["publish_site", "--out", str(tmp_path / "o")])
    with pytest.raises(SystemExit):
        publish.main()
    monkeypatch.setattr(build_site, "contact_email", lambda: "a@example.org")
    monkeypatch.setattr(build_site, "build",
                        lambda out, store, base, workdir, pages: seen.update(build=base)
                        or {"funds": 0, "stored": 0, "bytes": 0})
    monkeypatch.setattr(sys, "argv", ["build_site", "--out", str(tmp_path / "o"),
                                      "--workdir", str(tmp_path / "w")])
    build_site.main()
    assert seen == {"publish": "", "build": ""}


STATIC_DIR = Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"


def test_your_portfolio_answers_first(site: Path) -> None:
    """UI/UX critique P-01, P-02: the answer (one sentence beside each holding's
    reference) leads the summary, and once a portfolio exists the entry form folds
    away above the results instead of sitting 1,300px over them."""
    page = (site / "portfolio" / "index.html").read_text(encoding="utf-8")
    assert page.index('data-out="verdict"') < page.index('data-out="summary"')
    fold = re.search(r'<details class="pf__edit" open>\s*<summary[^>]*><h2', page)
    assert fold and fold.start() < page.index('id="pf-summary-h"')
    holds = r'<details class="pf__edit" open>.*?id="pf-pick".*?</details>'
    assert re.search(holds, page, re.S)
    script = (STATIC_DIR / "portfolio.js").read_text(encoding="utf-8")
    assert "editFold.open = !state.funds.length" in script
    assert "M.reference(x.fund, all, x.pos.firstDate)" in script


def test_clearing_your_portfolio_asks_on_the_page(site: Path) -> None:
    """P-10: Clear sat beside Save with equal weight and asked through `confirm()`.
    It is behind More now, which says what it removes and what it keeps."""
    page = (site / "portfolio" / "index.html").read_text(encoding="utf-8")
    more = re.search(r'<details class="pf__more">(.*?)</details>', page, re.S)
    assert more and 'data-action="clear"' in more.group(1)
    assert "A file you saved is kept" in _flat(more.group(1))
    toolbar = page[page.index('class="pf__toolbar"'):
                   page.index('<details class="pf__more">')]
    assert 'data-action="clear"' not in toolbar
    script = (STATIC_DIR / "portfolio.js").read_text(encoding="utf-8")
    assert "window.confirm" not in script


def test_the_other_funds_say_they_are_hindsight(site: Path) -> None:
    """P-07: picked after the fact, and titled so."""
    page = _flat((site / "portfolio" / "index.html").read_text(encoding="utf-8"))
    assert "In hindsight: the same money in other funds" in page
    assert "says nothing of what comes next" in page


def test_your_portfolios_form_reads_at_a_glance() -> None:
    """P-03: amounts in Indian grouping and in words; P-04: a "Still running" box,
    not "Until (blank if running)"; P-05: each kind of entry under its own name."""
    script = (STATIC_DIR / "portfolio.js").read_text(encoding="utf-8")
    assert "M.grouped(" in script and "M.inWords(" in script
    assert '"Still running"' in script and "Until (blank if running)" not in script
    for legend in ('"Lump sums"', '"SIPs"', '"Sales"'):
        assert legend in script, legend


def test_a_door_card_is_one_link(site: Path) -> None:
    """UI/UX critique H-02: a large card answered only on its small link. The card
    with one destination is a link across its whole face (the link's own ::after);
    the search card keeps its box usable."""
    page = (site / "index.html").read_text(encoding="utf-8")
    doors = re.findall(r'<li class="(lp-door[^"]*)">', page)
    # The SIP door holds two links (§5.2), so it is not one.
    assert doors == ["lp-door lp-door--link", "lp-door", "lp-door"]
    css = re.sub(r"/\*.*?\*/", "", (STATIC_DIR / "app.css").read_text(encoding="utf-8"),
                 flags=re.S)
    assert re.search(r"\.lp-door--link \.lp-door__link::after\s*\{[^}]*inset: 0", css)
    assert re.search(r"\.lp-door--link:focus-within\s*\{", css)


def test_the_fund_map_reads_in_sebis_order_with_mixed_headings_folded() -> None:
    """UI/UX critique H-03: legacy and catch-all headings came first and the families
    in no order a reader knows. Families run equity, hybrid, debt, index funds and
    ETFs, solution oriented; within each, its categories largest first, then the
    headings that mix funds doing different jobs (never ranked), folded away."""
    from src.m0_data.categories import FAMILIES

    assert [key for key, _, _ in FAMILIES] == ["equity", "hybrid", "debt", "other",
                                               "solution"]
    funds = [{"category": "Equity Scheme - Flexi Cap Fund"}] * 2 + [
        {"category": "Other Scheme - Index Funds"},
        {"category": "Equity Scheme - Large Cap Fund"},
        {"category": "Growth"}]
    shown = publish.fund_map(funds)
    assert [f["key"] for f in shown] == ["equity", "other"]
    equity = next(f for f in shown if f["key"] == "equity")
    names = [c["name"] for c in equity["categories"]]
    assert names == ["Flexi cap", "Growth", "Large cap"]
    assert equity["mixed"] == []
    assert [c["name"] for f in shown for c in f["mixed"]] == [
        "Index funds (earlier AMFI heading)"]


def test_the_privacy_picture_draws_one_way(site: Path) -> None:
    """UI/UX critique H-05: a crossed-out arrow back to the site still drew data
    going back. One arrow, from the site to the browser; the browser keeps yours."""
    page = (site / "index.html").read_text(encoding="utf-8")
    flow = page[page.index('class="lp-pic lp-flow"'):]
    flow = flow[:flow.index("</section>")]
    assert "lp-flow__back" not in flow and "lp-flow__cross" not in flow
    assert flow.count('class="lp-flow__head') == 1
    assert "kept here" in _flat(flow)


def test_the_about_section_dates_the_holdings(site: Path) -> None:
    """UI/UX critique H-07: "fund portfolios, monthly" said nothing of how old they
    are. The date most of them were disclosed for is given, and each fund's page has
    its own."""
    page = _flat((site / "index.html").read_text(encoding="utf-8"))
    about = page[page.index("Where every figure comes from"):]
    dated = r"Fund portfolios Monthly; most disclosed for \d{2} \w{3} \d{4}"
    assert re.search(dated, about)
    assert "Benchmark comparisons and your own ledger" not in about


def test_an_empty_compare_offers_somewhere_to_start(site: Path) -> None:
    """UI/UX critique C-02: four sections each said "Shown once two funds are
    chosen". With no fund chosen they are hidden, and one panel offers comparisons
    to start from (compare.js `starters`)."""
    page = (site / "compare" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<div class="card cmp__start" data-out="start" hidden>', page)
    assert page.count("data-cmp-section") == 4
    script = (STATIC_DIR / "compare.js").read_text(encoding="utf-8")
    assert "Shown once two funds are chosen" not in script
    assert "starters(Array.from(FUNDS.values()))" in script


def test_overlap_figures_are_tinted_by_their_size() -> None:
    """C-05: the overlap grid's figures were plain numbers. Each sits on a tint as
    strong as it is large (Kit.heat), the same fund against itself in grey; the
    figure stays written, so the tint is never the only way to read it."""
    kit = (STATIC_DIR / "kit.js").read_text(encoding="utf-8")
    assert "function heat(" in kit and "heat: heat" in kit
    for name in ("compare.js", "portfolio.js"):
        script = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert "K.heat(" in script and "heat--self" in script, name


def test_the_zoom_slider_is_big_enough_or_absent() -> None:
    """C-08: the slider's handles were about 8px wide. On a wide screen it is 24px
    tall with handles to match; on a phone the period buttons do its job."""
    charts = (STATIC_DIR / "charts.js").read_text(encoding="utf-8")
    assert 'type: "slider", height: 24' in charts and 'handleSize: "120%"' in charts
    assert "show: !phone()" in charts


def test_the_sip_page_is_published_and_linked(site: Path) -> None:
    """SPEC_SIP_WHAT_IF §4.1, §4.8: /sip/ is built, its script published, listed in
    search, and in the top bar between Compare and Your portfolio and in the footer."""
    page = (site / "sip" / "index.html").read_text(encoding="utf-8")
    assert "sip.js" in publish.STATIC_FILES and (site / "static" / "sip.js").is_file()
    assert f'<script src="{BASE}/static/sip.js" defer></script>' in page
    found = json.loads((site / "search.json").read_text(encoding="utf-8"))
    assert {"name": "What would a SIP have become?", "detail": "Page",
            "url": f"{BASE}/sip/"} in found
    nav = page[page.index('<nav class="topnav"'):page.index("</nav>")]
    hrefs = re.findall(r'href="([^"]+)"', nav)
    at = hrefs.index(f"{BASE}/sip/")
    assert hrefs[at - 1] == f"{BASE}/compare/" and hrefs[at + 1] == f"{BASE}/portfolio/"
    assert 'aria-current="page">What if</a>' in re.sub(r"\s+", " ", nav)
    foot = page[page.index('class="colophon__columns"'):]
    assert f'href="{BASE}/sip/"' in foot[:foot.index("</nav>")]


def test_the_sip_page_offers_the_ranked_kinds_by_family(site: Path) -> None:
    """§4.2: one <optgroup> a family, in the site's order; only ranked kinds, each
    with its count of Direct funds here and SEBI's one line on it."""
    page = (site / "sip" / "index.html").read_text(encoding="utf-8")
    select = re.search(r'<select id="sip-kind"[^>]*>(.*?)</select>', page, re.S)
    assert select
    groups = re.findall(r'<optgroup label="([^"]+)">', select.group(1))
    assert groups == ["Equity"]
    option = re.search(r'<option value="equity/flexi_cap" data-about="([^"]+)"[^>]*>'
                       r"Flexi cap \(2\)</option>", select.group(1))
    assert option and "65%" in option.group(1)


def test_the_sip_page_fetches_its_opening_kinds_prices_while_it_loads(site: Path) -> None:
    """§4.10: the page opens on large cap, or the first kind where there is none (as
    here); that kind's Direct NAV files are preloaded, and no other fund's."""
    page = (site / "sip" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<option value="equity/flexi_cap"[^>]* selected>', page)
    rows = json.loads((site / "funds.json").read_text(encoding="utf-8"))
    codes = sorted(r["amfi"] for r in rows
                   if r["category"] == "equity/flexi_cap" and r.get("plan") != "regular")
    link = (rf'<link rel="preload" href="{BASE}/data/nav/(\w+)\.csv\.gz"'
            r' as="fetch" crossorigin>')
    preloaded = sorted(re.findall(link, page))
    assert codes and preloaded == codes
    assert all((site / "data" / "nav" / f"{c}.csv.gz").is_file() for c in codes)


def test_the_build_writes_the_overview_of_kinds(site: Path) -> None:
    """§5.1.2: data/sip/kinds.json, one entry a kind /sip/ offers, each standard
    window for ₹1,000 a month and ₹1,00,000 once; two flexi cap funds here, so no
    window is a range."""
    found = json.loads((site / "data" / "sip" / "kinds.json").read_text(encoding="utf-8"))
    assert found["version"] == 1 and found["day"] == 5
    assert found["unit"] == {"sip": "1000.00", "once": "100000.00"}
    assert found["valued_on"]
    page = (site / "sip" / "index.html").read_text(encoding="utf-8")
    offered = re.findall(r'<option value="([^"]+)" data-about=', page)
    assert [k["category"] for k in found["kinds"]] == offered == ["equity/flexi_cap"]
    flexi = found["kinds"][0]
    assert (flexi["name"], flexi["family"], flexi["funds"]) == ("Flexi cap", "equity", 2)
    assert "65%" in flexi["about"]
    assert set(flexi["sip"]) == set(flexi["once"]) == {"1", "3", "5", "10"}
    assert all(w is None for mode in ("sip", "once") for w in flexi[mode].values())


def test_the_overview_reads_prices_as_the_page_does() -> None:
    """The NAV file's rows (raw, never a filled-in day), put on one scale where the
    fund re-denominated its units, as portfolio-math.js's parseNavFile does: so a
    kind's figure in kinds.json is the page's at the same amount."""
    class Market:
        def nav_series(self, sid: SchemeId, start: date, end: date,
                       adjusted: bool = True) -> list[NavPoint]:
            assert not adjusted and end == date(2026, 9, 26)
            rows = [("2018-11-01", "10.0034", False), ("2018-11-02", "505", True),
                    ("2018-11-04", "1000.6884", False)]
            return [NavPoint(sid, date.fromisoformat(d), Decimal(v), filled)
                    for d, v, filled in rows]

    got = publish.site_prices(Market(), "INF209KB1ZH2", date(2026, 9, 26))
    assert got is not None
    assert got.dates == [date(2018, 11, 1), date(2018, 11, 4)]
    assert got.navs == [Decimal("1000.34"), Decimal("1000.6884")]


def test_the_sip_page_always_carries_its_notes(site: Path) -> None:
    """§4.6.5: four notes, never folded."""
    page = _flat((site / "sip" / "index.html").read_text(encoding="utf-8"))
    for note in ("Direct plans, growth option, at their published prices.",
                 "Only funds open today are here.",
                 "A Regular plan of the same fund has a higher expense ratio",
                 "This looks back. It says nothing of what comes next."):
        assert note in page, note


def test_start_here_leads_learn_and_on_to_each_fuller_guide(site: Path) -> None:
    """SPEC_SIP_WHAT_IF §5.3: the newcomer's guide is Learn's first, each of its
    points links on to the guide that says more, and it ends at /sip/."""
    index = (site / "learn" / "index.html").read_text(encoding="utf-8")
    slugs = re.findall(rf'href="{BASE}/learn/([a-z-]+)/"', index)
    assert slugs and slugs[0] == "start-here"
    page = (site / "learn" / "start-here" / "index.html").read_text(encoding="utf-8")
    assert "New to mutual funds? Start here" in page
    for slug, title in (("what-a-mutual-fund-is", "What a mutual fund is"),
                        ("equity-debt-and-hybrid", None), ("sip-and-lump-sum", None)):
        link = re.search(rf'<p class="learn__next"><a href="{BASE}/learn/{slug}/">'
                         r"More: ([^<]+) →</a></p>", page)
        assert link and (title is None or link.group(1) == title), slug
    assert f'<a href="{BASE}/sip/">Try it with real funds →</a>' in page


def test_every_way_into_the_sip_page(site: Path) -> None:
    """SPEC_SIP_WHAT_IF §4.8: from a fund page (its kind and itself filled in),
    Compare, Your portfolio when empty, and the SIP guide."""
    fund = _page(site, DIRECT)
    growth = fund[fund.index('data-view-id="fund_growth"'):]
    growth = growth[:growth.index("</section>")]
    assert (f'href="{BASE}/sip/#c=equity/flexi_cap&amp;f={DIRECT}">'
            "Your own amount, as a SIP or once →</a>") in growth
    guide = (site / "learn" / "sip-and-lump-sum" / "index.html").read_text(
        encoding="utf-8")
    assert f'<a href="{BASE}/sip/">Try it with real funds →</a>' in guide
    for name, text in (
            ("compare.js", "The same funds as a monthly SIP →"),
            ("portfolio.js", "Holding no funds yet? See what a SIP would have become →")):
        script = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert text in script and 'BASE + "/sip/' in script, name
