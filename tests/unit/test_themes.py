"""Three themes, four accents, three fonts, one set of tokens. DECISIONS V1-81, V1-83.

A token the light theme defines and the dark or Matrix theme forgets renders the
light colour on a dark ground: unreadable, and nothing else would notice. An
accent is a colour people read text in, so each one is held to WCAG AA on its
theme's surface.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static" / "app.css")
#: Shape and type, the same in every theme.
SHARED = {"--radius", "--radius-sm", "--font", "--mono"}
#: light (accent, strong), dark (accent, strong): the spec's values. Navy is the
#: bare `:root` and the dark block, as before.
ACCENTS = {
    "violet": ("#5b3fc4", "#4a2fa8", "#b7a6ff", "#d3c8ff"),
    "raspberry": ("#b0245e", "#8f1c4c", "#ff8fbf", "#ffb8d6"),
    "graphite": ("#3b4656", "#262f3b", "#c3cbd8", "#e1e6ee"),
}
SURFACE = {"light": "#ffffff", "dark": "#111a2b"}


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
    light = _tokens_of(_block(":root")) - SHARED
    for theme in ("dark", "matrix"):
        assert _tokens_of(_block(f':root[data-theme="{theme}"]')) >= light, theme


def test_every_accent_defines_its_tokens_on_both_themes() -> None:
    for name, (la, ls, da, ds) in ACCENTS.items():
        for theme, accent, strong in (("light", la, ls), ("dark", da, ds)):
            block = _block(f':root[data-theme="{theme}"][data-accent="{name}"]')
            assert _tokens_of(block) >= {"--accent", "--accent-strong", "--accent-soft",
                                         "--on-accent"}, (name, theme)
            assert f"--accent: {accent};" in block
            assert f"--accent-strong: {strong};" in block


def test_every_accent_reads_on_its_surface() -> None:
    for name, (la, _, da, _) in ACCENTS.items():
        assert _contrast(la, SURFACE["light"]) >= 4.5, name
        assert _contrast(da, SURFACE["dark"]) >= 4.5, name


def test_each_font_choice_sets_the_stacks() -> None:
    assert '"Atkinson Hyperlegible"' in _block(':root[data-font="atkinson"]')
    assert '"Rubik"' in _block(':root[data-font="rubik"]')
