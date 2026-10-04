"""A fund's name as the site shows it (`universe.display_name`).

Design review, 2026-10-04: AMFI writes some funds' names in capitals ("BANDHAN
LARGE CAP FUND" beside "Bandhan Flexi Cap Fund"). Display only: matching and the
warehouse keep AMFI's own spelling.
"""

from __future__ import annotations

import pytest
from src.m0_data.universe import display_name


@pytest.mark.parametrize(("amfi", "shown"), [
    ("BANDHAN LARGE CAP FUND", "Bandhan Large Cap Fund"),
    ("BANK OF INDIA FLEXI CAP FUND", "Bank of India Flexi Cap Fund"),
    ("ANGEL ONE NIFTY 50 INDEX FUND", "Angel One Nifty 50 Index Fund"),
    ("HDFC ELSS TAX SAVER", "HDFC ELSS Tax Saver"),
    ("ICICI PRUDENTIAL NIFTY IT ETF", "ICICI Prudential Nifty IT ETF"),
    ("SBI CPSE BOND PLUS SDL SEP 2026 50:50 INDEX FUND",
     "SBI CPSE Bond Plus SDL Sep 2026 50:50 Index Fund"),
    ("AXIS GOLD FOF", "Axis Gold FoF"),
])
def test_a_name_in_capitals_is_shown_in_ordinary_ones(amfi: str, shown: str) -> None:
    assert display_name(amfi) == shown


def test_a_name_already_in_mixed_case_is_left_alone() -> None:
    for name in ("360 ONE Balanced Hybrid Fund", "Parag Parikh Flexi Cap Fund",
                 "Aditya Birla Sun Life CRISIL-IBX Gilt Index Fund"):
        assert display_name(name) == name
