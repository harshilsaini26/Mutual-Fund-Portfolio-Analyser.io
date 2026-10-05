"""The explanations in place on the pages (DECISIONS V1-87).

A `?` beside a term opens a native popover holding the term's explanation, so it
works with scripts off; each id is unique on its page.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from src.m6_views.learn import TERMS_FOR, load

from tests.unit.test_m6_render import QS, client  # noqa: F401  (fixture)
from tests.unit.test_publish_site import (  # noqa: F401  (fixtures)
    DIRECT,
    _page,
    site,
    warehouse,
)


def test_a_fund_page_explains_its_header_terms(site: Path) -> None:  # noqa: F811
    html = _page(site, DIRECT)
    assert 'popovertarget="t-expense_ratio-ter"' in html
    assert 'id="t-expense_ratio-ter"' in html
    assert 'popovertarget="t-annualised_return-return_1y"' in html
    assert 'id="t-annualised_return-return_1y"' in html
    assert "More in the glossary" in html


def test_term_popover_ids_are_unique_on_a_fund_page(site: Path) -> None:  # noqa: F811
    ids = re.findall(r'id="(t-[^"]+)"', _page(site, DIRECT))
    assert ids and len(ids) == len(set(ids))


def test_terms_work_without_scripts(site: Path) -> None:  # noqa: F811
    html = _page(site, DIRECT)
    targets = set(re.findall(r'popovertarget="([^"]+)"', html))
    popovers = set(re.findall(r'id="([^"]+)" popover\b', html))
    assert targets and targets <= popovers


def test_a_term_in_a_sortable_header_is_not_a_sort_button(site: Path) -> None:  # noqa: F811
    html = (site / "funds" / "index.html").read_text(encoding="utf-8")
    terms = re.findall(r'<button[^>]*class="term"[^>]*>', html)
    assert terms and not any("data-sort" in tag for tag in terms)


def test_the_compare_page_carries_its_terms(site: Path) -> None:  # noqa: F811
    html = (site / "compare" / "index.html").read_text(encoding="utf-8")
    assert 'id="t-expense_ratio-cmp"' in html and 'id="t-overlap-cmp"' in html


def test_the_portfolio_page_carries_its_terms(site: Path) -> None:  # noqa: F811
    html = (site / "portfolio" / "index.html").read_text(encoding="utf-8")
    assert 'id="t-xirr-pf"' in html and 'id="t-look_through-pf"' in html


def test_every_mapped_term_exists() -> None:
    terms = load().terms
    for kind, mapping in TERMS_FOR.items():
        for key in mapping.values():
            assert key in terms, (kind, key)


def test_the_local_fund_page_explains_its_terms(client: TestClient) -> None:  # noqa: F811
    assert 'class="term"' in client.get(f"/fund/S1{QS}").text


def test_the_benchmark_fact_is_explained() -> None:
    """The header's Benchmark fact (builders/fund/header.py) gets its `?`."""
    assert TERMS_FOR["fact"]["Benchmark"] == "benchmark"


def _guide_page(site: Path) -> str:  # noqa: F811
    guide = site / "learn" / "reading-a-fund-page" / "index.html"
    return guide.read_text(encoding="utf-8")


def test_a_guide_has_contents_neighbours_and_its_terms(site: Path) -> None:  # noqa: F811
    """UI/UX critique L-04: no table of contents, no previous or next, no list of the
    terms it uses. Each guide opens with its sections as links, ends with the guides
    before and after it, and lists the glossary terms it links to."""
    learn = load()
    slugs = [g.slug for g in learn.guides]
    at = slugs.index("reading-a-fund-page")
    page = _guide_page(site)
    toc = re.search(r'<nav class="learn__toc" aria-labelledby="toc-h">(.*?)</nav>',
                    page, re.S)
    assert toc
    for section in learn.guide("reading-a-fund-page").sections:
        assert f">{section.heading}</a>" in toc.group(1), section.heading
    pager = re.search(r'<nav class="learn__pager" aria-label="More guides">(.*?)</nav>',
                      page, re.S)
    assert pager
    if at > 0:
        assert f"/learn/{slugs[at - 1]}/" in pager.group(1)
    if at < len(slugs) - 1:
        assert f"/learn/{slugs[at + 1]}/" in pager.group(1)
    related = re.search(r'<ul class="learn__related">(.*?)</ul>', page, re.S)
    assert related and "/learn/glossary/#nav" in related.group(1)


def test_the_fund_page_guide_shows_the_page_it_describes(site: Path) -> None:  # noqa: F811
    """L-03: a guide to a visual page had no picture of it. Its sections carry
    screenshots with numbered marks, and a list says what each number points at."""
    page = _guide_page(site)
    shots = re.findall(r'<figure class="learn__shot">(.*?)</figure>', page, re.S)
    assert len(shots) >= 2
    for shot in shots:
        img = re.search(r'<img src="([^"]+)" alt="([^"]+)" width="\d+" height="\d+"',
                        shot)
        assert img and img.group(2), shot[:200]
        name = img.group(1).rsplit("/static/", 1)[1]
        assert (site / "static" / name).is_file(), name
        assert re.search(r"<ol class=\"learn__callouts\">\s*<li>", shot)
