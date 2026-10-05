"""The fund page, search and the period tabs. DECISIONS V1-70.

Over the same fixture as `test_m6_render.py`: a fund with four years of prices
beside a total-return benchmark, and a loaded portfolio. What is asserted here
is what a reader relies on and would not notice breaking: that a tooltip says
what the export says, that a period tab swaps one panel with its own footer,
and that a hostile name from a downloaded file stays text.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from src.m6_views.format import format_inr
from src.m6_views.registry import FUND_PAGE, SECTION_LABELS

from tests.unit.test_m6_render import QS, client  # noqa: F401  (fixture)


def test_search_finds_a_fund_by_any_word_of_its_name(client: TestClient) -> None:  # noqa: F811
    hits = client.get("/api/search?q=fund one").json()
    assert [h["scheme_id"] for h in hits] == ["S1"]
    assert hits[0]["url"] == "/fund/S1"
    assert client.get("/api/search?q=no such fund").json() == []
    assert client.get("/api/search?q=").json() == []


def test_search_works_without_javascript(client: TestClient) -> None:  # noqa: F811
    html = client.get("/search?q=one").text
    assert 'href="/fund/S1"' in html and "Fund One" in html
    assert 'action="/search"' in html  # the masthead box, on every page


def test_the_fund_page_shows_every_picture_and_loads_echarts_not_d3(
    client: TestClient,  # noqa: F811
) -> None:
    html = client.get(f"/fund/S1{QS}").text
    for view_id in FUND_PAGE:
        assert f'data-view-id="{view_id}"' in html, view_id
    assert '<script src="/static/vendor/echarts.v6.1.0.min.js"></script>' in html
    assert '<script src="/static/charts.js"></script>' in html
    assert "/static/vendor/d3" not in html
    assert "<title>Fund One</title>" in html
    assert client.get("/static/vendor/echarts.v6.1.0.min.js").status_code == 200


def test_a_tooltip_says_what_the_export_says(client: TestClient) -> None:  # noqa: F811
    """§16.4: the label a reader hovers is formatted in Python from the same
    figure the CSV writes, so the two cannot disagree."""
    env = client.get(f"/api/views/fund_growth{QS}&scope_id=S1").json()
    fund = env["payload"]["charts"][0]["series"][0]["points"]
    last_row = env["payload"]["rows"][-1]
    assert fund[-1][0] == last_row["date"]
    assert fund[-1][2] == format_inr(
        Decimal(last_row["fund_value_inr"]), precision=0, compact=False
    )
    assert env["payload"]["headline"].startswith("₹10,000 put into Fund One")


def test_a_period_tab_swaps_one_panel_with_its_own_footer(
    client: TestClient,  # noqa: F811
) -> None:
    page = client.get(f"/fund/S1{QS}").text
    tab = re.search(r'data-fragment="([^"]+window=1y)"', page)
    assert tab, "no period tab on the growth chart"
    fragment = client.get(tab.group(1).replace("&amp;", "&")).text
    assert fragment.count('class="view view--') == 1
    assert 'data-view-id="fund_growth"' in fragment
    assert "Export CSV" in fragment and "About this data" in fragment
    assert "<html" not in fragment
    assert client.get("/fragment/no_such_view").status_code == 404


def test_an_unknown_fund_explains_itself_rather_than_failing(
    client: TestClient,  # noqa: F811
) -> None:
    response = client.get(f"/fund/INF000X01000{QS}")
    assert response.status_code == 200
    assert "Nothing to show yet" in response.text


def _one_fund(tmp_path: Path, holdings: list[tuple[str, str, str, str]]) -> TestClient:
    """An app over one fund, S9, disclosed on 31 Jul 2026 with `holdings`
    as (issuer_id, issuer name, class, share of fund)."""
    from src.common.decimals import connect
    from src.m1_ledger.db import apply_ledger_schema, connect_ledger
    from src.m6_views.api.app import create_app

    from tests.conftest import migrated

    db = str(tmp_path / "w.db")
    migrated(db)
    warehouse = connect(db, check_same_thread=False)
    warehouse.execute(
        "INSERT INTO scheme (scheme_id, scheme_name, plan, option, status)"
        " VALUES ('S9', 'Fund nine', 'direct', 'growth', 'active')"
    )
    warehouse.execute(
        "INSERT INTO raw_file (file_id, source_id, fetched_at, storage_path, byte_size)"
        " VALUES ('f9', 'S5', '2026-08-01', '/x', 0)"
    )
    warehouse.execute(
        "INSERT INTO holding_disclosure (scheme_id, as_of_date, revision,"
        " source_file_id, row_count, unresolved_mv_pct, total_mv,"
        " validation_status, ingested_at, is_current)"
        " VALUES ('S9', '2026-07-31', 1, 'f9', ?, 0, 100, 'ok', '2026-08-01', 1)",
        (len(holdings),),
    )
    for row, (issuer, name, klass, weight) in enumerate(holdings, start=1):
        warehouse.execute(
            "INSERT OR IGNORE INTO issuer (issuer_id, canonical_name, is_listed)"
            " VALUES (?,?,1)",
            (issuer, name),
        )
        warehouse.execute(
            "INSERT INTO holding (scheme_id, as_of_date, revision, row_number,"
            " issuer_id, instrument_raw_name, market_value, pct_normalised,"
            " instrument_class, resolution_method, source_file_id, ingested_at,"
            " is_current) VALUES ('S9', '2026-07-31', 1, ?, ?, 'x', 1, ?, ?,"
            " 'isin', 'f9', '2026-08-01', 1)",
            (row, issuer, Decimal(weight), klass),
        )
    warehouse.commit()
    ledger = connect_ledger(
        str(tmp_path / "l.db"), key="test-key", check_same_thread=False
    )
    apply_ledger_schema(ledger)
    return TestClient(create_app(ledger, warehouse), base_url="http://127.0.0.1:8765")


def test_a_hostile_holding_name_stays_text_on_the_fund_page(tmp_path: Path) -> None:
    """Holding names come from fund houses' files. One written to close the
    chart's JSON block must arrive escaped in the JSON and in the table."""
    app = _one_fund(tmp_path, [("EVIL", HOSTILE, "equity", "100")])
    html = app.get("/fund/S9?as_of=2026-09-04").text
    assert 'data-view-id="fund_portfolio"' in html
    assert HOSTILE not in html
    assert "<script>alert(1)</script>" not in html
    assert "\\u003c/script\\u003e" in html  # escaped inside the JSON block
    assert "&lt;/script&gt;" in html  # escaped in the table


def test_a_fund_owing_more_than_it_is_owed_says_so(tmp_path: Path) -> None:
    """V1-71: V8 no longer warns on negative net current assets, so the page
    says it where a reader looks -- the holdings panel's own sentence."""
    app = _one_fund(tmp_path, [
        ("ACME", "Acme", "equity", "101.5"),
        ("__RECV__", "Net Receivables / Payables", "cash", "-1.5"),
    ])
    env = app.get("/api/views/fund_portfolio?as_of=2026-09-04&scope_id=S9").json()
    assert "net current assets were -1.50%" in env["payload"]["headline"]
    assert "owed more than it was owed" in env["payload"]["headline"]
    assert not any("negative weight" in c for c in env["quality"]["caveats"])


HOSTILE = "Acme</script><script>alert(1)</script>"


def test_performance_sets_each_measure_beside_its_benchmark(
    client: TestClient,  # noqa: F811
) -> None:
    env = client.get(f"/api/views/fund_performance{QS}&scope_id=S1").json()
    assert env["state"] == "ok", env.get("state_reason")
    rows = {r["measure"]: r for r in env["payload"]["rows"]}
    for measure in ("Sharpe ratio", "Treynor ratio", "Alpha a year", "Beta",
                    "Information ratio", "Up capture", "Down capture"):
        assert measure in rows, measure
    three = rows["Return a year"]["3y"], rows["Benchmark a year"]["3y"]
    assert all(v is not None for v in three)
    lead = Decimal(rows["Ahead of benchmark"]["3y"])
    assert lead == Decimal(three[0]) - Decimal(three[1])
    assert rows["Beta"]["3y"] is not None
    html = client.get(f"/fund/S1{QS}").text
    assert "What it says" in html and "Return above cash for each unit of beta." in html


def test_a_capture_ratio_says_how_few_months_it_rests_on(
    client: TestClient,  # noqa: F811
) -> None:
    """External audit, 2026-10-04: a one-year capture ratio rests on about six
    rising and six falling months, and the page should say so."""
    env = client.get(f"/api/views/fund_performance{QS}&scope_id=S1").json()
    rows = {r["measure"]: r for r in env["payload"]["rows"]}
    assert rows["Up capture"]["1y"] is not None
    caveats = env["quality"]["caveats"]
    note = next((c for c in caveats if "capture" in c), "")
    assert re.search(r"Over 1 year .* \d+ rising and \d+ falling months", note), caveats


def test_the_steadiness_claim_counts_only_the_stretches_it_compared(
    client: TestClient,  # noqa: F811
) -> None:
    """External audit, 2026-10-04: say "N of the M stretches", never a rounded
    share -- 200 of 201 read as "100%" -- and say from when, when the benchmark
    covers fewer stretches than the fund."""
    env = client.get(f"/api/views/fund_consistency{QS}&scope_id=S1").json()
    head = env["payload"]["headline"]
    claim = re.search(r"ahead of its benchmark in (\d+) of the (\d+) stretches", head)
    assert claim, head
    assert "%" not in head[claim.start():]
    html = client.get(f"/fund/S1{QS}").text
    assert re.search(r"Ahead of its benchmark in \d+ of \d+ three-year stretches", html)


def test_a_funds_holdings_report_their_coverage(client: TestClient) -> None:  # noqa: F811
    """External audit, 2026-10-04: every envelope showed Coverage "—", the
    holdings one too, where it means something: the share placed."""
    env = client.get(f"/api/views/fund_portfolio{QS}&scope_id=S1").json()
    quality = env["quality"]
    assert quality["coverage_pct"] is not None
    unresolved = Decimal(quality["unresolved_pct"] or 0)
    assert Decimal(quality["coverage_pct"]) == 100 - unresolved


def test_the_ranks_say_what_each_one_counts(client: TestClient) -> None:  # noqa: F811
    """External audit, 2026-10-04: one fund ranked of 40, 36, 27 and 46 on one
    page, unexplained. Each rank counts the funds with that figure."""
    env = client.get(f"/api/views/fund_peers{QS}&scope_id=S1").json()
    assert any("Each counts only the category's funds with that figure" in c
               for c in env["quality"]["caveats"]), env["quality"]["caveats"]


def test_without_a_benchmark_its_rows_are_left_out(
    client: TestClient, tmp_path: Path,  # noqa: F811
) -> None:
    """V1-94: a measure with no figure in any period is not drawn as a row of
    dashes (the note says why), and neither question promises a benchmark."""
    from src.common.decimals import connect

    warehouse = connect(str(tmp_path / "warehouse.db"))
    warehouse.execute("UPDATE scheme SET benchmark_id = NULL WHERE scheme_id = 'S1'")
    warehouse.commit()
    warehouse.close()
    env = client.get(f"/api/views/fund_performance{QS}&scope_id=S1").json()
    measures = {r["measure"] for r in env["payload"]["rows"]}
    assert {"Return a year", "Volatility", "Sharpe ratio"} <= measures
    assert not measures & {"Benchmark a year", "Ahead of benchmark", "Beta", "Up capture"}
    assert env["question"] == "How has it done for the risk taken?"
    caveats = env["quality"]["caveats"]
    assert any("left out" in c for c in caveats), caveats
    returns = client.get(f"/api/views/fund_returns{QS}&scope_id=S1").json()
    assert returns["question"] == "How much has it returned?"


def test_the_worst_fall_names_its_period(client: TestClient) -> None:  # noqa: F811
    """Beside a 3- or 5-year deepest fall, "Worst fall" alone reads as the same
    measure; it is the deepest since the first price, and says so (V1-94)."""
    html = client.get(f"/fund/S1{QS}").text
    assert re.search(r"Worst fall since (19|20)\d\d<", html)


def test_a_return_reads_to_one_place_everywhere(client: TestClient) -> None:  # noqa: F811
    """UI/UX critique G-20 (2026-10-04): the Performance table gave returns to two
    places (15.42%) beside tiles and lists at one (15.4%). One place for returns,
    falls and swings; two for a cost (AMFI's own); three for units."""
    html = client.get(f"/fund/S1{QS}").text
    panel = html[html.index('data-view-id="fund_performance"'):]
    # The table, not the bill rate in the sentence above it.
    panel = panel[panel.index("<table"):panel.index("</table>")]
    assert re.search(r">\s*-?\d+\.\d%\s*<", panel)
    assert not re.search(r"\d\.\d\d%", panel)


def test_a_table_of_unlike_measures_offers_no_sorting(
    client: TestClient,  # noqa: F811
) -> None:
    """UI/UX critique G-18 (2026-10-04): the Performance table showed sort arrows,
    but its rows are different measures -- a return beside a Sharpe ratio -- so
    an order by one column means nothing."""
    html = client.get(f"/fund/S1{QS}").text
    panel = html[html.index('data-view-id="fund_performance"'):]
    panel = panel[:panel.index("</section>")]
    assert "<table" in panel and "data-sortable" not in panel


def assert_tables_are_named_regions(html: str) -> int:
    """Every table that may scroll sideways is a region named by its own caption
    (UI/UX critique G-17): a screen reader hears what the table is, and app.js gives
    a region that overflows a tab stop, so a keyboard can scroll it."""
    wraps = re.findall(
        r'<div class="table-wrap"[^>]*>\s*<table[^>]*>\s*<caption[^>]*>', html)
    assert wraps and len(wraps) == html.count('class="table-wrap"')
    ids = []
    for wrap in wraps:
        region = re.search(r'role="region" aria-labelledby="([^"]+)"', wrap)
        caption = re.search(r'<caption class="sr-only" id="([^"]+)"', wrap)
        assert region and caption and region.group(1) == caption.group(1), wrap
        ids.append(caption.group(1))
    assert len(set(ids)) == len(ids), ids
    for name in re.findall(r"<caption[^>]*>([^<]*)</caption>", html):
        assert name.strip(), "an empty caption names nothing"
    return len(wraps)


def test_every_table_is_a_named_region(client: TestClient) -> None:  # noqa: F811
    assert assert_tables_are_named_regions(client.get(f"/fund/S1{QS}").text) >= 3


def test_rupees_are_written_with_the_rupee_sign(client: TestClient) -> None:  # noqa: F811
    """UI/UX critique G-02 (2026-10-04): one notation, ₹, not "Rs"."""
    html = client.get(f"/fund/S1{QS}").text
    assert "Rs 10,000" not in html and "Growth of ₹10,000" in html


def test_growth_and_price_are_one_chart_with_a_switch(
    client: TestClient,  # noqa: F811
) -> None:
    """Design review, 2026-10-04: "What ₹10,000 became" and "Price history" drew
    the same line twice. One panel holds both, with a switch; its file carries
    the NAV beside the ₹10,000 figure, so nothing the Price section gave is lost."""
    env = client.get(f"/api/views/fund_growth{QS}&scope_id=S1").json()
    payload = env["payload"]
    assert [c["title"] for c in payload["charts"]][1] == "Price per unit (NAV)"
    assert payload["switch"] == ["What ₹10,000 became", "Price per unit"]
    assert "nav" in {c["key"] for c in payload["columns"]}
    assert any(r["nav"] is not None for r in payload["rows"])
    assert "Its NAV was ₹" in payload["headline"]
    html = client.get(f"/fund/S1{QS}").text
    assert 'data-view-id="fund_nav"' not in html
    assert 'data-switch="What ₹10,000 became|Price per unit"' in html
    assert SECTION_LABELS["fund_growth"] == "Growth and price"


def test_the_price_history_is_the_published_nav_from_its_first_day(
    client: TestClient,  # noqa: F811
) -> None:
    env = client.get(f"/api/views/fund_nav{QS}&scope_id=S1").json()
    assert env["state"] == "ok", env.get("state_reason")
    rows = env["payload"]["rows"]
    line = env["payload"]["charts"][0]["series"][0]["points"]
    assert line[0][0] == rows[0]["date"] and line[-1][0] == rows[-1]["date"]
    assert env["payload"]["headline"].startswith("Its NAV was ₹")


def test_every_fund_panel_has_a_section_label() -> None:
    assert set(SECTION_LABELS) == {*FUND_PAGE, "fund_xray_header"}


def test_the_navigator_links_every_section_in_page_order(
    client: TestClient,  # noqa: F811
) -> None:
    html = client.get(f"/fund/S1{QS}").text
    nav = re.search(r'<nav class="sections"[^>]*>(.*?)</nav>', html, re.S)
    assert nav, "no navigator"
    links = re.findall(r'href="#([a-z_]+)"[^>]*>([^<]+)<', nav.group(1))
    assert links == [(v, SECTION_LABELS[v]) for v in (*FUND_PAGE, "fund_xray_header")]
    for view_id, _ in links:
        # `data-view-id="x"` contains `id="x"`; only a whole id attribute counts.
        assert len(re.findall(rf'(?<![\w-])id="{view_id}"', html)) == 1, view_id
    assert "/static/sections.js" in html


def test_a_swapped_panel_brings_no_second_id(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"/fund/S1{QS}").text
    tab = re.search(r'data-fragment="([^"]+window=1y)"', page)
    assert tab
    fragment = client.get(tab.group(1).replace("&amp;", "&")).text
    assert not re.search(r'(?<![\w-])id="fund_growth"', fragment)


def test_performance_reads_on_a_phone(client: TestClient) -> None:  # noqa: F811
    html = client.get(f"/fund/S1{QS}").text
    panel = html[html.index('data-view-id="fund_performance"'):
                 html.index('data-view-id="fund_growth"')]
    assert 'data-label="3 years"' in panel and 'data-label="What it says"' in panel
    tuck = re.search(r'<details class="tuck" open><summary>What each measure says'
                     r'</summary>(.*?)</details>', panel, re.S)
    assert tuck and tuck.group(1).count("<dt>") == 14
    assert "Return above cash for each unit of beta." in tuck.group(1)


def test_the_ranks_list_is_one_tap_away(client: TestClient) -> None:  # noqa: F811
    html = client.get(f"/fund/S1{QS}").text
    tuck = re.search(r'<details class="tuck" open><summary>All ranks \((\d+)\)</summary>'
                     r'\s*<dl class="facts-list facts-list--ranks">', html)
    assert tuck and int(tuck.group(1)) > 0


def test_the_local_app_has_no_compare_link(client: TestClient) -> None:  # noqa: F811
    """`/compare/` exists only on the public site (V1-85)."""
    assert "/compare/" not in client.get(f"/fund/S1{QS}").text


def test_a_fund_without_a_portfolio_says_where_portfolios_come_from(
    client: TestClient,  # noqa: F811
) -> None:
    """Only Kotak and ICICI are fetched; the other three houses' workbooks are
    read from the inbox, so "read directly" told the reader something untrue."""
    env = client.get(f"/api/views/fund_portfolio{QS}&scope_id=NOPORTFOLIO").json()
    reason = env["state_reason"]
    assert "read directly" not in reason
    assert "python -m jobs.fetch_amc" in reason and "data/inbox/" in reason
    assert "python -m jobs.fetch_groww" in reason


def _header(html: str) -> str:
    panel = html[html.index('id="fund_header"'):]
    return panel[:panel.index('id="fund_performance"')]


def test_the_figures_lead_the_fund_page(client: TestClient) -> None:  # noqa: F811
    """UI/UX critique F-01: how the fund has done is why a page is opened, so the
    returns, rank and falls come before the facts, not under them."""
    head = _header(client.get(f"/fund/S1{QS}").text)
    assert head.index('<dl class="tiles">') < head.index('<dl class="facts facts--grid">')


def test_a_return_says_how_far_it_is_from_its_benchmark(
    client: TestClient,  # noqa: F811
) -> None:
    """F-02: "Behind its benchmark, +11.5% p.a." read as the fund's own figure.
    The gap is said in points a year, beside the benchmark's own return."""
    head = re.sub(r"\s+", " ", _header(client.get(f"/fund/S1{QS}").text))
    found = re.search(r"\d+\.\d points a year (ahead of|behind) its benchmark,"
                      r" which returned [+\u2212-]\d+\.\d% a year", head)
    assert found, head[:400]
    assert "Behind its benchmark, " not in head and "Ahead of its benchmark, " not in head


def test_each_fact_is_said_once_and_what_is_not_held_is_said(
    client: TestClient,  # noqa: F811
) -> None:
    """F-04: fund size was a fact and a tile. F-13: the riskometer, manager, exit
    load and minimum SIP are what a reader looks for first; no source this site
    loads carries them, and the page says so rather than leaving them out."""
    head = _header(client.get(f"/fund/S1{QS}").text)
    facts = head[head.index('<dl class="facts facts--grid">'):]
    facts = facts[:facts.index("</dl>")]
    assert "Fund size" not in facts and "Fund size" in head
    for label in ("Riskometer", "Fund manager", "Exit load", "Minimum SIP"):
        row = re.search(
            rf"<dt>{label}</dt>\s*<dd class=\"facts__absent\">([^<]*)</dd>", facts)
        assert row and row.group(1) == "Not in the data this site loads", label


def test_the_peers_picture_names_its_axes_and_its_bubbles(
    client: TestClient,  # noqa: F811
) -> None:
    """UI/UX critique F-08: the y-axis read as untitled and the bubbles' size was
    unexplained. Each axis is named with its unit, the other funds' legend entry
    says what their size shows, and the y name turns to run up its axis."""
    env = client.get(f"/api/views/fund_peers{QS}&scope_id=S1").json()
    chart = env["payload"]["charts"][0]
    assert chart["x_name"] == "Volatility, % a year"
    assert chart["y_name"] == "Return, % a year"
    # Said only where a bubble is sized: the fixture's funds carry no size.
    sized = any(pt[4] for s in chart["series"] for pt in s["points"])
    assert chart["series"][0]["name"].endswith(", sized by fund size") == sized
    charts = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static"
              / "charts.js").read_text(encoding="utf-8")
    scatter = charts[charts.index("scatter: function"):charts.index("hbar: function")]
    assert "nameRotate: where === \"y\" ? 90 : 0" in scatter
    assert "o.grid.top = 56" in scatter and "o.grid.left = 36" in scatter


def test_what_could_not_be_matched_is_a_bar_of_its_own(tmp_path: Path) -> None:
    """UI/UX critique F-10: the largest, darkest tile was "Unresolved Holdings" --
    the part not seen through anchored the picture of what a fund owns. It is a
    grey bar above the tiles now, said in words, and never a tile. F-11: the
    sectors take the full width. F-12: the largest holdings as a table, in the page."""
    app = _one_fund(tmp_path, [
        ("ACME", "Acme", "equity", "55"),
        ("BETA", "Beta", "equity", "35"),
        ("__UNRESOLVED__", "Unresolved Holdings", "unknown", "10"),
    ])
    env = app.get("/api/views/fund_portfolio?as_of=2026-09-04&scope_id=S9").json()
    charts = {c["kind"]: c for c in env["payload"]["charts"]}
    names = [cell["name"] for cell in charts["treemap"]["cells"]]
    assert names == ["Acme", "Beta"]
    assert env["payload"]["unmatched"] == {"value": "10", "label": "10.00%"}
    assert [r["holding"] for r in env["payload"]["top"]] == ["Acme", "Beta"]
    # The tiles' own figures, to the same two places (G-20: one precision a panel).
    assert [r["label"] for r in env["payload"]["top"]] == ["55.00%", "35.00%"]
    html = app.get("/fund/S9?as_of=2026-09-04").text
    panel = html[html.index('data-view-id="fund_portfolio"'):]
    panel = re.sub(r"\s+", " ", panel[:panel.index("</section>")])
    assert re.search(r'<p class="unmatched"><svg class="bar bar--neutral"', panel)
    assert "10.00% of the fund is in holdings not matched to a company" in panel
    assert "<caption" in panel and ">Largest holdings</caption>" in panel
    assert ">55.00%</td>" in panel
