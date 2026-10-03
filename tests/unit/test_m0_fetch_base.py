"""`conditional_get`'s politeness on throttling and redirects (MODULE_0 §2.3).

A scripted client stands in for the network: each URL answers from a queue, and
robots.txt answers per host. Nothing is contacted.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from src.m0_data.fetch.base import (
    DomainRateLimiter,
    FetchError,
    RobotsCache,
    conditional_get,
)


class _Client:
    def __init__(self, answers: dict[str, list[httpx.Response]],
                 robots: dict[str, str] | None = None) -> None:
        self.answers = answers
        self.robots = robots or {}
        self.calls: list[str] = []

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        assert kw.get("follow_redirects") is False, "every hop is checked here"
        self.calls.append(url)
        return self.answers[url].pop(0)

    def get(self, url: str, **kw: Any) -> httpx.Response:
        host = httpx.URL(url).host
        return httpx.Response(200, text=self.robots.get(host, ""))


def _response(status: int, url: str, **headers: str) -> httpx.Response:
    return httpx.Response(status, headers=headers, request=httpx.Request("GET", url))


def test_a_throttled_request_waits_and_tries_again() -> None:
    """429 is the host asking for time, not an answer: it is retried like a 5xx,
    waiting at least as long as Retry-After asks."""
    url = "https://a.example/file"
    client = _Client({url: [_response(429, url, **{"Retry-After": "7"}),
                            _response(200, url)]})
    slept: list[float] = []
    got = conditional_get(url, user_agent="t", client=client, retries=2,
                          sleep=slept.append)
    assert got.status_code == 200 and client.calls == [url, url]
    assert slept and slept[0] >= 7


def test_still_throttled_after_every_retry_is_a_failure() -> None:
    url = "https://a.example/file"
    client = _Client({url: [_response(429, url) for _ in range(3)]})
    with pytest.raises(FetchError, match="429"):
        conditional_get(url, user_agent="t", client=client, retries=2,
                        sleep=lambda s: None)


def test_a_redirect_to_another_host_asks_that_hosts_robots_and_limiter() -> None:
    """robots.txt and the rate limit are per host; a redirect does not inherit
    the first host's permission or budget."""
    first, second = "https://a.example/file", "https://cdn.example/file"
    client = _Client({first: [_response(302, first, location=second)],
                      second: [_response(200, second)]},
                     robots={"cdn.example": "User-agent: *\nDisallow: /"})
    with pytest.raises(FetchError, match=r"robots\.txt disallows https://cdn\.example"):
        conditional_get(first, user_agent="t", client=client, retries=0,
                        robots=RobotsCache(), sleep=lambda s: None)
    assert client.calls == [first]

    client = _Client({first: [_response(302, first, location=second)],
                      second: [_response(200, second)]})
    limiter = DomainRateLimiter(rate_per_sec=1000, burst=5)
    got = conditional_get(first, user_agent="t", client=client, retries=0,
                          robots=RobotsCache(), limiter=limiter, sleep=lambda s: None)
    assert got.status_code == 200 and client.calls == [first, second]
    assert set(limiter._tokens) == {"a.example", "cdn.example"}
