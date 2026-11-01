"""Delete every Vercel deployment of the public site but the one it is served from.

Each nightly build force-pushes one commit to gh-pages, and Vercel's Git integration
deploys every push: a full copy of the site (about 250 MB) a night, so a month of them
filled the Hobby plan's 10 GB of storage. This keeps the deployment the production alias
points at (the live site) and any deployment still building, and deletes the rest.

    python -m jobs.prune_vercel --project NAME                  # list what would go
    python -m jobs.prune_vercel --project NAME --delete         # delete it
    python -m jobs.prune_vercel --project NAME --sha SHA --delete
        # after a build (.github/workflows/site.yml): first wait until Vercel has
        # deployed that gh-pages commit and made it the live one, then delete the rest

The token is read from VERCEL_TOKEN in the environment, never from an argument (where
the shell's history and the process list would keep it), and is sent only to
api.vercel.com. VERCEL_PROJECT and VERCEL_TEAM_ID may stand in for --project and --team.

Nothing is deleted when the live deployment cannot be found, or when the new build
failed or did not become live in time: the site stays as it is, and so does the bill.
Endpoints from Vercel's REST API reference, read 2026-11-01: GET /v9/projects/{idOrName}
(`alias[].environment`, `alias[].deployment.id`), GET /v7/deployments (`uid`,
`readyState`, `pagination.next`, the `sha` filter), DELETE /v13/deployments/{id}.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

API = "https://api.vercel.com"
#: Never deleted: a deployment Vercel has not finished (it may be tonight's).
UNFINISHED = {"BUILDING", "INITIALIZING", "QUEUED"}
WAIT_SECONDS, EVERY_SECONDS = 20 * 60, 20

Call = Callable[[str, str, dict[str, Any]], Any]


class PruneError(RuntimeError):
    """Why nothing was deleted."""


def live_ids(project: dict[str, Any]) -> set[str]:
    """The deployments the production alias (every production domain) points at."""
    return {a["deployment"]["id"] for a in project.get("alias") or []
            if a.get("environment") == "production" and a.get("deployment")}


def doomed(deployments: list[dict[str, Any]], keep: set[str]) -> list[dict[str, Any]]:
    """Every deployment but the kept ones, those still building, and those gone."""
    return [d for d in deployments if d["uid"] not in keep
            and d.get("readyState") not in UNFINISHED | {"DELETED"}]


def plan(deployments: list[dict[str, Any]],
         project: dict[str, Any]) -> list[dict[str, Any]]:
    keep = live_ids(project)
    if not keep:
        raise PruneError("no deployment holds the production alias; nothing deleted")
    return doomed(deployments, keep)


def deployments(call: Call, project: str) -> list[dict[str, Any]]:
    """All of the project's deployments, newest first, page by page."""
    params: dict[str, Any] = {"projectId": project, "limit": 100}
    out: list[dict[str, Any]] = []
    for _ in range(1000):
        page = call("GET", "/v7/deployments", params)
        out += page["deployments"]
        after = (page.get("pagination") or {}).get("next")
        if not after:
            return out
        params = {**params, "until": after}
    raise PruneError("more than 100,000 deployments listed; stopped")


def wait_until_live(call: Call, project: str, sha: str, sleep: Callable[[float], None],
                    timeout: float, every: float) -> str:
    """The deployment of commit `sha`, once it is ready and the live one."""
    waited = 0.0
    while True:
        rows = call("GET", "/v7/deployments",
                    {"projectId": project, "sha": sha, "limit": 5})
        newest = (rows.get("deployments") or [None])[0]
        state = newest.get("readyState") if newest else None
        if state in ("ERROR", "CANCELED"):
            raise PruneError(
                f"the deployment of {sha[:7]} ended {state}; nothing deleted")
        if state == "READY" and newest is not None and newest["uid"] in live_ids(
                call("GET", f"/v9/projects/{urllib.parse.quote(project)}", {})):
            return str(newest["uid"])
        if waited >= timeout:
            raise PruneError(f"the deployment of {sha[:7]} was not live after "
                             f"{timeout / 60:g} minutes; nothing deleted")
        sleep(every)
        waited += every


def prune(call: Call, project: str, delete: bool, sha: str | None = None,
          sleep: Callable[[float], None] = time.sleep, timeout: float = WAIT_SECONDS,
          every: float = EVERY_SECONDS) -> list[dict[str, Any]]:
    """The deployments that go (deleted only with `delete`)."""
    if sha:
        wait_until_live(call, project, sha, sleep, timeout, every)
    gone = plan(deployments(call, project),
                call("GET", f"/v9/projects/{urllib.parse.quote(project)}", {}))
    if delete:
        for d in gone:
            call("DELETE", f"/v13/deployments/{d['uid']}", {})
    return gone


def client(token: str, team: str | None) -> Call:
    """Vercel's REST API, with the token in the header and nowhere else."""
    def call(method: str, path: str, params: dict[str, Any]) -> Any:
        query = {**params, **({"teamId": team} if team else {})}
        url = f"{API}{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
        request = urllib.request.Request(url, method=method,
                                         headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            if method == "DELETE" and exc.code in (404, 410):
                return None   # already gone
            body = exc.read()[:300].decode("utf-8", "replace")
            raise PruneError(f"{method} {path}: HTTP {exc.code} {body}") from exc
    return call


def _when(d: dict[str, Any]) -> str:
    created = d.get("created") or d.get("createdAt")
    if not created:
        return "?"
    return datetime.fromtimestamp(created / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project", default=os.environ.get("VERCEL_PROJECT"),
                        help="the Vercel project's name or id (or VERCEL_PROJECT)")
    parser.add_argument("--team", default=os.environ.get("VERCEL_TEAM_ID") or None,
                        help="a team id, if the project is not on a personal account")
    parser.add_argument("--sha", help="first wait until this gh-pages commit is live")
    parser.add_argument("--delete", action="store_true",
                        help="delete; without it, only list")
    args = parser.parse_args(argv)
    token = os.environ.get("VERCEL_TOKEN")
    if not token:
        raise SystemExit("Set VERCEL_TOKEN in the environment (a token from Vercel's "
                         "Account Settings > Tokens); it is never taken as an argument.")
    if not args.project:
        raise SystemExit("Name the project: --project NAME, or VERCEL_PROJECT.")
    try:
        gone = prune(client(token, args.team), args.project, args.delete, args.sha)
    except PruneError as exc:
        print(f"  ! {exc}")
        raise SystemExit(1) from exc
    verb = "deleted" if args.delete else "would delete (dry run; add --delete)"
    print(f"{len(gone)} deployment{'' if len(gone) == 1 else 's'} {verb}:")
    for d in gone:
        print(f"  {d['uid']}  {_when(d)}  {d.get('target') or 'preview'}"
              f"  {d.get('readyState')}")


if __name__ == "__main__":
    main(sys.argv[1:])
