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
