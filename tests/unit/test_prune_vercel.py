"""jobs/prune_vercel.py: keep only the deployment the site is served from.

Vercel deploys every push to gh-pages, a full copy of the site each night, and a
month of them filled the Hobby plan's 10 GB. These tests drive the job against a fake
API (the `call` it is handed): which deployments go, which stay, and that it deletes
nothing until the new build is the live one.

What this does not prove: that Vercel's real responses have the fields used here. They
were read from Vercel's REST API reference on 2026-11-01 (GET /v7/deployments `uid`,
`readyState`, `pagination.next`; GET /v9/projects/{idOrName} `alias[].environment`,
`alias[].deployment.id`; DELETE /v13/deployments/{id}); the first real run is the check.
"""

from __future__ import annotations

from typing import Any

import pytest
from jobs import prune_vercel as P


def dep(uid: str, state: str = "READY", target: str | None = "production",
        created: int = 0) -> dict[str, Any]:
    return {"uid": uid, "readyState": state, "target": target, "created": created}


PROJECT = {"alias": [
    {"domain": "didmysipwork.vercel.app", "environment": "production",
     "deployment": {"id": "dpl_live"}},
    {"domain": "x-git-gh-pages.vercel.app", "environment": "preview",
     "deployment": {"id": "dpl_branch"}},
]}


def test_the_live_deployment_is_the_one_the_production_alias_points_at() -> None:
    assert P.live_ids(PROJECT) == {"dpl_live"}
    assert P.live_ids({"alias": []}) == set()
    unset = {"alias": [{"environment": "production", "deployment": None}]}
    assert P.live_ids(unset) == set()


def test_everything_but_the_kept_and_the_unfinished_goes() -> None:
    deps = [dep("dpl_live"), dep("dpl_old"), dep("dpl_err", "ERROR"),
            dep("dpl_prev", target=None), dep("dpl_new", "BUILDING"),
            dep("dpl_q", "QUEUED"), dep("dpl_gone", "DELETED")]
    gone = [d["uid"] for d in P.doomed(deps, {"dpl_live"})]
    assert gone == ["dpl_old", "dpl_err", "dpl_prev"]


def test_with_no_live_deployment_nothing_is_deleted() -> None:
    with pytest.raises(P.PruneError, match="no deployment holds the production alias"):
        P.plan([dep("dpl_a"), dep("dpl_b")], {"alias": []})


class FakeVercel:
    """Vercel's API, as far as the job uses it, over a list of deployments."""

    def __init__(self, deployments: list[dict[str, Any]], project: dict[str, Any],
                 page: int = 2) -> None:
        self.deployments, self.project, self.page = deployments, project, page
        self.deleted: list[str] = []
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(self, method: str, path: str, params: dict[str, Any]) -> Any:
        self.calls.append((method, path, params))
        if method == "GET" and path.startswith("/v9/projects/"):
            return self.project
        if method == "GET" and path == "/v7/deployments":
            rows = sorted(self.deployments, key=lambda d: -d["created"])
            if "sha" in params:
                rows = [d for d in rows if d.get("sha") == params["sha"]]
            if "until" in params:
                rows = [d for d in rows if d["created"] < params["until"]]
            got = rows[: self.page]
            more = len(rows) > self.page
            after = got[-1]["created"] if more else None
            return {"deployments": got,
                    "pagination": {"count": len(got), "next": after, "prev": None}}
        if method == "DELETE":
            self.deleted.append(path.rsplit("/", 1)[1])
            return {"state": "DELETED", "uid": path.rsplit("/", 1)[1]}
        raise AssertionError(f"unexpected call {method} {path}")


def test_every_page_of_deployments_is_read() -> None:
    api = FakeVercel([dep(f"dpl_{i}", created=i) for i in range(1, 6)], PROJECT, page=2)
    assert [d["uid"] for d in P.deployments(api, "site")] == [
        "dpl_5", "dpl_4", "dpl_3", "dpl_2", "dpl_1"]
    assert all(c[2]["projectId"] == "site" for c in api.calls)


def test_a_dry_run_lists_and_deletes_nothing() -> None:
    api = FakeVercel([dep("dpl_live", created=3), dep("dpl_old", created=2)], PROJECT)
    gone = P.prune(api, "site", delete=False)
    assert [d["uid"] for d in gone] == ["dpl_old"] and api.deleted == []


def test_delete_removes_all_but_the_live_one() -> None:
    api = FakeVercel([dep("dpl_live", created=9)] + [dep(f"dpl_{i}", created=i)
                                                     for i in range(1, 5)], PROJECT)
    P.prune(api, "site", delete=True)
    assert sorted(api.deleted) == ["dpl_1", "dpl_2", "dpl_3", "dpl_4"]


def test_after_a_build_it_waits_for_that_commit_to_be_live_first() -> None:
    """The new deployment builds, then becomes ready, then takes the alias: only
    then does anything go, and the old live one goes with the rest."""
    new = {**dep("dpl_new", "BUILDING", created=10), "sha": "abc"}
    api = FakeVercel([new, dep("dpl_live", created=5), dep("dpl_old", created=1)],
                     PROJECT)
    ticks: list[int] = []

    def wait(_: float) -> None:
        ticks.append(1)
        if len(ticks) == 1:
            new["readyState"] = "READY"
        elif len(ticks) == 2:
            api.project = {"alias": [{"environment": "production",
                                      "deployment": {"id": "dpl_new"}}]}

    P.prune(api, "site", delete=True, sha="abc", sleep=wait, timeout=60, every=1)
    assert sorted(api.deleted) == ["dpl_live", "dpl_old"]
    assert len(ticks) == 2


@pytest.mark.parametrize("state", ["ERROR", "CANCELED"])
def test_a_build_that_failed_deletes_nothing(state: str) -> None:
    api = FakeVercel([{**dep("dpl_new", state, created=10), "sha": "abc"},
                      dep("dpl_live", created=5), dep("dpl_old", created=1)], PROJECT)
    with pytest.raises(P.PruneError, match=state):
        P.prune(api, "site", delete=True, sha="abc", sleep=lambda _: None,
                timeout=5, every=1)
    assert api.deleted == []


def test_a_build_never_seen_live_deletes_nothing() -> None:
    api = FakeVercel([{**dep("dpl_new", "BUILDING", created=10), "sha": "abc"},
                      dep("dpl_live", created=5), dep("dpl_old", created=1)], PROJECT)
    with pytest.raises(P.PruneError, match="not live"):
        P.prune(api, "site", delete=True, sha="abc", sleep=lambda _: None,
                timeout=3, every=1)
    assert api.deleted == []


def test_the_token_is_read_from_the_environment_only(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="VERCEL_TOKEN"):
        P.main(["--project", "site"])
