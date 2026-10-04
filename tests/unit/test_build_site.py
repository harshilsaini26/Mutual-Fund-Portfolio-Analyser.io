"""The nightly build's fetch steps (`jobs.build_site.fetch`).

External audit, 2026-10-04: no holdings on the public site came from Kotak's or
ICICI's own files, though the build fetches them. Those steps are optional, and
a failure printed one line deep in the log. On GitHub Actions it is a warning
now, on the run's summary page.
"""

from __future__ import annotations

from collections.abc import Sequence

import jobs.build_site as build_site
import pytest


def _failing(name: str):  # type: ignore[no-untyped-def]
    def run(job: Sequence[str], env: dict[str, str]) -> int:
        return 1 if name in job else 0
    return run


def test_a_failed_optional_step_is_a_warning_on_actions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(build_site, "run_step", _failing("kotak"))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert build_site.fetch({}) == ["Kotak's disclosures"]
    out = capsys.readouterr().out
    assert "::warning title=Nightly build::Kotak's disclosures did not finish" in out


def test_off_actions_it_is_a_plain_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(build_site, "run_step", _failing("icici"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert build_site.fetch({}) == ["ICICI Prudential's disclosures"]
    assert "::warning" not in capsys.readouterr().out


def test_a_failed_required_step_stops_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_site, "run_step", _failing("fetch_nav"))
    with pytest.raises(SystemExit, match="today's prices"):
        build_site.fetch({})
