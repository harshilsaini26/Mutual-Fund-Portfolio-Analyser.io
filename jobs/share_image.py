"""Share previews: the picture a link shows on WhatsApp or Twitter. UI/UX critique G-11.

A fund page's `share.png` (1200x630, Open Graph's size) carries the fund's name and
category, its three-year return and rank, and a line of its price; `site_card` is
the one for every other page. Drawn with Pillow from the site's own Atkinson
Hyperlegible, which has no ₹ -- so no figure here is in rupees. Every figure is a
label the build already formatted (§16.4): nothing is computed here.

Kept small (an adaptive 48-colour palette), since a build makes one per fund.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CARD_SIZE = (1200, 630)
FONTS = Path(__file__).resolve().parents[1] / "src" / "m6_views" / "static" / "fonts"
REGULAR = FONTS / "atkinson-hyperlegible-latin-400-normal.woff2"
BOLD = FONTS / "atkinson-hyperlegible-latin-700-normal.woff2"

GROUND, INK, SOFT, NAVY, RULE, FILL = (
    "#f5f7fb", "#0f1b2d", "#46566c", "#134585", "#c8d2e0", "#dde6f3")
ADDRESS = "didmysipwork.vercel.app"
LEFT, RIGHT = 80, 1120


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD if bold else REGULAR), size)


def _lines(text: str, font: ImageFont.FreeTypeFont, width: int, most: int) -> list[str]:
    """`text` wrapped to `width`, at most `most` lines, the last cut with an ellipsis."""
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(f"{lines[-1]} {word}") <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    if len(lines) > most:
        lines = lines[:most]
        while lines[-1] and font.getlength(lines[-1] + "…") > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def _brand(draw: ImageDraw.ImageDraw) -> None:
    """The site's mark (icons.html "logo") and its name, top left."""
    x, y, s = LEFT, 56, 2.2
    draw.ellipse([x + 3 * s, y + 3 * s, x + 18 * s, y + 18 * s], outline=NAVY, width=5)
    draw.line([x + 16 * s, y + 16 * s, x + 21 * s, y + 21 * s], fill=NAVY, width=6)
    for bx, top in ((7.5, 11.5), (10.5, 7.5), (13.5, 9.5)):
        draw.line([x + bx * s, y + top * s, x + bx * s, y + 13.5 * s], fill=NAVY, width=4)
    draw.text((x + 64, y + 6), "Look-through", font=_font(True, 30), fill=NAVY)


def _footer(draw: ImageDraw.ImageDraw) -> None:
    draw.line([LEFT, 572, RIGHT, 572], fill=RULE, width=2)
    draw.text((LEFT, 586), f"{ADDRESS}  ·  Descriptive, not advice",
              font=_font(False, 22), fill=SOFT)


def _spark(draw: ImageDraw.ImageDraw, values: Sequence[Decimal],
           box: tuple[int, int, int, int]) -> None:
    """A line of the fund's price across `box`, its area lightly filled."""
    if len(values) < 2:
        return
    x0, y0, x1, y1 = box
    low, high = min(values), max(values)
    span = (high - low) or Decimal(1)
    step = (x1 - x0) / (len(values) - 1)
    points = [(x0 + i * step, float(y1 - (v - low) / span * (y1 - y0)))
              for i, v in enumerate(values)]
    draw.polygon([(x0, y1), *points, (x1, y1)], fill=FILL)
    draw.line(points, fill=NAVY, width=4, joint="curve")


def _save(img: Image.Image, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("P", palette=Image.Palette.ADAPTIVE, colors=48).save(out, optimize=True)


def fund_card(out: Path, name: str, detail: str, figure: str | None,
              rank: str | None, prices: Sequence[Decimal]) -> None:
    """One fund's preview. `figure` and `rank` are labels already written ("+15.4% a
    year over 3 years", "10th of 37 in its category"); None leaves the line out."""
    img = Image.new("RGB", CARD_SIZE, GROUND)
    draw = ImageDraw.Draw(img)
    _brand(draw)
    big = _font(True, 54)
    y = 140
    for line in _lines(name, big, RIGHT - LEFT, 2):
        draw.text((LEFT, y), line, font=big, fill=INK)
        y += 64
    draw.text((LEFT, y + 6), detail, font=_font(False, 28), fill=SOFT)
    y += 62
    if figure:
        draw.text((LEFT, y), figure, font=_font(True, 46), fill=NAVY)
        y += 58
    if rank:
        draw.text((LEFT, y), rank, font=_font(False, 28), fill=SOFT)
    _spark(draw, prices, (640, 420, RIGHT, 548))
    _footer(draw)
    _save(img, out)


def site_card(out: Path, funds: int) -> None:
    """The preview for every page that is not a fund's own."""
    img = Image.new("RGB", CARD_SIZE, GROUND)
    draw = ImageDraw.Draw(img)
    _brand(draw)
    draw.text((LEFT, 170), "Did my SIP work?", font=_font(True, 84), fill=INK)
    sub = _font(False, 34)
    y = 300
    for line in _lines(f"See what each of {funds:,} Indian mutual funds owns, and how it "
                       "has done beside the funds that do the same job.", sub, 980, 3):
        draw.text((LEFT, y), line, font=sub, fill=SOFT)
        y += 46
    _footer(draw)
    _save(img, out)


def icon_png(out: Path, size: int) -> None:
    """The site's mark on its navy square, as favicon.svg draws it: for the web
    manifest and an iPhone's home screen, which want pictures, not SVG."""
    scale = size / 24
    img = Image.new("RGB", (size, size), NAVY)
    draw = ImageDraw.Draw(img)
    w = max(2, round(1.9 * scale))

    def at(x: float, y: float) -> tuple[float, float]:
        return x * scale, y * scale

    draw.ellipse([*at(4.5, 4.5), *at(16.5, 16.5)], outline="#ffffff", width=w)
    draw.line([at(15, 15), at(19.5, 19.5)], fill="#ffffff", width=w)
    for x, top in ((8, 11.4), (10.5, 8), (13, 9.8)):
        draw.line([at(x, top), at(x, 13)], fill="#ffffff", width=w)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)


__all__ = ["CARD_SIZE", "fund_card", "icon_png", "site_card"]
