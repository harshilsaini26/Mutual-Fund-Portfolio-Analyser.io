"""Which share class stands for a fund (`m0_data.universe.live_funds`).

Design critique, 2026-11-04: HSBC Liquid and Navi Liquid sat at +0.0% a year at
the foot of the liquid category. AMFI's file lists their Direct Growth plans
with the plan and option wrong or blank ("Regular Plan;Direct"), so the only
Direct plans left were daily IDCW ones, whose NAV stays near ₹1,000 because the
income is paid out. That NAV is no total return, and ranking it against growth
plans puts a fund that earned 6.5% a year at the bottom with nothing.
"""

from __future__ import annotations

from pathlib import Path

from src.common.decimals import connect
from src.m0_data.universe import live_funds

from tests.conftest import migrated


def test_a_fund_whose_direct_plan_pays_out_its_income_is_not_a_live_fund(
    tmp_path: Path,
) -> None:
    db = tmp_path / "w.db"
    migrated(db)
    conn = connect(str(db))
    for sid, family, option in (
        ("G1", "fund one", "growth"),
        ("I1", "fund one", "idcw_payout"),      # beside its growth plan: unused
        ("I2", "liquid fund", "idcw_payout"),   # its growth plan misfiled by AMFI
        ("I3", "liquid fund", "idcw_reinvest"),
        ("E1", "an etf", "unknown"),            # an ETF states no option at all
    ):
        conn.execute(
            "INSERT INTO scheme (scheme_id, scheme_name, plan, option, amc_id,"
            " scheme_family, status, last_seen) VALUES (?, ?, 'direct', ?, 'amc1', ?,"
            " 'active', '2026-10-03')",
            (sid, family.title(), option, family),
        )
    conn.commit()
    assert sorted(f.scheme_id for f in live_funds(conn)) == ["E1", "G1"]
