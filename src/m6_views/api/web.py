"""The local app's web layer, on the standard library (WSGI).

FastAPI and uvicorn served this until the ponytail audit (2026-11-01): for one
user on loopback, a dozen GET routes, one header policy and a static folder, they
brought starlette, pydantic and an event loop. This is what the app used of them:

- a router of GET routes with `{name}` path parameters (`Router`);
- query parameters read and checked, a bad one answering 422 (`Query`, `Invalid`);
- answers as bytes with a type and headers (`Reply`, `html`, `json_reply`);
- the Host check against DNS rebinding, and the security and cache headers on
  every answer, errors included (`App`);
- `/static/` files, revalidated by ETag (`App._static`).

`jobs/serve.py` runs `App` under `wsgiref`'s server, one thread a request; the
database lock in `app.py` serialises what they share.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

#: Every answer carries these (MODULE_6 §15.3 and the CSP of DECISIONS V1-23):
#: no inline script or style, nothing from another host, never framed.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}
#: Types the platform's table may not know (Windows' often lacks woff2).
_TYPES = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2",
          ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json"}


class Invalid(ValueError):
    """A query parameter the route cannot read: the caller's error, a 422."""


@dataclass
class Reply:
    status: int
    body: bytes = b""
    type: str = "text/html; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)


def html(text: str, status: int = 200) -> Reply:
    return Reply(status, text.encode("utf-8"))


def json_reply(value: Any, status: int = 200) -> Reply:
    # Decimals and dates are text on the wire, as `serialise` makes them.
    body = json.dumps(value, default=str).encode("utf-8")
    return Reply(status, body, "application/json")


class Query:
    """A request's query string, read as the routes need it."""

    def __init__(self, raw: str) -> None:
        self._values = parse_qs(raw, keep_blank_values=True)

    def text(self, name: str, default: str | None = None,
             max_length: int | None = None) -> str | None:
        value = self._values.get(name, [default])[0]
        if value is not None and max_length is not None and len(value) > max_length:
            raise Invalid(f"{name} is longer than {max_length} characters")
        return value

    def date(self, name: str) -> date | None:
        value = self.text(name)
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise Invalid(f"{name} is not a date: {value!r}") from None

    def int(self, name: str, default: int | None = None) -> int | None:
        value = self.text(name)
        if value in (None, ""):
            return default
        try:
            return int(value)
        except ValueError:
            raise Invalid(f"{name} is not a whole number: {value!r}") from None


Handler = Callable[..., Reply]


class Router:
    """GET routes, tried in the order they were added."""

    def __init__(self) -> None:
        self.routes: list[tuple[re.Pattern[str], Handler]] = []

    def get(self, pattern: str) -> Callable[[Handler], Handler]:
        rx = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

        def add(fn: Handler) -> Handler:
            self.routes.append((rx, fn))
            return fn
        return add


class App:
    """A WSGI application: the routes, the static folder and the header policy."""

    def __init__(self, routers: Iterable[Router], static: Path,
                 allowed_hosts: Iterable[str]) -> None:
        self.routes = [r for router in routers for r in router.routes]
        self.static, self.hosts = static.resolve(), set(allowed_hosts)

    def __call__(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        path = environ.get("PATH_INFO") or "/"
        reply = self._answer(environ, path)
        cache = "no-cache" if path.startswith("/static/") else "no-store"
        heads = {**SECURITY_HEADERS, "Content-Type": reply.type, "Cache-Control": cache,
                 **reply.headers}
        body = b"" if environ.get("REQUEST_METHOD") == "HEAD" else reply.body
        heads["Content-Length"] = str(len(body))
        start_response(f"{reply.status} {_REASONS.get(reply.status, '')}".rstrip(),
                       list(heads.items()))
        return [body]

    def _answer(self, environ: dict[str, Any], path: str) -> Reply:
        # DNS rebinding: a page on an attacker's name, pointed at 127.0.0.1, still
        # says whom it asked for. Port is ignored.
        host = str(environ.get("HTTP_HOST", "")).rsplit(":", 1)[0]
        if host not in self.hosts:
            return Reply(400, b"Invalid host header", "text/plain; charset=utf-8")
        if environ.get("REQUEST_METHOD") not in ("GET", "HEAD"):
            return json_reply({"detail": "Method Not Allowed"}, 405)
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):], environ)
        query = Query(environ.get("QUERY_STRING", ""))
        for rx, handler in self.routes:
            match = rx.match(path)
            if match:
                try:
                    return handler(query, **match.groupdict())
                except Invalid as exc:
                    return json_reply({"detail": str(exc)}, 422)
                except Exception:   # never a stack trace, and the headers still go
                    return Reply(500, b"Internal error", "text/plain; charset=utf-8")
        return json_reply({"detail": "Not Found"}, 404)

    def _static(self, name: str, environ: dict[str, Any]) -> Reply:
        target = (self.static / name).resolve()
        if not target.is_relative_to(self.static) or not target.is_file():
            return json_reply({"detail": "Not Found"}, 404)
        stat = target.stat()
        stamp = f"{stat.st_mtime_ns}-{stat.st_size}".encode()
        tag = '"' + hashlib.sha1(stamp).hexdigest() + '"'
        kind = (_TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0]
                or "application/octet-stream")
        if environ.get("HTTP_IF_NONE_MATCH") == tag:
            return Reply(304, b"", kind, {"ETag": tag})
        return Reply(200, target.read_bytes(), kind, {"ETag": tag})


_REASONS = {200: "OK", 304: "Not Modified", 400: "Bad Request", 404: "Not Found",
            405: "Method Not Allowed", 422: "Unprocessable Entity",
            500: "Internal Server Error"}
