"""A zero AMFI publishes is "not reported", not a figure (external audit, 2026-10-04).

AMFI lists some funds of funds with a size of 0 and some ETFs with an expense
ratio of 0.0000. Neither is real: shown, they read as "₹0" and "0.00%", and the
zero cost ranked those ETFs cheapest. The provider hands back None instead, as
for a fund with no row at all (D-613: None renders as "—").
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.decimals import connect
from src.common.types import SchemeId
from src.m0_data.providers.warehouse import WarehouseMarketDataProvider

from tests.conftest import migrated


def _provider(tmp_path: Path, aum: str, ter: str) -> WarehouseMarketDataProvider:
    db = tmp_path / "w.db"
    migrated(db)
    conn = connect(str(db))
    conn.execute(
        "INSERT INTO scheme (scheme_id, scheme_name, plan, option, status)"
        " VALUES ('S1', 'Omni FoF - Direct Growth', 'direct', 'growth', 'active')"
    )
    conn.execute(
        "INSERT INTO scheme_aum (scheme_id, as_of_date, aum_inr, basis, source_file_id)"
        " VALUES ('S1', '2026-06-30', ?, 'quarterly_average', 'f1')",
        (aum,),
    )
    conn.execute(
        "INSERT INTO scheme_ter (scheme_id, valid_from, total_ter, base_ter,"
        " source_file_id)"
        " VALUES ('S1', '2026-08-31', ?, ?, 'f1')",
        (ter, ter),
    )
    conn.commit()
    return WarehouseMarketDataProvider(conn)


def test_a_zero_size_or_cost_is_not_reported(tmp_path: Path) -> None:
    md = _provider(tmp_path, "0", "0.0000")
    facts = md.scheme_facts(SchemeId("S1"))
    assert facts is not None
    assert facts.aum_inr is None and facts.aum_as_of is None
    assert facts.ter is None
    assert md.fund_sizes(["S1"]) == {}
    assert md.ters(["S1"], date.max) == {}


def test_a_real_size_and_cost_are_kept(tmp_path: Path) -> None:
    md = _provider(tmp_path, "1250000000", "0.6200")
    facts = md.scheme_facts(SchemeId("S1"))
    assert facts is not None and facts.aum_inr is not None and facts.ter is not None
    assert "S1" in md.fund_sizes(["S1"]) and "S1" in md.ters(["S1"], date.max)
