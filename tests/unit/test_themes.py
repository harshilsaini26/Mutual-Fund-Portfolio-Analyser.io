"""Six themes, three fonts, one set of tokens. DECISIONS V1-81, V1-83.

Five palettes (2026-11-01) and Matrix. Each palette is a whole theme, its own
accent included, so the separate accent setting and the plain Light and Dark
themes are gone. A token Santorini (the bare :root) defines and another theme
forgets renders Santorini's colour on that theme's ground: unreadable, and
nothing else would notice. Contrast is held to WCAG AA in test_settings_css.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static" / "app.css")
#: Shape and type, the same in every theme.
SHARED = {"--radius", "--radius-sm", "--font", "--mono", "--font-prose",
          # the type scale (V1-88) is the same in every theme
          "--text-xs", "--text-sm", "--text-md", "--text-base", "--text-lead",
          "--text-h3", "--text-h2", "--text-display", "--track-label", "--track-tight",
          "--lh-body", "--lh-tight", "--lh-display"}
#: Each palette's own colours, as the reader gave them, where the theme uses them
#: unchanged (a shade too light for text on its ground is darkened, keeping its hue).
PALETTES = {
    "santorini": {"--bg": "#f7f4ec", "--cat-1": "#0077c8", "--cat-2": "#486b1f",
                  "--sky": "#f2c400"},
    "sky": {"--surface": "#fcffff", "--sky": "#0593c6"},
    "heritage": {"--bg": "#f5e6d3", "--ink": "#2b2024", "--accent": "#8b1e3f",
                 "--sky": "#d4af37"},
    "crimson": {"--bg": "#161616", "--ink": "#f2f1ed", "--sky": "#710014"},
    "midnight": {"--bg": "#0f172a", "--ink": "#ede9fe", "--accent": "#a78bfa",
                 "--sky": "#22d3ee"},
}


def _block(selector: str) -> str:
    css = CSS.read_text(encoding="utf-8")
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\n?\}", css, re.S)
    assert block, f"no {selector} block"
    return block.group(1)


def _tokens_of(block: str) -> set[str]:
    return set(re.findall(r"(?:^|;|\{)\s*(--[\w-]+):", block, re.M))


def _contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        r, g, bl = (int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
        f = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
             for c in (r, g, bl)]
        return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_theme_defines_every_colour() -> None:
    base = _tokens_of(_block(":root")) - SHARED
    for theme in ("sky", "heritage", "crimson", "midnight", "matrix"):
        assert _tokens_of(_block(f':root[data-theme="{theme}"]')) >= base, theme


def test_each_palette_carries_its_own_colours() -> None:
    for theme, colours in PALETTES.items():
        selector = ":root" if theme == "santorini" else f':root[data-theme="{theme}"]'
        block = _block(selector)
        for token, value in colours.items():
            assert f"{token}: {value};" in block, (theme, token)


def test_the_old_themes_and_accents_are_gone() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "data-accent" not in css
    for old in ("light", "dark"):
        assert f'data-theme="{old}"' not in css, old


def test_each_font_choice_sets_the_stacks() -> None:
    # Atkinson Hyperlegible is the bare :root's since the UI/UX critique (G-01);
    # Terminess, once the default, is the opt-in "Terminal".
    assert '"Terminess Nerd Font"' in _block(':root[data-font="terminess"]')
    assert '"Rubik"' in _block(':root[data-font="rubik"]')
