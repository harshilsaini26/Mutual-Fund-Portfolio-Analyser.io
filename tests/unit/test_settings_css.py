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
