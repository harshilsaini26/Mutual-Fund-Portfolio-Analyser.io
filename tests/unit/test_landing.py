"""The landing page's example fund and example pair (DECISIONS V1-89).

Hand-built rows in the shape `publish_site.explorer_row` returns, so the rule that
picks the example is tested without building a site.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import jobs.publish_site as publish
from jobs.landing import (
    EXAMPLE_CATEGORY,
    FIVE_YEAR,
    landing_candidate,
    landing_example,
    landing_pair,
)
from src.common.types import IssuerId, SchemeId
from src.m3_lookthrough.engine import IssuerWeight
from src.m3_lookthrough.overlap import pairwise_overlap
from src.m6_views.format import format_pct

DASH = "—"
HELD = [["I1", "One Co", "equity", "10"], ["I2", "Two Co", "equity", "5"]]


def _range(label: str) -> dict[str, str]:
    return {"label": label, "low_label": "1.0%", "high_label": "9.0%",
            "value_label": "5.0%", "pos": "50.00"}


def _cand(
    sid: str, category: str = EXAMPLE_CATEGORY, size: str = "100",
    five_year: str = "0.12", ter: str = "0.75%", ranges: int = 3,
    holdings: list[list[str]] | None = None, has_holdings: bool = True,
    mix: list[list[str]] | None = None,
) -> dict[str, Any]:
    returns = [{"value": "0.1"}, {"value": "0.1"}, {"value": five_year}]
    row = {
        "scheme_id": sid, "name": f"Fund {sid}",
        "detail": "Equity Scheme - Flexi Cap Fund · Direct · Growth",
        "family": category.split("/")[0], "category_key": category,
        "category_short": category.split("/")[1].replace("_", " ").capitalize(),
        "size_value": size, "ter_label": ter, "returns": returns,
    }
    held = {
        "as_of": "2026-08-31", "aggregator": False,
        "holdings": HELD if holdings is None else holdings,
        "mix": mix or [["equity", "100"]],
    } if has_holdings else None
    periods = ("1 year", "3 years", "5 years")[:ranges]
    return landing_candidate(row, [_range(p) for p in periods], held)


def test_five_year_is_the_publish_jobs_five_year_column() -> None:
    assert publish.RETURN_WINDOWS[FIVE_YEAR] == "5y"


def test_the_example_is_the_largest_complete_flexi_cap_fund() -> None:
    candidates = [
        _cand("A", size="900", has_holdings=False),
        _cand("B", size="800", five_year=""),
        _cand("X", size="850", ranges=2),
        _cand("Y", size="840", ter=DASH),
        _cand("C", size="700"),
        _cand("D", size="700"),
        _cand("E", category="equity/large_cap", size="990"),
    ]
    example = landing_example(candidates)
    assert example is not None and example["scheme_id"] == "C"


def test_the_example_is_not_a_fund_we_mostly_could_not_identify() -> None:
    """External audit, 2026-10-04: the front page's worked example was PPFAS at
    23% unidentified, the worst of the funds checked closely. A fund at most 5%
    unidentified is preferred over a larger one; failing that, the least."""
    murky = [["__UNRESOLVED__", "Unresolved", "equity", "23"], *HELD]
    clear = [["__UNRESOLVED__", "Unresolved", "equity", "1"], *HELD]
    big = _cand("BIG", size="900", holdings=murky)
    small = _cand("SMALL", size="100", holdings=clear)
    example = landing_example([big, small])
    assert example is not None and example["scheme_id"] == "SMALL"
    worse = _cand("WORSE", size="500",
                  holdings=[["__UNRESOLVED__", "U", "equity", "40"], *HELD])
    example = landing_example([big, worse])
    assert example is not None and example["scheme_id"] == "BIG"


def test_equal_sizes_go_to_the_lower_scheme_id() -> None:
    example = landing_example([_cand("D", size="700"), _cand("C", size="700")])
    assert example is not None and example["scheme_id"] == "C"


def test_size_is_compared_as_a_number_not_text() -> None:
    example = landing_example([_cand("S", size="5000"), _cand("T", size="25000")])
    assert example is not None and example["scheme_id"] == "T"


def test_no_candidate_no_example() -> None:
    assert landing_example([]) is None
    assert landing_example([_cand("A", has_holdings=False), _cand("B", ranges=0)]) is None


def test_the_example_card_clamps_and_shows_what_there_is() -> None:
    holdings = [
        ["I1", "Big Co", "equity", "150"], ["I2", "Short Co", "equity", "-5"],
        ["I3", "Mid Co", "equity", "20"], ["__UNRESOLVED__", "Unresolved", "other", "40"],
        ["__NO_DISCLOSURE__", "None", "other", "30"],
    ]
    example = landing_example([_cand("C", holdings=holdings)])
    assert example is not None
    assert [r["name"] for r in example["top"]] == ["Big Co", "Mid Co", "Short Co"]
    # Bars run against the largest holding shown (the figure beside each is the
    # real weight): 150 fills the track, 20 is 13.33 of it, -5 draws nothing.
    assert [r["width"] for r in example["top"]] == ["100.00", "13.33", "0.00"]
    assert example["top"][1]["weight_label"] == format_pct(Decimal("20"), precision=1)
    assert len(example["ranges"]) == 3
    assert example["as_of_label"] and example["ter_label"] == "0.75%"


def test_the_mix_bar_is_laid_end_to_end() -> None:
    mix = [["debt", "5.0"], ["equity", "88.0"], ["cash", "7.0"]]
    example = landing_example([_cand("C", mix=mix)])
    assert example is not None
    assert [m["label"] for m in example["mix"]] == [
        "Shares", "Cash and equivalents", "Bonds and other debt"]
    assert [m["x"] for m in example["mix"]] == ["0.00", "88.00", "95.00"]
    assert [m["width"] for m in example["mix"]] == ["88.00", "7.00", "5.00"]
    assert example["mix"][0]["pct_label"] == format_pct(Decimal("88.0"), precision=1)


PAIR_C = [["I1", "One Co", "equity", "10"], ["I2", "Two Co", "equity", "5"],
          ["I9", "Nine Co", "equity", "85"]]
PAIR_G = [["I1", "One Co", "equity", "6"], ["I2", "Two Co", "equity", "8"],
          ["I7", "Seven Co", "equity", "86"]]


def test_the_pair_is_the_largest_fund_from_another_equity_category() -> None:
    candidates = [
        _cand("C", holdings=PAIR_C),
        _cand("F", category="equity/large_cap", size="500", holdings=PAIR_G),
        _cand("G", category="equity/mid_cap", size="600", holdings=PAIR_G),
        _cand("H", category="debt/liquid", size="2000", holdings=PAIR_G),
        _cand("K", category="equity/small_cap", size="9000", has_holdings=False),
    ]
    pair = landing_pair("C", candidates)
    assert pair is not None
    assert [f["scheme_id"] for f in pair["funds"]] == ["C", "G"]


def test_the_pair_overlap_is_pairwise_overlap() -> None:
    candidates = [_cand("C", holdings=PAIR_C),
                  _cand("G", category="equity/mid_cap", holdings=PAIR_G)]
    pair = landing_pair("C", candidates)
    assert pair is not None

    def weights(rows: list[list[str]]) -> list[IssuerWeight]:
        return [IssuerWeight(IssuerId(i), Decimal(w), c) for i, _, c, w in rows]

    expected = pairwise_overlap(SchemeId("C"), SchemeId("G"), date(2026, 8, 31),
                                date(2026, 8, 31), weights(PAIR_C), weights(PAIR_G))
    assert pair["common"] == 2
    assert pair["overlap_label"] == format_pct(expected.overlap_pct, precision=1)
    # (10 + 6) / 2 = 8 beats (5 + 8) / 2 = 6.5: with ₹1 in each, One Co is 8% of it.
    assert pair["lead"] == {"name": "One Co", "share_label": format_pct(Decimal("8"),
                                                                        precision=1)}
    for fund in pair["funds"]:
        shared = {r["name"] for r in fund["top"] if r["shared"]}
        assert shared == {"One Co", "Two Co"}


def test_a_pair_with_nothing_in_common_says_so() -> None:
    other = [["I5", "Five Co", "equity", "100"]]
    pair = landing_pair("C", [_cand("C", holdings=PAIR_C),
                              _cand("G", category="equity/mid_cap", holdings=other)])
    assert pair is not None
    assert pair["common"] == 0 and pair["lead"] is None


def test_no_second_fund_no_pair() -> None:
    assert landing_pair("C", [_cand("C"), _cand("D")]) is None


def test_the_card_names_the_category_as_the_site_does() -> None:
    """AMFI's heading ("Equity Scheme - Flexi Cap Fund") becomes the short name."""
    example = landing_example([_cand("C")])
    assert example is not None and example["detail"] == "Flexi cap · Direct · Growth"


def test_an_example_needs_a_named_holding() -> None:
    """A fund whose disclosure resolved to no company would show an empty list."""
    synthetic = [["__UNRESOLVED__", "Unresolved", "other", "100"]]
    assert landing_example([_cand("C", holdings=synthetic)]) is None
    example = landing_example([_cand("C", size="9", holdings=synthetic), _cand("D")])
    assert example is not None and example["scheme_id"] == "D"


def test_a_tied_lead_goes_to_the_lower_issuer_id() -> None:
    """Like every other tie in the landing page's rules."""
    both = [["I2", "Two Co", "equity", "6"], ["I1", "One Co", "equity", "6"],
            ["I9", "Nine Co", "equity", "88"]]
    other = [["I2", "Two Co", "equity", "6"], ["I1", "One Co", "equity", "6"],
             ["I7", "Seven Co", "equity", "88"]]
    pair = landing_pair("C", [_cand("C", holdings=both),
                              _cand("G", category="equity/mid_cap", holdings=other)])
    assert pair is not None and pair["lead"] is not None
    assert pair["lead"]["name"] == "One Co"


def test_the_mix_bar_fits_when_a_sleeve_is_negative() -> None:
    """Parag Parikh Flexi Cap's mix: the positive parts total 101.9% beside -1.9%
    of derivatives. The bar is scaled to fit, so its parts sit end to end within
    it; the labels keep the real figures."""
    mix = [["equity", "84.1"], ["other", "6.2"], ["debt", "5.9"], ["cash", "5.3"],
           ["mfunit", "0.4"], ["derivative", "-1.9"]]
    example = landing_example([_cand("C", mix=mix)])
    assert example is not None
    widths = [Decimal(m["width"]) for m in example["mix"]]
    ends = [Decimal(m["x"]) + Decimal(m["width"]) for m in example["mix"]]
    assert abs(sum(widths, Decimal(0)) - 100) <= Decimal("0.05")
    assert max(ends) <= Decimal("100.05")
    assert widths[-1] == 0  # the negative sleeve draws nothing
    assert example["mix"][0]["pct_label"] == format_pct(Decimal("84.1"), precision=1)


def test_the_pair_partner_names_its_companies() -> None:
    """A partner whose disclosure matched no company would make the page say the
    two "share nothing"; it is passed over for one that names its holdings."""
    unresolved = [["__UNRESOLVED__", "Unresolved", "other", "100"]]
    pair = landing_pair("C", [
        _cand("C", holdings=PAIR_C),
        _cand("Z", category="equity/small_cap", size="9000", holdings=unresolved),
        _cand("G", category="equity/mid_cap", size="600", holdings=PAIR_G),
    ])
    assert pair is not None and pair["funds"][1]["scheme_id"] == "G"
