"""The public fund explorer: `jobs/publish_site.py`. DECISIONS V1-72.

A public website built from the same warehouse as the private app, so every
test here is about what must NOT reach it -- index levels, the portfolio --
what must reach it only marked (an aggregator's holdings), and about the links
still working from the subdirectory GitHub Pages serves a project site under.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import jobs.publish_site as publish
import pytest
from src.common.decimals import connect
from src.common.types import IndexId, SchemeId
from src.m0_data.categories import category_of
from src.m6_views.api.pages import templates
from src.m6_views.builders.fund.common import INDEX_WITHHELD
from src.m6_views.format import format_date

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
    # The benchmark column is there and empty.
    assert all(line.endswith(",") for line in growth.splitlines()[-3:])


def test_funds_json_lists_every_published_fund_for_the_portfolio_page(site: Path) -> None:
    funds = json.loads((site / "funds.json").read_text(encoding="utf-8"))
    assert {f["id"] for f in funds} == {DIRECT, AGGREGATED}
    one = next(f for f in funds if f["id"] == DIRECT)
    assert set(one) == {"id", "amfi", "name", "category", "category_name",
                        "prices_from", "ter", "size", "r1", "r3", "r5",
                        "vol3", "fall3",
                        # for the compare page (V1-85)
                        "house", "benchmark", "sharpe3", "rank3", "labels"}
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
    assert "<table data-sortable data-filterable>" in index
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
    assert row.group(1).count("—") == 6


PRIVACY = (
    "Nothing you enter leaves your browser",
    "Your portfolio and your settings are kept in this browser's own storage, on this"
    " device. Nothing you enter is sent anywhere or kept on any server. You can clear"
    " them at any time: Clear on Your portfolio, Reset to defaults in Settings.",
    "No accounts, no cookies, no analytics.",
    "The page loads nothing from any other site: its content security policy allows"
    " only this one.",
    "Like any web host, GitHub Pages keeps ordinary request logs (the address and the"
    " page asked for), never what you type into a page.",
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
    assert re.search(r"<h1[^>]*>\s*See what every fund owns, and how it has done", index)
    assert re.search(r'<a[^>]*href="#privacy"[^>]*>[^<]*Nothing you enter leaves your'
                     r' browser', index)
    hero = index[index.index('class="lp-hero"'):index.index('id="lookup"')]
    assert hero.count('class="lp-door"') == 3
    assert 'data-index="/Repo/search.json"' in hero
    assert 'href="/Repo/learn/"' in hero and 'href="/Repo/portfolio/"' in hero
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
    assert "An example: the largest flexi cap fund by size." in text
    assert "Fund One Flexi Cap within its category, Flexi cap" in text
    for n in range(1, 6):
        assert f"Company {n}" in text
    for period in ("1 year", "3 years", "5 years"):
        assert period in text
    assert "2 companies in both" in text and "7.0%" in text
    assert "of the two portfolios is the same" in text
    assert 'width="57.89"' in page  # the fill runs to the fund's position
    none = _flat(_home(EXAMPLE, {**PAIR, "common": 0, "lead": None}))
    assert "No companies in both" in none and "0 companies" not in none
    alone = _flat(_home(EXAMPLE, None))
    assert "No example tonight" in alone


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
        "categories": [], "category_options": [], "count": 0, "funds": [],
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
    assert [x.strip() for x in links] == ["Explore funds", "Compare", "Your portfolio",
                                         "Learn", "Categories", "About the data"]
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
    category = re.search(r"<dt>Category.*?</dt><dd>([^<]+)</dd>", page, re.S)
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
    assert card.count("errorSlot()") == 2 and 'err && el("p"' not in card
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
        "categories": [], "category_options": [], "count": 0, "funds": [],
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
