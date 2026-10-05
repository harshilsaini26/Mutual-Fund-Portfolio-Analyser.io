"""A fund's share preview (`jobs.share_image`). UI/UX critique G-11, 2026-10-04.

A link to a fund page shared on WhatsApp or Twitter showed nothing. Each fund page
gets a 1200x630 picture: its name, its category, its three-year return and rank,
and a line of its price. Drawn at build time with Pillow; small enough to make for
every fund every night.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from jobs.share_image import CARD_SIZE, fund_card, site_card
from PIL import Image

LONG = ("Aditya Birla Sun Life CRISIL-IBX Gilt Index Fund - April 2029 Plan "
        "with a name long enough to need cutting")


def test_a_fund_card_is_a_small_wide_picture(tmp_path: Path) -> None:
    out = tmp_path / "share.png"
    fund_card(out, "HDFC Flexi Cap Fund", "Flexi cap · Direct · Growth",
              "+15.4% a year over 3 years", "10th of 37 in its category",
              [Decimal(100 + i % 7 + i // 3) for i in range(160)])
    with Image.open(out) as img:
        assert img.size == CARD_SIZE == (1200, 630)
    assert out.stat().st_size < 60_000


def test_a_card_copes_with_a_long_name_and_no_figures(tmp_path: Path) -> None:
    out = tmp_path / "share.png"
    fund_card(out, LONG, "Index funds · Direct · Growth", None, None, [])
    with Image.open(out) as img:
        assert img.size == CARD_SIZE


def test_the_site_card(tmp_path: Path) -> None:
    out = tmp_path / "share.png"
    site_card(out, 1662)
    with Image.open(out) as img:
        assert img.size == CARD_SIZE
