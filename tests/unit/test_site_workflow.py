"""The daily site build's workflow keeps its token to itself. DECISIONS V1-75.

`.github/workflows/site.yml` can push to the repository. What keeps that safe is
in the file, so it is asserted rather than trusted: it never runs on a pull
request (where a stranger's code would run with the token), it asks for no more
than write access to contents, and every action is pinned to a commit rather
than a tag that could be moved to other code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "site.yml"


def _workflow() -> dict[Any, Any]:
    loaded: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return loaded


def test_it_never_runs_on_a_pull_request() -> None:
    # PyYAML reads the bare key `on` as the boolean True.
    workflow = _workflow()
    triggers: dict[str, Any] = workflow.get(True) or workflow.get("on") or {}
    assert set(triggers) == {"schedule", "workflow_dispatch"}


def test_it_asks_only_for_write_access_to_contents() -> None:
    assert _workflow()["permissions"] == {"contents": "write"}


def test_every_action_is_pinned_to_a_commit() -> None:
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW.read_text(encoding="utf-8"))
    assert uses, "no actions found"
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action


def test_the_checkouts_keep_no_credentials() -> None:
    for job in _workflow()["jobs"].values():
        checkouts = [
            s for s in job["steps"]
            if str(s.get("uses", "")).startswith("actions/checkout")
        ]
        assert checkouts
        assert all(s["with"]["persist-credentials"] is False for s in checkouts)


def _step(job: str, name: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = _workflow()["jobs"][job]["steps"]
    return next(s for s in steps if s.get("name") == name)


def test_older_vercel_deployments_go_only_once_tonights_is_live() -> None:
    """Vercel keeps a full copy of the site for every push: a month of them filled the
    Hobby plan's 10 GB (jobs/prune_vercel.py). The step runs after the publish, waits
    for that commit (--sha), never fails the build, and has its token from secrets."""
    steps = [s.get("name") for s in _workflow()["jobs"]["build"]["steps"]]
    prune = _step("build", "Delete older Vercel deployments")
    assert (steps.index("Delete older Vercel deployments")
            > steps.index("Build and publish"))
    assert prune.get("continue-on-error") is True
    assert prune["env"]["VERCEL_TOKEN"] == "${{ secrets.VERCEL_TOKEN }}"
    assert "python -m jobs.prune_vercel --sha" in prune["run"]
    assert "--delete" in prune["run"]
    assert "echo $VERCEL_TOKEN" not in prune["run"]


def test_a_run_by_hand_can_delete_older_deployments_without_building() -> None:
    workflow = _workflow()
    triggers: dict[str, Any] = workflow.get(True) or workflow.get("on") or {}
    only = triggers["workflow_dispatch"]["inputs"]["prune_only"]
    assert only["type"] == "boolean" and only["default"] is False
    assert workflow["jobs"]["build"]["if"] == "${{ !inputs.prune_only }}"
    assert workflow["jobs"]["prune"]["if"] == "${{ inputs.prune_only }}"
    run = _step("prune", "Delete every Vercel deployment but the live one")["run"]
    assert "python -m jobs.prune_vercel --delete" in run and "--sha" not in run
