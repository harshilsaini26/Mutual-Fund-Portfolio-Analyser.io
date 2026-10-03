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
        if ".lp-hero" in sel:
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


def test_landing_names_wrap() -> None:
    """A long fund or company name wraps inside its card on a phone (V1-89)."""
    css = CSS.read_text(encoding="utf-8")
    for sel in (r"\.lp-fund__name", r"\.lp-row__name"):
        rule = re.search(sel + r"[^{]*\{([^}]*)\}", css)
        assert rule and "overflow-wrap: anywhere" in rule.group(1), sel


# --- the landing page's motion (V1-89) --------------------------------------------

LANDING = (".lp-", "#categories .fundmap")
TEXT_SELECTORS = ("h1", "h2", "h3", " p", "figcaption", ".lp-row__name", ".lp-fund__name",
        ".fundmap__node", ".lp-text", ".lp-hero__text", ".lp-range__head")


def _rules(css: str) -> list[tuple[list[str], str, str]]:
    """Every rule as (its enclosing at-rule preludes, its selector, its body)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: list[tuple[list[str], str, str]] = []
    stack: list[str] = []
    buf = ""
    for ch in css:
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            prelude = stack.pop() if stack else ""
            if not prelude.startswith("@"):
                out.append(([p for p in stack if p.startswith("@")], prelude, buf))
            buf = ""
        else:
            buf += ch
    return out


def _landing(rules: list[tuple[list[str], str, str]]) -> list[tuple[list[str], str, str]]:
    return [r for r in rules if any(k in r[1] for k in LANDING)
            and not any(a.startswith("@keyframes") for a in r[0])]


def test_landing_motion_is_guarded() -> None:
    """Scroll-linked pictures exist only where the browser has scroll timelines; all
    motion stops with the site's motion setting, or the device's reduced-motion
    preference when the reader has not chosen (V1-83)."""
    css = CSS.read_text(encoding="utf-8")
    rules = _rules(css)
    for ats, sel, body in rules:
        if "animation-timeline" in body or "view-timeline" in body:
            assert any("@supports (animation-timeline: view())" in a for a in ats), sel
    animated = [sel for _, sel, body in _landing(rules)
                if re.search(r"animation(-name)?\s*:\s*lp-", body)]
    assert len(animated) >= 6, animated
    off = r'\[data-motion="off"\] \*[^{]*\{[^}]*animation: none !important'
    assert re.search(off, css)
    reduce = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{([^}]*)\{"
                       r"[^}]*animation: none !important", css)
    # `*` matches no ::before or ::after, and the fund map's lines are pseudo-elements.
    assert reduce, "no reduced-motion stop rule"
    for part in (":root:not([data-motion]) *", ":root:not([data-motion]) *::before",
                 ":root:not([data-motion]) *::after"):
        assert part in [x.strip() for x in reduce.group(1).split(",")], part


def test_landing_motion_moves_marks_not_words() -> None:
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    frames = re.findall(r"@keyframes (lp-[\w-]+)\s*\{(.*?\})\s*\}", css, flags=re.S)
    assert frames
    for name, body in frames:
        props = set(re.findall(r"([\w-]+)\s*:", body))
        assert props <= {"transform", "opacity", "stroke-dashoffset", "clip-path"}, name
    for _, sel, body in _landing(_rules(css)):
        if "animation" in body:
            parts = [s.strip() for s in sel.split(",")]
            for part in parts:
                assert not any(part.endswith(t.strip()) or t in f" {part}"
                               for t in TEXT_SELECTORS), part


def test_every_scroll_animation_finishes_by_half_way() -> None:
    """Arriving by an anchor (/#about, #privacy) finds each picture complete."""
    css = CSS.read_text(encoding="utf-8")
    ranges = re.findall(r"animation-range\s*:\s*([^;]+);", css)
    assert ranges
    for value in ranges:
        end = value.split()[-2:]
        # "contain 100%" of a section taller than the screen ends late; "entry"
        # always ends by the time the section has fully entered.
        assert end[0] in ("cover", "entry"), value
        if end[0] == "cover":
            assert int(end[1].rstrip("%")) <= 50, value


def test_no_mark_is_hidden_outside_an_animation() -> None:
    """Without scroll timelines, or with motion off, every mark sits finished."""
    hidden = re.compile(r"opacity:\s*0(?![.\d])|scale[XY]?\(0[\s,)]|"
                        r"stroke-dashoffset:\s*(?!0\b)[\d.]+")
    for _, sel, body in _landing(_rules(CSS.read_text(encoding="utf-8"))):
        assert not hidden.search(body), sel


def test_landing_phone_targets() -> None:
    """On a phone every landing link is a 40px target, the pair's fund names
    included (V1-89 browser pass: they measured 15px)."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    block = r"@media \(max-width: 720px\)\s*\{((?:[^{}]*\{[^{}]*\})*)"
    phone = "".join(re.findall(block, css))
    for sel in (".lp-door a", ".lp-links a", ".lp-pair__card h3 a"):
        rules = [body for s, body in re.findall(r"([^{}]+)\{([^{}]*)\}", phone)
                 if sel in [x.strip() for x in s.split(",")]]
        assert any("min-height: 40px" in b for b in rules), sel


def test_landing_paragraphs_are_prose() -> None:
    """The spec's Visual section: display face for headings, prose face for paragraphs."""
    css = CSS.read_text(encoding="utf-8")
    rule = re.search(r"([^{}]+)\{\s*font-family: var\(--font-prose\);\s*\}", css)
    assert rule
    selectors = [x.strip() for x in rule.group(1).split(",")]
    prose = (".lp-hero__lede", ".lp-text p", ".lp-how li", ".lp-pic__note", ".lp-none")
    for sel in prose:
        assert sel in selectors, sel


def test_the_hero_needs_no_display_contents() -> None:
    """The page's own order is the order shown (words, doors, example), so the hero
    is laid out by grid areas, not by re-ordering flattened children."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if ".lp-hero" in sel or ".lp-fund" in sel or ".lp-doors" in sel:
            assert "display: contents" not in body, sel.strip()
            assert not re.search(r"(?<![\w-])order\s*:", body), sel.strip()


def test_the_leader_fold_looks_like_a_control() -> None:
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    looks = [b for b in re.findall(r"\.leaders-fold > summary\s*\{([^}]*)\}", css)
             if "cursor: pointer" in b and "var(--accent)" in b]
    assert looks
    fold = re.search(r"(?m)^\.leaders-fold\s*\{([^}]*)\}", css)
    assert fold and "margin" in fold.group(1)
    block = r"@media \(max-width: 720px\)\s*\{((?:[^{}]*\{[^{}]*\})*)"
    phone = "".join(re.findall(block, css))
    rules = [b for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", phone)
             if ".leaders-fold > summary" in [x.strip() for x in s.split(",")]]
    assert any("min-height: 40px" in b for b in rules)


def test_the_fund_cards_badge_takes_its_own_room() -> None:
    """The header card's confidence badge was laid over the card's corner, with
    90px kept free for it; "Confidence: medium" (V1-88) is twice that and ran
    over the NAV box on every fund page. It sits in the flow now, at any width,
    so no gap has to guess its length (or the reader's text size)."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    quiet = re.findall(r"\.view__header--quiet\s*\{([^}]*)\}", css)
    assert quiet and all("absolute" not in body for body in quiet)
    for body in re.findall(r"\.fundcard__top\s*\{([^}]*)\}", css):
        assert not re.search(r"padding-right:\s*[1-9]", body), body


def test_a_hover_explanation_is_a_light_hint() -> None:
    """V1-91: on hover the glossary card opens beside its label, placed by
    app.js, with nothing dimmed behind it; a click still opens it as before."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    hint = re.search(r"\.term-pop--hint\s*\{([^}]*)\}", css)
    assert hint
    for decl in ("position: fixed", "margin: 0", "inset: auto"):
        assert decl in hint.group(1), decl
    backdrop = re.search(r"\.term-pop--hint::backdrop\s*\{([^}]*)\}", css)
    assert backdrop and "transparent" in backdrop.group(1)
