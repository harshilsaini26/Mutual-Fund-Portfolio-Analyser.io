"""Explanations of what the site shows, and guides (DECISIONS V1-87).

`learn.yaml` holds every term and guide, each written in this project's own
words and linked to the pages it was checked against, on an allowed list of
sources. `load` refuses anything that breaks the rules, so a bad entry stops
the build and the app rather than reaching a reader:

- a source not on the list, a URL that is not `https` on that source's own
  site, a `checked` date that is missing or more than a day ahead;
- text over its length (a term's explanation 60 words, a guide's summary 25,
  a paragraph 120) and a guide outside 4 to 6 sections;
- a `[[key]]` link or a related term that names no term;
- any percentage in the tax guide: rates change with each Budget and are not
  this site's to print (invariant 8).

What the checks cannot prove is that an explanation is true. Only reading it
against its source does, which is why the content is reviewed before release.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from markupsafe import Markup, escape

LEARN_YAML = Path(__file__).with_name("learn.yaml")
GROUPS = ("Basics", "Costs", "Risk and return", "Your portfolio", "Using this site")
TAX_GUIDE = "how-gains-are-taxed"
LIMITS = {"short": 60, "summary": 25, "paragraph": 120}
LINK = re.compile(r"\[\[([a-z0-9_]+)(?:\|([^\]]+))?\]\]")
PERCENT = re.compile(r"\d+(\.\d+)?\s*%|per\s*cent", re.I)


#: Which term explains a label the builders produce. Fixed markup (the /funds/
#: headers, compare, portfolio) names its terms in the template instead.
TERMS_FOR: dict[str, dict[str, str]] = {
    "tile": {
        "return_1y": "annualised_return", "return_3y": "annualised_return",
        "return_5y": "annualised_return", "rank_3y": "category_rank",
        "worst_fall": "max_drawdown", "volatility": "volatility",
        "fund_size": "aum", "ter": "expense_ratio",
    },
    "fact": {"Category": "sebi_categories", "Plan": "direct_plan", "Fund size": "aum",
             "Benchmark": "benchmark"},
    "view": {
        "fund_growth": "nav", "fund_returns": "annualised_return",
        "fund_peers": "category_rank", "fund_drawdown": "max_drawdown",
        "fund_consistency": "rolling_returns", "fund_portfolio": "asset_mix",
    },
    "measure": {
        "Return a year": "annualised_return", "Benchmark a year": "benchmark",
        "Volatility": "volatility", "Deepest fall": "max_drawdown",
        "Sharpe ratio": "sharpe",
    },
}


class LearnError(ValueError):
    """The content breaks one of the rules above; the message names the entry."""


@dataclass(frozen=True)
class SourceRef:
    source: str
    url: str
    checked: date


@dataclass(frozen=True)
class Term:
    key: str
    title: str
    short: str
    sources: tuple[SourceRef, ...]
    related: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Guide:
    slug: str
    title: str
    group: str
    summary: str
    sections: tuple[Section, ...]
    sources: tuple[SourceRef, ...]


@dataclass(frozen=True)
class Learn:
    sources: dict[str, dict[str, Any]]
    terms: dict[str, Term]
    guides: tuple[Guide, ...]

    def source_names(self, refs: tuple[SourceRef, ...]) -> list[str]:
        """Each source's display name once, in the order first cited."""
        return list(dict.fromkeys(self.sources[r.source]["name"] for r in refs))

    def term(self, key: str) -> Term:
        """The term, or KeyError: a template naming a term that does not exist
        fails the render instead of drawing an empty explanation."""
        return self.terms[key]

    def guide(self, slug: str) -> Guide:
        for guide in self.guides:
            if guide.slug == slug:
                return guide
        raise KeyError(slug)


def words(text: str) -> int:
    """Words as a reader sees them: `[[key|label]]` counts as its label."""
    return len(LINK.sub(lambda m: m.group(2) or m.group(1), text).split())


def _refs(raw: Any, who: str, sources: dict[str, dict[str, Any]], today: date
          ) -> tuple[SourceRef, ...]:
    if not raw:
        raise LearnError(f"{who}: no source")
    out = []
    for item in raw:
        name, checked = item.get("source"), item.get("checked")
        url = str(item.get("url", ""))
        allowed = sources.get(name)
        if allowed is None:
            raise LearnError(f"{who}: {name!r} is not an allowed source")
        parts = urlparse(url)
        if parts.scheme != "https" or parts.hostname not in allowed["hosts"]:
            raise LearnError(f"{who}: {url} is not an https page on {name}'s own site")
        if not parts.path.startswith(allowed.get("path", "/")):
            raise LearnError(f"{who}: {url} is outside {allowed['path']} on {name}")
        # A day's grace: the nightly build's clock is UTC, India is ahead of it.
        if not isinstance(checked, date) or checked > today + timedelta(days=1):
            raise LearnError(
                f"{who}: {url} needs the date it was checked, not after today")
        out.append(SourceRef(name, url, checked))
    return tuple(out)


def _length(text: str, kind: str, who: str) -> str:
    if not text or words(text) > LIMITS[kind]:
        raise LearnError(f"{who}: the {kind} is empty or over {LIMITS[kind]} words")
    return text


def load(path: Path = LEARN_YAML, today: date | None = None) -> Learn:
    """The content, checked. Cached for the real file at today's date."""
    if path == LEARN_YAML and today is None:
        return _load_default()
    return _load(path, today or date.today())


@functools.cache
def _load_default() -> Learn:
    return _load(LEARN_YAML, date.today())


def _load(path: Path, today: date) -> Learn:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources: dict[str, dict[str, Any]] = doc["sources"]
    terms = {
        key: Term(key, raw["title"], _length(raw["short"], "short", key),
                  _refs(raw.get("sources"), key, sources, today),
                  tuple(raw.get("related") or ()))
        for key, raw in (doc.get("terms") or {}).items()
    }
    guides: list[Guide] = []
    for raw in doc.get("guides") or []:
        slug = raw["slug"]
        if any(g.slug == slug for g in guides):
            raise LearnError(f"{slug}: the slug is used twice")
        if raw["group"] not in GROUPS:
            raise LearnError(f"{slug}: {raw['group']!r} is not one of {GROUPS}")
        if not 4 <= len(raw["sections"]) <= 6:
            raise LearnError(f"{slug}: a guide has 4 to 6 sections")
        sections = tuple(
            Section(s["heading"],
                    tuple(_length(p, "paragraph", slug) for p in s["paragraphs"]))
            for s in raw["sections"]
        )
        guides.append(Guide(slug, raw["title"], raw["group"],
                            _length(raw["summary"], "summary", slug), sections,
                            _refs(raw.get("sources"), slug, sources, today)))
    learn = Learn(sources, terms, tuple(guides))
    _check_links(learn)
    return learn


def _check_links(learn: Learn) -> None:
    for term in learn.terms.values():
        for key in term.related:
            if key not in learn.terms:
                raise LearnError(f"{term.key}: related term {key!r} does not exist")
    for guide in learn.guides:
        text = " ".join(p for s in guide.sections for p in (s.heading, *s.paragraphs))
        for match in LINK.finditer(text):
            if match.group(1) not in learn.terms:
                raise LearnError(f"{guide.slug}: [[{match.group(1)}]] names no term")
        if guide.slug == TAX_GUIDE and PERCENT.search(text + " " + guide.summary):
            raise LearnError(f"{guide.slug}: no tax figure may be printed")


def link_terms(text: str, learn: Learn, root: str) -> Markup:
    """`text` escaped, with `[[key]]` and `[[key|label]]` as glossary links."""
    out, last = [], 0
    for match in LINK.finditer(text):
        key, label = match.group(1), match.group(2) or learn.terms[match.group(1)].title
        out.append(escape(text[last:match.start()]))
        link = Markup('<a href="{}/learn/glossary/#{}">{}</a>')
        out.append(link.format(root, key, label))
        last = match.end()
    out.append(escape(text[last:]))
    return Markup("").join(out)


def stale(learn: Learn, today: date, days: int = 365) -> list[str]:
    """Each source check older than `days`: the build logs these as warnings."""
    cutoff = today - timedelta(days=days)
    entries = [(t.key, t.sources) for t in learn.terms.values()]
    entries += [(g.slug, g.sources) for g in learn.guides]
    return [f"{who}: {r.url} checked {r.checked.isoformat()}"
            for who, refs in entries for r in refs if r.checked < cutoff]
