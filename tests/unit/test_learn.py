"""The learn content's checks (DECISIONS V1-87).

Each test breaks one rule in an otherwise valid document and expects `load` to
refuse it. What these do not prove: that an explanation is true. Only reading
it against its source does, which is why the content is reviewed before release.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from src.m6_views.learn import LEARN_YAML, Learn, LearnError, link_terms, load, stale

TODAY = date(2026, 10, 2)
AMFI = "https://www.amfiindia.com/investor-corner/knowledge-center/net-asset-value.html"


def _ref(url: str = AMFI, checked: Any = date(2026, 10, 1)) -> dict[str, Any]:
    return {"source": "amfi", "url": url, "checked": checked}


def _term(**over: Any) -> dict[str, Any]:
    term = {"title": "NAV", "short": "The price of one unit of a fund.",
            "sources": [_ref()], "related": []}
    term.update(over)
    return term


def _guide(**over: Any) -> dict[str, Any]:
    guide = {
        "slug": "what-a-mutual-fund-is", "title": "What a mutual fund is",
        "group": "Basics", "summary": "Pooling money to buy many things at once.",
        "sections": [{"heading": f"Part {n}",
                      "paragraphs": ["Units are priced at [[nav]]."]} for n in range(4)],
        "sources": [_ref()],
    }
    guide.update(over)
    return guide


def _write(tmp_path: Path, terms: dict[str, Any] | None = None,
           guides: list[dict[str, Any]] | None = None) -> Path:
    sources = yaml.safe_load(LEARN_YAML.read_text(encoding="utf-8"))["sources"]
    doc = {"sources": sources, "terms": terms if terms is not None else {"nav": _term()},
           "guides": guides if guides is not None else []}
    path = tmp_path / "learn.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def _refused(path: Path, *needles: str) -> None:
    with pytest.raises(LearnError) as err:
        load(path, today=TODAY)
    for needle in needles:
        assert needle in str(err.value), str(err.value)


def test_the_real_file_loads() -> None:
    assert isinstance(load(), Learn)


def test_a_valid_document_loads(tmp_path: Path) -> None:
    learn = load(_write(tmp_path, guides=[_guide()]), today=TODAY)
    assert learn.terms["nav"].title == "NAV"
    assert learn.guide("what-a-mutual-fund-is").group == "Basics"


def test_a_host_outside_the_allowlist_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"nav": _term(sources=[_ref("https://example.com/nav")])})
    _refused(path, "nav", "example.com")


def test_plain_http_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"nav": _term(sources=[_ref(AMFI.replace("https", "http"))])})
    _refused(path, "nav")


def test_zerodha_outside_varsity_is_refused(tmp_path: Path) -> None:
    ref = {"source": "zerodha", "url": "https://zerodha.com/z-connect/x",
           "checked": date(2026, 10, 1)}
    _refused(_write(tmp_path, {"nav": _term(sources=[ref])}), "nav")


def test_a_ref_naming_an_unknown_source_is_refused(tmp_path: Path) -> None:
    ref = {"source": "nse", "url": "https://www.nseindia.com/x",
           "checked": date(2026, 10, 1)}
    _refused(_write(tmp_path, {"nav": _term(sources=[ref])}), "nav", "nse")


def test_a_future_checked_date_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, {"nav": _term(sources=[_ref(checked=date(2026, 10, 4))])})
    _refused(path, "nav")


def test_a_checked_value_that_is_not_a_date_is_refused(tmp_path: Path) -> None:
    _refused(_write(tmp_path, {"nav": _term(sources=[_ref(checked="last week")])}), "nav")


def test_a_term_needs_a_source(tmp_path: Path) -> None:
    _refused(_write(tmp_path, {"nav": _term(sources=[])}), "nav")


def test_an_overlong_explanation_is_refused(tmp_path: Path) -> None:
    _refused(_write(tmp_path, {"nav": _term(short=" ".join(["word"] * 61))}), "nav")


def test_an_unknown_term_link_is_refused(tmp_path: Path) -> None:
    guide = _guide(sections=[{"heading": "H", "paragraphs": ["See [[nope]]."]}] * 4)
    _refused(_write(tmp_path, guides=[guide]), "nope")


def test_an_unknown_related_term_is_refused(tmp_path: Path) -> None:
    _refused(_write(tmp_path, {"nav": _term(related=["nope"])}), "nope")


def test_a_percentage_in_the_tax_guide_is_refused(tmp_path: Path) -> None:
    sections = [{"heading": "H",
                 "paragraphs": ["Long-term gains are taxed at 12.5%."]}] * 4
    guide = _guide(slug="how-gains-are-taxed", group="Your portfolio", sections=sections)
    _refused(_write(tmp_path, guides=[guide]), "how-gains-are-taxed")


def test_per_cent_in_words_in_the_tax_guide_is_refused(tmp_path: Path) -> None:
    sections = [{"heading": "H", "paragraphs": ["Ten per cent of the gain."]}] * 4
    guide = _guide(slug="how-gains-are-taxed", group="Your portfolio", sections=sections)
    _refused(_write(tmp_path, guides=[guide]), "how-gains-are-taxed")


def test_an_unknown_group_is_refused(tmp_path: Path) -> None:
    _refused(_write(tmp_path, guides=[_guide(group="Advanced")]), "Advanced")


def test_a_guide_needs_four_to_six_sections(tmp_path: Path) -> None:
    three = _guide(sections=_guide()["sections"][:3])
    _refused(_write(tmp_path, guides=[three]), "what-a-mutual-fund-is")


def test_an_overlong_paragraph_is_refused(tmp_path: Path) -> None:
    sections = [{"heading": "H", "paragraphs": [" ".join(["word"] * 121)]}] * 4
    path = _write(tmp_path, guides=[_guide(sections=sections)])
    _refused(path, "what-a-mutual-fund-is")


def test_duplicate_guide_slugs_are_refused(tmp_path: Path) -> None:
    _refused(_write(tmp_path, guides=[_guide(), _guide()]), "what-a-mutual-fund-is")


def test_link_terms_escapes_the_text_around_links(tmp_path: Path) -> None:
    learn = load(_write(tmp_path), today=TODAY)
    out = link_terms("a < b [[nav]] & c [[nav|the price]]", learn, "/R")
    assert str(out) == (
        'a &lt; b <a href="/R/learn/glossary/#nav">NAV</a> &amp; c '
        '<a href="/R/learn/glossary/#nav">the price</a>'
    )


def test_stale_lists_old_checks(tmp_path: Path) -> None:
    old = _term(sources=[_ref(checked=date(2025, 9, 1))])
    learn = load(_write(tmp_path, {"nav": old}), today=TODAY)
    lines = stale(learn, TODAY)
    assert len(lines) == 1 and AMFI in lines[0] and "nav" in lines[0]
    assert stale(load(_write(tmp_path), today=TODAY), TODAY) == []


TERMS = {
    "nav", "units", "amc", "direct_plan", "regular_plan", "growth_idcw", "lump_sum",
    "sip", "exit_load", "stamp_duty",
    "expense_ratio", "aum", "annualised_return", "xirr", "volatility", "max_drawdown",
    "sharpe", "rolling_returns", "category_rank", "benchmark", "index_fund",
    "sebi_categories", "asset_mix", "sectors", "market_cap", "portfolio_disclosure",
    "look_through", "overlap",
}
GUIDES = [
    ("start-here", "Basics"),
    ("what-a-mutual-fund-is", "Basics"), ("equity-debt-and-hybrid", "Basics"),
    ("how-funds-are-grouped", "Basics"), ("direct-and-regular-plans", "Costs"),
    ("what-a-fund-costs", "Costs"), ("risk-and-return", "Risk and return"),
    ("index-and-active-funds", "Risk and return"), ("sip-and-lump-sum", "Your portfolio"),
    ("how-gains-are-taxed", "Your portfolio"),
    ("look-through-and-overlap", "Your portfolio"),
    ("reading-a-fund-page", "Using this site"),
]
#: Entries that state an Indian rule cite the body that sets it.
RULES = {"direct_plan", "regular_plan", "sebi_categories", "market_cap", "expense_ratio",
         "portfolio_disclosure", "how-funds-are-grouped", "direct-and-regular-plans",
         "what-a-fund-costs", "exit_load", "stamp_duty"}


def test_the_content_covers_the_spec() -> None:
    learn = load()
    assert set(learn.terms) == TERMS
    assert [(g.slug, g.group) for g in learn.guides] == GUIDES
    entries = {**{k: t.sources for k, t in learn.terms.items()},
               **{g.slug: g.sources for g in learn.guides}}
    for key in RULES:
        assert {r.source for r in entries[key]} & {"sebi", "amfi"}, key


def test_a_check_dated_tomorrow_is_allowed(tmp_path: Path) -> None:
    """The nightly build runs at 02:00 in India but its clock says the day
    before (UTC), so content checked and dated in India after midnight must not
    fail that night's build. Two days ahead is still refused."""
    tomorrow = _write(tmp_path, {"nav": _term(sources=[_ref(checked=date(2026, 10, 3))])})
    assert load(tomorrow, today=TODAY).terms["nav"]
    later = _write(tmp_path, {"nav": _term(sources=[_ref(checked=date(2026, 10, 4))])})
    _refused(later, "nav")


def _text(key: str) -> str:
    learn = load()
    if key in learn.terms:
        return learn.terms[key].short
    guide = learn.guide(key)
    return " ".join([guide.summary] + [p for s in guide.sections for p in s.paragraphs])


def test_the_reviewed_statements_say_what_their_sources_say() -> None:
    """Corrections from the content review (V1-87): each wrong or overstated
    sentence, and what replaced it."""
    nav = _text("what-a-mutual-fund-is")
    assert "with the money for a purchase already with the fund" in nav
    assert "Liquid and overnight funds follow their own timings" in nav
    tax = _text("how-gains-are-taxed")
    assert "bought since April 2023, every gain counts as short-term" in tax
    assert "dated by financial year" in tax
    for key in ("sharpe", "risk-and-return"):
        assert "interest-rate risk" not in _text(key), key
        assert "default" in _text(key), key
    costs = _text("what-a-fund-costs")
    assert "nothing is charged on buying" not in costs and "transaction charge" in costs
    assert "three years of daily prices" not in _text("volatility")
    assert "before it climbed back" not in _text("max_drawdown")
    assert "a day after the last" not in _text("rolling_returns")
    assert "hold only government securities" not in _text("equity-debt-and-hybrid")
    index = _text("index-and-active-funds")
    assert "is often called alpha" not in index and "beyond what its beta" in index


def test_the_sip_spec_entries_say_what_their_sources_say() -> None:
    """SPEC_SIP_WHAT_IF §5.3. Stamp duty's rate is printed because the page cited
    states it (SEBI's FAQ on the Stamp Act: 0.005% on issue, ₹500 on ₹1 crore);
    exit load's period and rate are each fund's own, in its scheme documents."""
    stamp = _text("stamp_duty")
    assert "1 July 2020" in stamp and "0.005%" in stamp and "₹500 on ₹1 crore" in stamp
    assert "not on redemptions" in stamp
    assert any("1639980911330.pdf" in r.url for r in load().terms["stamp_duty"].sources)
    load_ = _text("exit_load")
    assert "scheme information document" in load_ and "set period" in load_
    start = _text("start-here")
    assert "wound up" in start and "this site's included" in start


def test_a_section_may_point_to_a_guide_that_exists(tmp_path: Path) -> None:
    """"Start here" leads to the fuller guide on each point (§5.3): a section's
    `guide` names one, or the file is refused."""
    other = _guide(slug="other")
    first = _guide(sections=[{**_guide()["sections"][0], "guide": "other"},
                             *_guide()["sections"][1:]])
    learn = load(_write(tmp_path, guides=[first, other]), today=TODAY)
    assert learn.guide("what-a-mutual-fund-is").sections[0].guide == "other"
    assert learn.guide("what-a-mutual-fund-is").sections[1].guide is None
    _refused(_write(tmp_path, guides=[first]), "what-a-mutual-fund-is", "other")


def _with_figure(figure: dict[str, Any]) -> dict[str, Any]:
    sections = _guide()["sections"]
    return _guide(sections=[{**sections[0], "figure": figure}, *sections[1:]])


def test_a_guide_figure_is_a_png_with_its_numbers_said(tmp_path: Path) -> None:
    """UI/UX critique L-03: a guide may show the page it describes, as a screenshot
    in static/learn/ with numbered marks, each number's meaning in words; its size
    is read from the file, so the page reserves its room."""
    figure = {"src": "learn/fund-header.png", "alt": "A fund page's header, numbered.",
              "callouts": ["The fund's name.", "Its latest NAV."]}
    learn = load(_write(tmp_path, guides=[_with_figure(figure)]), today=TODAY)
    shot = learn.guides[0].sections[0].figure
    assert shot is not None and shot.callouts == ("The fund's name.", "Its latest NAV.")
    assert shot.width > 0 and shot.height > 0
    for bad in ({**figure, "src": "fonts/rubik.png"}, {**figure, "src": "learn/none.png"},
                {**figure, "alt": ""}, {**figure, "callouts": []}):
        _refused(_write(tmp_path, guides=[_with_figure(bad)]), "what-a-mutual-fund-is")


def test_a_guide_names_the_terms_it_links_to_once_each() -> None:
    """L-04: the guide's glossary terms, listed at its end, in the order first linked."""
    guide = load().guide("reading-a-fund-page")
    assert guide.terms[:3] == ("nav", "annualised_return", "benchmark")
    assert len(guide.terms) == len(set(guide.terms))
