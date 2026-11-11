"""The fund page, end to end over a migrated warehouse.

Opened with plain `connect()`, as `jobs/serve.py` opens it: tuple rows, no
`row_factory`. The provider reads rows by name, and before it set that on its
own cursor this page raised on the first NAV it read.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from src.common.decimals import connect
from src.common.types import UserId, ViewState
from src.m1_ledger.db import apply_ledger_schema, connect_ledger
from src.m6_views.builder import Scope
from src.m6_views.builders import fund  # noqa: F401  — registers builders
from src.m6_views.deps import Deps
from src.m6_views.envelope import ViewEnvelope
from src.m6_views.registry import VIEW_REGISTRY

from tests.conftest import migrated

AS_OF = date(2026, 9, 4)
DAYS = 800
INDEX = "NSE:NIFTY_500_TRI"


@pytest.fixture
def deps(tmp_path: Path) -> Deps:
    db = str(tmp_path / "warehouse.db")
    migrated(db)
    warehouse: sqlite3.Connection = connect(db)
    warehouse.execute(
        "INSERT INTO benchmark_index (index_id, index_name, is_total_return)"
        " VALUES (?, 'Nifty 500 TRI', 1)",
        (INDEX,),
    )
    warehouse.executemany(
        "INSERT INTO scheme (scheme_id, scheme_name, plan, option, benchmark_id)"
        " VALUES (?, ?, 'direct', ?, ?)",
        [("S1", "Growth fund", "growth", INDEX), ("FLAT", "IDCW fund", "idcw", None)],
    )
    days = [AS_OF - timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    warehouse.executemany(
        "INSERT INTO nav_daily (scheme_id, nav_date, nav, nav_adj) VALUES (?,?,?,?)",
        [
            (s, d, nav, nav)
            for i, d in enumerate(days)
            for s, nav in (
                ("S1", Decimal(100) + Decimal(i) / 10 + i % 7),
                ("FLAT", Decimal(10)),
            )
        ],
    )
    warehouse.executemany(
        "INSERT INTO index_level (index_id, level_date, level) VALUES (?,?,?)",
        [(INDEX, d, Decimal(1000) + i + 3 * (i % 5)) for i, d in enumerate(days)],
    )
    warehouse.commit()
    ledger = connect_ledger(str(tmp_path / "personal.db"), key="test-key")
    apply_ledger_schema(ledger)
    return Deps.over(ledger, warehouse)


def build(deps: Deps, scheme: str) -> ViewEnvelope:
    scope = Scope(user_id=UserId("USER-01"), as_of=AS_OF, scope_type="scheme",
                  scope_id=scheme)
    return VIEW_REGISTRY["fund_xray_header"](deps).build(scope, {})


def test_every_window_is_a_row_measured_against_its_benchmark(deps: Deps) -> None:
    env = build(deps, "S1")
    assert env.state == ViewState.OK, env.state_reason
    rows = env.payload["rows"]
    # The key stays the key; the table shows a name beside it, as Returns names
    # its periods (design critique, 2026-11-04).
    assert [r["window_key"] for r in rows] == ["1y", "3y", "5y", "since_first_nav"]
    names = [r["window"] for r in rows]
    assert names[:3] == ["1 year", "3 years", "5 years"] and names[3].startswith("Since ")
    shown = [c["key"] for c in env.payload["columns"]]
    assert shown[0] == "window" and "window_key" not in shown
    assert all(r["beta"] is not None and r["alpha_ann"] is not None for r in rows)
    assert INDEX in env.payload["definition"]
    # Look-through properties, not a fund's: "not applicable", never 100%.
    assert env.coverage_pct is None and env.unresolved_pct is None
    assert env.data_as_of == AS_OF and env.staleness_days == 0


def test_the_site_build_reads_its_figures_from_every_figures_rows(deps: Deps) -> None:
    """Regression, 2026-11-11: the window column was renamed to its display name
    ("3 years"), and the site build, which finds the three-year row by its key,
    published every fund's return, volatility, fall and Sharpe as blank for a
    week. The build reads `window_key`; the page shows `window`."""
    from jobs.publish_site import fund_record

    env = build(deps, "S1")
    row = {"scheme_id": "S1", "amfi_code": "1", "name": "Fund", "category_key": "k",
           "category_short": "K", "ter_value": None, "size_value": None,
           "house": None, "rank_label": None, "size_label": None, "category": None}
    record = fund_record(row, env, "2013-01-01")
    # The fixture's prices span one year, not three: the one-year figure is the
    # one that must arrive.
    assert record["r1"] is not None and record["labels"]["r1"].endswith("p.a.")


def test_a_flat_nav_is_explained_not_reported_as_zero(deps: Deps) -> None:
    env = build(deps, "FLAT")
    assert env.state == ViewState.EMPTY
    assert env.state_reason and "IDCW" in env.state_reason
