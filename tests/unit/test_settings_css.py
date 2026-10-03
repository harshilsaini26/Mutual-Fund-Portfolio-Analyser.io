"""The settings' CSS: text size, density and motion. DECISIONS V1-83."""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[2] / "src" / "m6_views" / "static" / "app.css"


def test_no_text_size_is_fixed_in_pixels() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert not re.findall(r"font-size:\s*[\d.]+px", css)
    assert not re.findall(r"\bfont:\s*[\d.]+px", css)


def test_standard_text_is_todays_text() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "font: 0.875rem/1.55 var(--font)" in css  # the body, 14px today


def test_the_root_size_carries_the_choice() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r':root\[data-size="small"\]\s*\{[^}]*font-size:\s*93\.75%', css)
    assert re.search(r':root\[data-size="large"\]\s*\{[^}]*font-size:\s*112\.5%', css)


def test_compact_tightens_tables_cards_and_panels() -> None:
    css = CSS.read_text(encoding="utf-8")
    for target in ("td", ".card", ".view"):
        pattern = r'\[data-density="compact"\][^{]*' + re.escape(target)
        assert re.search(pattern, css), target


def test_motion_off_stops_every_transition_and_animation() -> None:
    css = CSS.read_text(encoding="utf-8")
    rule = re.search(r'\[data-motion="off"\][^{]*\{([^}]*)\}', css)
    assert rule and "transition: none !important" in rule.group(1)
    assert "animation: none !important" in rule.group(1)


def test_everything_that_moves_asks_one_attribute() -> None:
    static = CSS.parent
    for name in ("app.js", "charts.js"):
        text = (static / name).read_text(encoding="utf-8")
        assert "prefers-reduced-motion" not in text, name
        assert "data-motion" in text, name
    islands = static.parents[2] / "ui" / "src" / "islands.jsx"
    assert "prefers-reduced-motion" not in islands.read_text(encoding="utf-8")


def _inexact(css: str) -> list[str]:
    """rem font sizes that are not a whole or half pixel at standard text."""
    values = re.findall(r"(?:font-size:|\bfont:)[^;}]*?([\d.]+)rem", css)
    return [v for v in values if (float(v) * 32) != round(float(v) * 32)]


def test_every_text_size_is_exactly_its_old_pixel_size() -> None:
    # Each was a whole or half pixel; N/16 rem is exact in five decimals, and a
    # rounded one (0.9688 for 15.5px) renders a fraction of a pixel off.
    assert _inexact("body { font-size: 0.9688rem; }") == ["0.9688"]
    assert not _inexact(CSS.read_text(encoding="utf-8"))


def test_hidden_means_hidden_whatever_the_class() -> None:
    # `.icon-button { display: inline-grid }` beat the browser's [hidden] rule, so
    # the gear showed without scripts, opening nothing.
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"(?m)^\[hidden\]\s*\{\s*display:\s*none\s*!important;?\s*\}", css)


def test_the_settings_chips_show_keyboard_focus_like_every_other_control() -> None:
    css = CSS.read_text(encoding="utf-8")
    rule = re.search(r"\.settings__chip:has\(input:focus-visible\)\s*\{([^}]*)\}", css)
    assert rule and "var(--accent)" in rule.group(1)  # --sky is ~1.7:1 on white


def test_every_chart_axis_label_follows_the_text_size() -> None:
    charts = (CSS.parent / "charts.js").read_text(encoding="utf-8")
    labels = re.findall(r"axisLabel:\s*\{[^}]*\}", charts)
    assert labels and all("fontSize: textSize()" in label for label in labels), labels


def test_jumps_clear_both_pinned_bars() -> None:
    css = CSS.read_text(encoding="utf-8")
    padding = "scroll-padding-top: calc(var(--bar-h, 63px) + var(--nav-h, 0px) + 12px)"
    assert padding in css
    assert re.search(r":root:has\(nav\.sections\)\s*\{\s*--nav-h:\s*44px", css)
    assert re.search(r"\.sections\s*\{[^}]*position:\s*sticky", css)


def test_phones_get_full_width_charts_and_large_tap_targets() -> None:
    css = CSS.read_text(encoding="utf-8")
    block = css[css.index("@media (max-width: 720px)"):]
    assert re.search(r"\.echart--line \.echart__canvas[^{]*\{[^}]*height:\s*280px", block)
    scatter = r"\.echart--scatter \.echart__canvas[^{]*\{[^}]*height:\s*300px"
    assert re.search(scatter, block)
    assert re.search(r"\.zoom button[^{]*\{[^}]*min-height:\s*40px", block)


def test_a_mouse_can_reach_every_section_chip() -> None:
    # The chip row overflows between 721px and about 1,000px too; its scrollbar
    # may be hidden only where a finger scrolls it.
    css = CSS.read_text(encoding="utf-8")
    base = re.search(r"\.sections\s*\{([^}]*)\}", css)
    assert base and "scrollbar-width: none" not in base.group(1)
    phone = (r"@media \(max-width: 720px\)\s*\{\s*"
             r"\.sections\s*\{\s*scrollbar-width:\s*none")
    assert re.search(phone, css)


def test_charts_can_be_drawn_after_the_page_loads() -> None:
    charts = (CSS.parent / "charts.js").read_text(encoding="utf-8")
    assert re.search(r"window\.Charts\s*=\s*\{\s*draw:", charts)


def test_compare_tables_keep_the_measure_in_view_on_phones() -> None:
    css = CSS.read_text(encoding="utf-8")
    pinned = r"\.cmp table (th|td):first-child[^{]*\{[^}]*position:\s*sticky"
    assert re.search(pinned, css)


def test_a_chart_of_several_funds_keeps_its_legend_to_one_row() -> None:
    """Long fund names in a wrapping legend covered the compare chart (V1-85):
    several funds get a scrolling, truncated legend with the full name on hover."""
    charts = (CSS.parent / "charts.js").read_text(encoding="utf-8")
    many = charts[charts.index("var many ="):charts.index("o.series = c.series.map")]
    assert re.search(r'type\s*[:=]\s*"scroll"', many) and '"truncate"' in many


def test_an_explanation_stays_hidden_where_popovers_are_not_supported() -> None:
    """Hiding a closed popover comes only from the browser's own stylesheet, so a
    browser without popovers would show every explanation inline (V1-87)."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\.term-pop\s*\{[^}]*display:\s*none", css)
    assert re.search(r"\.term-pop:popover-open\s*\{[^}]*display:\s*block", css)


# --- colour and focus (UX audit, V1-88) -----------------------------------------


def _block(css: str, opener: str) -> str:
    """The body of the first rule block whose selector is exactly `opener`."""
    start = re.search(r"(?m)^" + re.escape(opener) + r"\s*\{", css)
    assert start, opener
    depth, i = 1, start.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return css[start.end():i - 1]


def _tokens(theme: str) -> dict[str, str]:
    css = CSS.read_text(encoding="utf-8")
    hexes = r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b"
    tokens = dict(re.findall(hexes, _block(css, ":root")))
    if theme != "light":
        tokens |= dict(re.findall(hexes, _block(css, f':root[data-theme="{theme}"]')))
    return tokens


def _ratio(a: str, b: str) -> float:
    def lum(h: str) -> float:
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    x, y = lum(a), lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


THEMES = ("light", "dark", "matrix")
SURFACES = ("bg", "surface", "surface-2", "surface-3")
TEXT = ("ink", "ink-soft", "ink-faint", "accent", "gain", "loss", "warn", "bench")


def test_text_tokens_meet_aa_on_every_surface() -> None:
    """WCAG AA 4.5:1 for every text colour on every surface it can sit on."""
    low = []
    for theme in THEMES:
        t = _tokens(theme)
        for fg in TEXT:
            for bg in SURFACES:
                if fg in t and bg in t and _ratio(t[fg], t[bg]) < 4.5:
                    low.append(f"{theme} {fg} on {bg} {_ratio(t[fg], t[bg]):.2f}")
    assert not low, low


def test_field_borders_meet_3_to_1() -> None:
    """WCAG 1.4.11: a field's outline is what shows where to type."""
    css = CSS.read_text(encoding="utf-8")
    for theme in THEMES:
        t = _tokens(theme)
        for bg in ("surface", "surface-2"):
            assert _ratio(t["field-line"], t[bg]) >= 3.0, (theme, bg)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        last = sel.split(",")[0].split()[-1]
        if re.search(r"\b(input|select|textarea)\b", sel) and ":" not in last:
            for decl in re.findall(r"border(?:-color)?\s*:\s*([^;]+);", body):
                if "radius" in decl:
                    continue
                ok = "--field-line" in decl or decl.strip() in ("0", "none")
                assert ok, (sel.strip(), decl)


def test_fields_have_a_focus_ring() -> None:
    css = CSS.read_text(encoding="utf-8")
    ring = re.search(r"([^{}]*a:focus-visible[^{}]*)\{", css)
    assert ring and "input:focus-visible" in ring.group(1)
    assert "textarea:focus-visible" in ring.group(1)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if re.search(r"outline:\s*none", body):
            assert re.search(r"outline:\s*(?!none)\S", body), sel.strip()


# --- type scale and prose face (V1-88) ------------------------------------------

SCALE = {
    "text-xs": "0.75rem", "text-sm": "0.8125rem", "text-md": "0.875rem",
    "text-base": "0.96875rem", "text-lead": "1.125rem", "text-h3": "1.375rem",
    "text-h2": "1.75rem", "text-display": "clamp(2.125rem, 5.4vw, 3.75rem)",
}


def test_every_font_size_is_a_token() -> None:
    """Eight sizes, none under 12px at standard text size; the reader's text-size
    setting (V1-83) scales them all through the root."""
    css = CSS.read_text(encoding="utf-8")
    root = _block(css, ":root")
    for name, value in SCALE.items():
        assert re.search(rf"--{name}:\s*{re.escape(value)};", root), name
    stray = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for value in re.findall(r"(?<!-)font-size:\s*([^;]+);", body):
            value = value.strip()
            token = re.fullmatch(r"var\(--text-[a-z0-9]+\)", value)
            if token or value in ("inherit", "1em"):
                continue
            if value.endswith("%") and re.search(r"html|:root\[data-size", sel):
                continue  # the text-size setting itself
            if value == "0.75em" and ".term" in sel:
                continue  # the "?" sizes to the label it sits beside
            stray.append(f"{sel.strip()[:50]}: {value}")
    assert not stray, stray


def test_prose_uses_the_prose_face() -> None:
    """Running text reads in Atkinson Hyperlegible while the reader's font is
    Terminess, the default; headings, figures and controls keep Terminess."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r'--font-prose:\s*"Atkinson Hyperlegible"', _block(css, ":root"))
    for font in ("rubik", "atkinson"):
        assert "--font-prose: var(--font)" in _block(css, f':root[data-font="{font}"]')
    for sel in (".learn--guide p", ".learn__term dd p", ".lede", ".public-note",
                ".term-pop__text", ".placeholder__reason", ".pf__note", ".cmp__note"):
        rules = re.findall(r"(?m)^([^{}]*" + re.escape(sel) + r"[^{}]*)\{([^{}]*)\}", css)
        assert any("font-family: var(--font-prose)" in body for _, body in rules), sel


def test_wide_screens_show_the_links_inline() -> None:
    """Wide: the nav sits inline, the Menu button gone (a menu still open when the
    window widens is closed by app.js; see test_widening_closes_an_open_menu).
    Narrow: the nav is a popover panel under the bar."""
    css = CSS.read_text(encoding="utf-8")
    wide = _block(css, "@media (min-width: 1180px)")
    assert re.search(r"\.topmenu__summary\s*\{[^}]*display:\s*none", wide)
    inline = r"\.topnav\[popover\]\s*\{[^}]*display:\s*flex[^}]*position:\s*static"
    assert re.search(inline, wide)
    narrow = _block(css, "@media (max-width: 1179px)")
    assert re.search(r"\.topnav\[popover\]\s*\{[^}]*position:\s*fixed", narrow)
    assert not re.search(r"(?m)^\s*\.topnav\s*\{\s*display:\s*none", css)


def test_the_menu_panel_opens_under_the_menu_button() -> None:
    """The button sits at the bar's left after the brand, so the panel opens from
    the left edge, not under Settings at the far right."""
    narrow = _block(CSS.read_text(encoding="utf-8"), "@media (max-width: 1179px)")
    panel = re.search(r"\.topnav\[popover\]\s*\{([^}]*)\}", narrow)
    assert panel and re.search(r"(?<![-\w])left:\s*12px", panel.group(1))
    assert "inset" not in panel.group(1)


def test_widening_closes_an_open_menu() -> None:
    """An open popover lives in the top layer, where no media query can put it back
    in the bar; app.js closes it at 1180px, first thing, before any page code."""
    script = (CSS.parent / "app.js").read_text(encoding="utf-8")
    close = script.index('window.matchMedia("(min-width: 1180px)")')
    assert "shut()" in script[close:close + 160]
    assert close < script.index("// A browser without popovers")


def test_no_rule_is_left_for_the_hero_islands() -> None:
    """The headline is plain text now (V1-88); its BlurText rule had no reader."""
    assert ".home-hero__title .blur-text" not in CSS.read_text(encoding="utf-8")


def test_phone_targets_are_40px() -> None:
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    phone = " ".join(_block(css[m.start():], "@media (max-width: 720px)")
                     for m in re.finditer(r"(?m)^@media \(max-width: 720px\)", css))
    targets = ("th button", ".leader__all", ".cmp__pick", ".pf__pick",
               ".topmenu__summary", ".colophon .topbar__link")
    for sel in targets:
        rules = [body for s, body in re.findall(r"([^{}]+)\{([^{}]*)\}", phone)
                 if sel in s.split(",") or sel in [x.strip() for x in s.split(",")]]
        assert any("min-height: 40px" in b for b in rules), sel


def test_the_hero_does_not_use_the_viewport_width() -> None:
    """100vw counts the scrollbar, so a hero sized with it is wider than the page."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if ".home-hero" in sel:
            assert "vw" not in re.sub(r"clamp\([^)]*\)", "", body), sel.strip()


def test_the_fund_table_grows_with_the_page() -> None:
    css = CSS.read_text(encoding="utf-8")
    wrap = re.search(r"\.table-card \.table-wrap\s*\{([^}]*)\}", css)
    assert wrap and "max-height" not in wrap.group(1)
    head = re.search(r"\.table-card thead th\s*\{([^}]*)\}", css)
    assert head and "position: sticky" in head.group(1) and "var(--bar-h" in head.group(1)
    # A sticky header sticks to its nearest scroll container: neither the card nor
    # (where the table fits) its wrapper may be one, or it never reaches the bar.
    card = re.search(r"(?m)^\.table-card\s*\{([^}]*)\}", css)
    assert card and "overflow: clip" in card.group(1)
    # Only where every column fits with the widest font and text size (final review:
    # at 1000-1180px the clip hid the last columns, with nothing to scroll).
    wide = _block(css, "@media (min-width: 1280px)")
    assert re.search(r"\.table-card \.table-wrap\s*\{[^}]*overflow:\s*visible", wide)
    narrow = r"@media \(min-width: 1000px\)\s*\{\s*\.table-card \.table-wrap"
    assert not re.search(narrow, css)


def test_the_public_note_wraps_so_its_link_stays_reachable() -> None:
    """The note is one sentence now; trimming it on a phone hid "About this data"
    off the edge, out of reach and out of sight when focused (final review)."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if ".public-note" in sel:
            assert "nowrap" not in body and "ellipsis" not in body, sel.strip()


def test_the_glossary_index_links_are_24px_on_phones() -> None:
    """The A to Z list wraps tightly, so WCAG 2.5.8's spacing exception does not
    cover its 22px links; each gets a 24px-plus target (V1-88 re-audit)."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    phone = " ".join(_block(css[m.start():], "@media (max-width: 720px)")
                     for m in re.finditer(r"(?m)^@media \(max-width: 720px\)", css))
    rule = re.search(r"\.learn__az a\s*\{([^}]*)\}", phone)
    assert rule and "min-height: 32px" in rule.group(1)
