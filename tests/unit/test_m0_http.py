"""The fetch layer's HTTP client: the standard library, not httpx (ponytail audit,
2026-11-01). Driven against a real server on localhost; nothing else is contacted.

It must answer as `conditional_get` expects: a status is an answer, never an
exception (304, 404 and 5xx included); a redirect is returned, not followed, so
each hop gets its own robots.txt check; and only a network failure raises.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from src.m0_data.fetch.base import HTTP, HttpError, HttpStatusError, Response


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:   # quiet
        pass

    def _send(self, status: int, body: bytes = b"", **headers: str) -> None:
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k.replace("_", "-"), v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/ok":
            self._send(200, "café".encode(), Content_Type="text/plain; charset=utf-8",
                       ETag='"v1"')
        elif self.path == "/moved":
            self._send(302, Location="/ok")
        elif self.path == "/same":
            self._send(304)
        else:
            self._send(404, b"no")

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self._send(200, json.dumps({"got": json.loads(body),
                                    "type": self.headers["Content-Type"]}).encode())


@pytest.fixture(scope="module")
def base() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_an_answer_carries_status_headers_and_body(base: str) -> None:
    r = HTTP.request("GET", f"{base}/ok", headers={"User-Agent": "t"}, timeout=5)
    assert r.status_code == 200 and r.content == "café".encode()
    assert r.text == "café" and r.headers.get("etag") == '"v1"'
    assert r.url == f"{base}/ok"


def test_a_redirect_is_returned_not_followed(base: str) -> None:
    r = HTTP.request("GET", f"{base}/moved", timeout=5, follow_redirects=False)
    assert r.status_code == 302 and r.headers.get("location") == "/ok"


def test_a_status_is_an_answer_never_an_exception(base: str) -> None:
    assert HTTP.request("GET", f"{base}/same", timeout=5).status_code == 304
    gone = HTTP.get(f"{base}/missing", timeout=5)
    assert gone.status_code == 404
    with pytest.raises(HttpStatusError) as err:
        gone.raise_for_status()
    assert err.value.response.status_code == 404
    HTTP.get(f"{base}/ok", timeout=5).raise_for_status()   # 2xx: nothing raised


def test_a_json_body_is_sent_as_json(base: str) -> None:
    r = HTTP.request("POST", f"{base}/api", json={"a": 1}, timeout=5)
    assert r.json() == {"got": {"a": 1}, "type": "application/json"}


def test_only_a_network_failure_raises() -> None:
    with pytest.raises(HttpError):
        HTTP.get("http://127.0.0.1:9/", timeout=2)   # nothing listens on port 9


def test_a_response_can_be_made_by_hand_for_a_test() -> None:
    r = Response(200, b'{"x": 2}', {"Content-Type": "application/json"}, "https://x/")
    assert r.json() == {"x": 2} and r.headers.get("content-type") == "application/json"
