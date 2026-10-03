"""The landing page's example fund and example pair (DECISIONS V1-89).

Both are picked by a stated rule from what the build loop already drew -- the
`/funds/` row, the peer panel's ranges and the look-through file -- so nothing is
computed twice and the page can say why this fund: "the largest flexi cap fund by
size". Geometry (bar lengths, offsets) is returned as text for SVG attributes; every
figure beside it is formatted here (§16.4). Sorted in Python on Decimals, never in
SQL (CLAUDE.md invariant 1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.common.types import IssuerId, SchemeId
from src.m3_lookthrough.engine import IssuerWeight, is_synthetic
from src.m3_lookthrough.overlap import pairwise_overlap
from src.m6_views.builders.fund.common import CLASS_NAMES
from src.m6_views.format import DASH, format_date, format_pct
from src.m6_views.render import bar_width

EXAMPLE_CATEGORY = "equity/flexi_cap"
#: The index of "5y" in `publish_site.RETURN_WINDOWS` (a test holds the two together;
#: importing it would make the two modules import each other).
FIVE_YEAR = 2
TOP_HOLDINGS = 5
PAIR_HOLDINGS = 3


def landing_candidate(
    row: dict[str, Any], ranges: list[dict[str, Any]], held: dict[str, Any] | None
) -> dict[str, Any]:
    """One equity fund as the build loop saw it: its `/funds/` row, its peer ranges
    (`render.range_bars`) and its look-through file (`lookthrough_file`)."""
    return {"row": row, "ranges": ranges, "held": held}


def _size(candidate: dict[str, Any]) -> Decimal:
    return Decimal(candidate["row"]["size_value"])


def _largest(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = sorted(candidates, key=lambda c: (-_size(c), c["row"]["scheme_id"]))
    return ranked[0] if ranked else None


def _holdings(held: dict[str, Any]) -> list[tuple[str, str, Decimal]]:
    """(issuer id, name, weight), named companies only, largest first."""
    named = [(str(i), str(n), Decimal(w)) for i, n, _, w in held["holdings"]
             if not is_synthetic(str(i))]
    return sorted(named, key=lambda h: (-h[2], h[0]))


def _qualifies(c: dict[str, Any]) -> bool:
    row = c["row"]
    return (row["category_key"] == EXAMPLE_CATEGORY and bool(row["size_value"])
            and bool(row["returns"][FIVE_YEAR]["value"]) and row["ter_label"] != DASH
            and c["held"] is not None and len(c["ranges"]) == 3
            and bool(_holdings(c["held"])))


def _mix(held: dict[str, Any]) -> list[dict[str, str]]:
    parts = sorted(((k, Decimal(v)) for k, v in held["mix"]), key=lambda p: (-p[1], p[0]))
    # A negative sleeve (derivatives) lets the positive parts pass 100%: the bar is
    # scaled to hold them end to end; the labels keep the real figures.
    scale = max(sum((p for _, p in parts if p > 0), Decimal(0)), Decimal(100))
    out, x = [], Decimal(0)
    for kind, pct in parts:
        width = Decimal(bar_width(pct * 100 / scale))
        out.append({"label": CLASS_NAMES.get(kind, kind),
                    "pct_label": format_pct(pct, precision=1),
                    "x": f"{min(x, Decimal(100)):.2f}", "width": f"{width:.2f}"})
        x += width
    return out


def landing_example(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The largest flexi cap fund by size whose page has holdings, a five-year return,
    a cost and all three return ranges. Equal sizes go to the lower scheme id."""
    chosen = _largest([c for c in candidates if _qualifies(c)])
    if chosen is None:
        return None
    row, held = chosen["row"], chosen["held"]
    top = _holdings(held)[:TOP_HOLDINGS]
    # Each bar runs against the largest holding shown; the figure beside it is the
    # holding's real weight, so the bars compare holdings and say nothing alone.
    largest = max((w for _, _, w in top), default=Decimal(0))
    # AMFI's heading first in `detail` ("Equity Scheme - Flexi Cap Fund · Direct ·
    # Growth") becomes the name the site uses everywhere else.
    plan = row["detail"].split(" · ")[1:]
    return {
        "scheme_id": row["scheme_id"], "name": row["name"],
        "detail": " · ".join([row["category_short"], *plan]),
        "category": row["category_short"], "ter_label": row["ter_label"],
        "as_of_label": format_date(date.fromisoformat(held["as_of"])),
        "aggregator": bool(held.get("aggregator")),
        "mix": _mix(held),
        "top": [{"name": n, "weight_label": format_pct(w, precision=1),
                 "width": bar_width(w * 100 / largest if largest > 0 else 0)}
                for _, n, w in top],
        "ranges": chosen["ranges"],
    }


def _weights(held: dict[str, Any]) -> list[IssuerWeight]:
    return [IssuerWeight(IssuerId(str(i)), Decimal(w), str(k))
            for i, _, k, w in held["holdings"]]


def landing_pair(
    example_id: str, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The example fund and the largest fund, with holdings, from another equity
    category: what they hold in common, with ₹1 in each."""
    first = next((c for c in candidates if c["row"]["scheme_id"] == example_id), None)
    if first is None or first["held"] is None:
        return None
    second = _largest([
        c for c in candidates
        if c["held"] is not None and c["row"]["family"] == "equity"
        and c["row"]["category_key"] != first["row"]["category_key"]
        and c["row"]["size_value"] and _holdings(c["held"])
    ])
    if second is None:
        return None
    a, b = first["held"], second["held"]
    found = pairwise_overlap(
        SchemeId(example_id), SchemeId(second["row"]["scheme_id"]),
        date.fromisoformat(a["as_of"]), date.fromisoformat(b["as_of"]),
        _weights(a), _weights(b),
    )
    wa = {i: w for i, _, w in _holdings(a)}
    wb = {i: w for i, _, w in _holdings(b)}
    names = {i: n for i, n, _ in _holdings(a) + _holdings(b)}
    shared = wa.keys() & wb.keys()
    # The largest average weight; a tie goes to the lower issuer id, as every tie here.
    lead = min(shared, key=lambda i: (-(wa[i] + wb[i]) / 2, i), default=None)
    return {
        "funds": [
            {"scheme_id": c["row"]["scheme_id"], "name": c["row"]["name"],
             "category": c["row"]["category_short"],
             "top": [{"name": n, "weight_label": format_pct(w, precision=1),
                      "shared": i in shared}
                     for i, n, w in _holdings(c["held"])[:PAIR_HOLDINGS]]}
            for c in (first, second)
        ],
        "common": len(shared),
        "overlap_label": format_pct(found.overlap_pct, precision=1),
        "lead": None if lead is None else {
            "name": names[lead],
            "share_label": format_pct((wa[lead] + wb[lead]) / 2, precision=1)},
    }
