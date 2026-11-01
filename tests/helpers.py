"""Questions only the tests ask of the ledger's in-memory objects.

Production reads lots, positions and balances back from the ledger database;
these read the `LotBook`, `Reconciliation` and `CasContext` a test has just
built, so they live with the tests rather than on the classes (DECISIONS V1-73).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import unquote, urlsplit
from wsgiref.util import setup_testing_defaults

from src.common.types import SchemeId
from src.m1_ledger.cas.parse import CasContext
from src.m1_ledger.lots import Consumption, LotBook
from src.m1_ledger.reconcile import Reconciliation


def consumptions_for(book: LotBook, txn_ref: str) -> list[Consumption]:
    return [
        c
        for c in sorted(book.consumptions, key=lambda x: x.sequence_in_txn)
        if c.close_txn_ref == txn_ref
    ]


def closing_txn_refs(book: LotBook) -> list[str]:
    return sorted({c.close_txn_ref for c in book.consumptions})


def total_units_remaining(book: LotBook) -> Decimal:
    return sum((lot.units_remaining for lot in book.lots), Decimal(0))


def cost_basis_remaining(book: LotBook, scheme_id: str) -> Decimal:
    """Cost of the units still held, after FIFO consumption.

    Reads the tracked remainder rather than recomputing
    cost_per_unit * units_remaining, the drifting form V0-10 removed.
    """
    return sum(
        (lot.cost_remaining for lot in book.lots if lot.scheme_id == scheme_id),
        Decimal(0),
    )


def fingerprint(book: LotBook) -> str:
    """Stable hash of the derived state: PLAN.md §8.3 invariant 5, a full
    rebuild reproduces it byte for byte."""
    h = hashlib.sha256()
    for lot in sorted(book.lots, key=lambda x: x.lot_id):
        h.update(
            f"{lot.lot_id}|{lot.acquisition_date}|{lot.book_date}|"
            f"{lot.units_original}|{lot.units_remaining}|{lot.cost_total}|"
            f"{lot.cost_per_unit}|{lot.origin}|{lot.is_closed}\n".encode()
        )
    for c in sorted(book.consumptions, key=lambda x: (x.close_txn_id, x.sequence_in_txn)):
        h.update(
            f"{c.lot_id}|{c.close_txn_id}|{c.units_consumed}|{c.cost_allocated}|"
            f"{c.proceeds_net}|{c.holding_days}|{c.gain_type}|{c.gain_amount}|"
            f"{c.cost_basis_method}|{c.tax_class_at_sale}\n".encode()
        )
    return h.hexdigest()


@dataclass(frozen=True)
class GateResult:
    """MODULE_1.md §11.3. V0 does not ship while `passed` is False."""

    passed: bool
    failures: list[Reconciliation]
    excluded_scheme_ids: set[SchemeId]


def apply_gate(results: list[Reconciliation]) -> GateResult:
    """MODULE_1.md §11.3: a failing position is excluded from every aggregate."""
    failures = [r for r in results if r.status == "fail"]
    return GateResult(
        passed=not failures,
        failures=failures,
        excluded_scheme_ids={r.scheme_id for r in failures},
    )


def closing_balance(ctx: CasContext, folio: str, isin: str) -> Decimal | None:
    """The last closing balance printed for this folio-scheme."""
    found = [
        b for b in ctx.balances
        if b.folio == folio and b.scheme_raw_isin == isin and b.kind == "closing"
    ]
    return found[-1].units if found else None


def opening_balance(ctx: CasContext, folio: str, isin: str) -> Decimal | None:
    found = [
        b for b in ctx.balances
        if b.folio == folio and b.scheme_raw_isin == isin and b.kind == "opening"
    ]
    return found[0].units if found else None


class TestClient:
    """The local app, called in-process over WSGI, as FastAPI's test client was
    until the ponytail audit (2026-11-01) put the app on the standard library."""

    __test__ = False   # not a test class, whatever its name

    def __init__(self, app: Any, base_url: str = "http://127.0.0.1:8765") -> None:
        self.app, self.host = app, urlsplit(base_url).netloc

    def get(self, url: str, headers: dict[str, str] | None = None) -> Answer:
        path, _, query = url.partition("?")
        environ: dict[str, Any] = {}
        setup_testing_defaults(environ)
        environ.update(REQUEST_METHOD="GET", PATH_INFO=unquote(path), QUERY_STRING=query,
                       HTTP_HOST=self.host)
        for name, value in (headers or {}).items():
            environ["HTTP_" + name.upper().replace("-", "_")] = value
        got: dict[str, Any] = {}

        def start_response(status: str, heads: list[tuple[str, str]]) -> None:
            got["status"], got["headers"] = int(status.split()[0]), heads

        body = b"".join(self.app(environ, start_response))
        return Answer(got["status"], {k.lower(): v for k, v in got["headers"]}, body)


@dataclass
class Answer:
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content)
