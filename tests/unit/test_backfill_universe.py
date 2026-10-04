"""Which funds the nightly history step covers (`backfill_scheme_nav --universe`).

External audit, 2026-10-04: Your portfolio lists Regular plans now, so their
price histories are fetched with their Direct plans' (`regular_twins`).
"""

from __future__ import annotations

from pathlib import Path

from jobs.backfill_scheme_nav import universe_ids
from src.common.decimals import connect

from tests.conftest import migrated


def test_the_universe_is_every_live_direct_plan_and_its_regular_twin(
    tmp_path: Path,
) -> None:
    db = tmp_path / "w.db"
    migrated(db)
    conn = connect(str(db))
    for sid, plan, family, seen in (
        ("D1", "direct", "fund one", "2026-10-03"),
        ("R1", "regular", "fund one", "2026-10-03"),   # its twin
        ("D2", "direct", "fund two", "2026-10-03"),     # no Regular plan
        ("R9", "regular", "old fund", "2026-10-03"),    # Regular-only legacy fund
        ("RX", "regular", "fund one", "2020-01-01"),    # long gone
    ):
        conn.execute(
            "INSERT INTO scheme (scheme_id, scheme_name, plan, option, amc_id,"
            " scheme_family, status, last_seen) VALUES (?, ?, ?, 'growth', 'amc1', ?,"
            " 'active', ?)",
            (sid, family.title(), plan, family, seen),
        )
    conn.commit()
    assert universe_ids(conn) == ["D1", "D2", "R1"]
