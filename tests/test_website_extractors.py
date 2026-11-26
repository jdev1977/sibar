"""The twelve website extractors on hand-made fixtures with known values (T1.4).

Fixtures are in tests/fixtures/website/. Each test states the values worked
out by reading the fixture, not values copied from a run.
"""

import json
import time
from pathlib import Path

import pytest

from extractors import base
from extractors.base import Inputs, InputFile, run_extractors
from extractors.registry import extractors_for
from extractors.website import stock_phrases

FIXTURES = Path(__file__).parent / "fixtures" / "website"
WEBSITE = extractors_for("website")


def run(name):
    """``{extractor short name: values}`` for a fixture folder."""
    results = run_extractors(WEBSITE, Inputs.from_directory(FIXTURES / name))
    return {full.split(".", 1)[1]: values for full, (_, values) in results.items()}


@pytest.fixture(scope="module")
def tailwind_landing():
    return run("tailwind-landing")


@pytest.fixture(scope="module")
def plain_css():
    return run("plain-css")


@pytest.fixture(scope="module")
def react_spa():
    return run("react-spa")


@pytest.fixture(scope="module")
def negative():
    return run("negative")


@pytest.fixture(scope="module")
def bootstrap():
    return run("bootstrap")


def subset(values, expected):
    """The expected keys of ``values``, for a readable comparison."""
    return {key: values.get(key, "<missing>") for key in expected}


def check(values, expected):
    assert subset(values, expected) == expected
    assert values["status"] == "ok"


# --- Every fixture: statuses and determinism ----------------------------------------


@pytest.mark.parametrize("name", ["tailwind-landing", "plain-css", "react-spa",
                                  "negative", "bootstrap", "hostile"])
def test_every_extractor_runs_and_is_deterministic(name):
    first = run(name)
    assert set(first) == {e.name.split(".", 1)[1] for e in WEBSITE}
    assert all(values["status"] in ("ok", "partial") for values in first.values()), {
        key: values.get("error") for key, values in first.items()}
    again = run(name)
    assert json.dumps(first) == json.dumps(again)
    for values in first.values():
        assert list(values) == sorted(values)


def test_no_files_means_no_input():
    results = run_extractors(WEBSITE, Inputs([]))
    assert {values["status"] for _, values in results.values()} == {"no-input"}
    assert all(list(values) == ["status"] for _, values in results.values())


def test_css_only_output():
    inputs = Inputs([InputFile("style.css", b"body{color:#ff0000}")])
    results = {k: v for k, (_, v) in run_extractors(WEBSITE, inputs).items()}
    assert results["website.palette"]["colors"] == ["#ff0000"]
    assert results["website.layout"] == {"status": "no-input"}
    assert results["website.accessibility"] == {"status": "no-input"}


# --- Palette -----------------------------------------------------------------------------


def test_palette_tailwind(tailwind_landing):
    check(tailwind_landing["palette"], {
        "tailwind_colors": ["gray-100", "gray-200", "gray-50", "gray-500", "gray-600",
                            "gray-900", "gray-950", "indigo-100", "indigo-500",
                            "indigo-600", "pink-400", "purple-600", "white",
                            "yellow-300"],
        "hues": ["blue", "indigo", "pink", "purple", "yellow"],
        "dominant_hue": "indigo",
        "background": "white", "background_hex": "#ffffff", "base_scheme": "light",
        "unparsed_colors": 0,
    })


def test_palette_plain_css(plain_css):
    check(plain_css["palette"], {
        "colors": ["#000000", "#121212", "#1a1a1a", "#2b2118", "#667eea", "#764ba2",
                   "#8b4513", "#cf7317", "#eeeeee", "#fdf6e3", "#ffffff"],
        "color_count": 11,
        "color_classes": ["black", "blue-mid", "brown-dark", "gray-dark", "gray-light",
                          "orange-mid", "violet-mid", "white", "yellow-light"],
        "hues": ["blue", "brown", "orange", "violet", "yellow"],
        "dominant_hue": "brown",  # brown and yellow both 3; ties go alphabetically
        "background": "yellow-light", "background_hex": "#fdf6e3",
        "base_scheme": "light", "tailwind_colors": [], "unparsed_colors": 0,
    })


def test_palette_react_wrapper_background(react_spa):
    check(react_spa["palette"], {
        "tailwind_colors": ["cyan-400", "slate-100", "slate-400", "slate-500",
                            "slate-900", "slate-950", "violet-400", "violet-500"],
        "background": "black", "background_hex": "#020617", "base_scheme": "dark",
        "dominant_hue": "blue",  # Tailwind's slate reads as a dark blue-grey
    })


def test_palette_negative(negative):
    check(negative["palette"], {
        "colors": [], "color_count": 0, "hues": [], "dominant_hue": "none",
        "background": "default", "background_hex": None, "base_scheme": "light",
        "tailwind_colors": [],
    })


def test_background_through_an_unknown_variable_is_unknown():
    inputs = Inputs([InputFile("index.html",
                               b"<style>body{background:var(--nope)}</style><p>x")])
    values = run_extractors([e for e in WEBSITE if e.name == "website.palette"],
                            inputs)["website.palette"][1]
    assert values["background"] is None and values["base_scheme"] is None
    assert values["unparsed_colors"] == 1


# --- Fonts ---------------------------------------------------------------------------------


def test_fonts_tailwind_config_and_google(tailwind_landing):
    check(tailwind_landing["fonts"], {
        "families": ["inter"], "loaded_families": ["inter"],
        "font_sources": ["google-fonts"], "primary_font": "inter",
        "primary_category": "sans", "heading_font": "same", "generic_families": [],
    })


def test_fonts_plain_css(plain_css):
    check(plain_css["fonts"], {
        "families": ["arial", "georgia", "helvetica", "lato", "playfair display"],
        "family_count": 5,
        "generic_families": ["sans-serif", "serif"],
        "loaded_families": ["lato", "playfair display"],
        "font_categories": ["sans", "serif"],
        "font_sources": ["google-fonts"],
        "primary_font": "lato", "primary_category": "sans",
        "heading_font": "playfair display", "heading_category": "serif",
        "system_stack": False,
    })


def test_fonts_none_declared(negative, react_spa):
    check(negative["fonts"], {"families": [], "primary_font": "default",
                              "heading_font": "same", "font_sources": []})
    check(react_spa["fonts"], {"families": [], "generic_families": ["sans-serif"],
                               "primary_font": "default"})


def test_fonts_system_stack_and_shorthand():
    inputs = Inputs([InputFile("a.html", b"<style>html{font:16px/1.5 -apple-system,"
                               b"BlinkMacSystemFont,'Segoe UI',sans-serif}"
                               b"@font-face{font-family:Mine;src:url(mine.woff2)}"
                               b"</style><p>x")])
    values = run_extractors([e for e in WEBSITE if e.name == "website.fonts"],
                            inputs)["website.fonts"][1]
    assert values["primary_font"] == "-apple-system"
    assert values["primary_category"] == "system" and values["system_stack"]
    assert values["font_sources"] == ["self-hosted"]
    assert "mine" in values["loaded_families"]


# --- Libraries -------------------------------------------------------------------------------


def test_libraries_cdn(tailwind_landing):
    check(tailwind_landing["libraries"], {
        "libraries": ["lucide", "tailwindcss"], "framework": "none",
        "css_framework": "tailwindcss", "tailwind_usage": "referenced",
        "tailwind_evidence": ["inline-config", "reference"], "delivery": ["cdn"],
        "cdn_hosts": ["cdn.tailwindcss.com", "fonts.googleapis.com", "unpkg.com"],
        "unrecognised": [],
    })


def test_libraries_packages(react_spa):
    check(react_spa["libraries"], {
        "libraries": ["lucide", "react", "recharts", "tailwindcss", "vite"],
        "framework": "react", "css_framework": "tailwindcss",
        "tailwind_evidence": ["config-file", "css-directive", "package"],
        "delivery": ["package"], "cdn_hosts": [],
        "unrecognised": ["@vitejs/plugin-react"],
    })


def test_libraries_plain_and_bootstrap(plain_css, bootstrap, negative):
    check(plain_css["libraries"], {
        "libraries": ["font-awesome"], "css_framework": "none", "framework": "none",
        "cdn_hosts": ["cdnjs.cloudflare.com", "fonts.googleapis.com"]})
    check(bootstrap["libraries"], {
        "libraries": ["bootstrap", "bootstrap-icons"], "css_framework": "bootstrap",
        "tailwind_usage": "none", "unrecognised": ["cdn.example.net"]})
    check(negative["libraries"], {"libraries": [], "framework": "none",
                                  "css_framework": "none", "tailwind_usage": "none"})


def test_tailwind_classes_without_a_reference():
    page = (b'<div class="flex items-center justify-between gap-4 rounded-xl '
            b'bg-indigo-600 text-sm font-semibold shadow-md">x</div>')
    values = run_extractors([e for e in WEBSITE if e.name == "website.libraries"],
                            Inputs([InputFile("a.html", page)]))
    values = values["website.libraries"][1]
    assert values["tailwind_usage"] == "classes-only"
    assert values["css_framework"] == "tailwindcss" and values["libraries"] == []


# --- Layout ------------------------------------------------------------------------------------


def test_layout_tailwind(tailwind_landing):
    check(tailwind_landing["layout"], {
        "sections": ["header", "hero", "features", "testimonials", "pricing",
                     "footer"],
        "hero": True, "landmarks": ["footer", "header", "nav", "section"],
        "layout_systems": ["flex", "grid"], "grid_columns": ["1", "3"],
        "card_groups": 1, "card_group_sizes": [3], "nav_position": "sticky",
        "max_widths_px": [768, 1280], "container_class": False,
    })


def test_layout_plain_css(plain_css):
    check(plain_css["layout"], {
        "sections": ["header", "hero", "menu", "about", "order", "footer"],
        "landmarks": ["article", "footer", "header", "main", "nav", "section"],
        "layout_systems": ["flex", "grid"], "grid_columns": ["1", "auto-fit"],
        "card_group_sizes": [4], "nav_position": "sticky",
        "max_widths_px": [1100],
    })


def test_layout_react_components(react_spa):
    check(react_spa["layout"], {
        "sections": ["header", "hero", "other", "other", "footer"],
        "landmarks": ["footer", "header", "main", "nav", "section"],
        "grid_columns": ["2", "3"], "card_groups": 0, "nav_position": "static",
        "max_widths_px": [1152],
    })


def test_layout_negative(negative):
    check(negative["layout"], {"hero": False, "landmarks": [], "layout_systems": [],
                               "card_groups": 0, "nav_position": "none",
                               "max_widths_px": []})


# --- Corners and shadows ---------------------------------------------------------------------


def test_corners_tailwind(tailwind_landing):
    check(tailwind_landing["corners-shadows"], {
        "radii": ["8px", "12px", "16px", "full"], "common_radius": "16px",
        "corner_style": "very-rounded", "pill_shapes": True, "shadow_count": 5,
        "shadow_kinds": ["soft", "subtle"], "backdrop_blur": True,
        "text_shadow": False,
    })


def test_corners_plain_css_follow_variables(plain_css):
    check(plain_css["corners-shadows"], {
        "radii": ["8px", "full"], "common_radius": "8px", "corner_style": "rounded",
        "pill_shapes": True, "shadow_count": 2, "shadow_kinds": ["soft", "subtle"],
        "backdrop_blur": False,
    })


def test_corners_react_coloured_shadow(react_spa):
    check(react_spa["corners-shadows"], {
        "radii": ["12px"], "corner_style": "rounded", "shadow_count": 1,
        "shadow_kinds": ["colored", "subtle"]})


def test_corners_bootstrap_classes_are_not_read_as_tailwind(bootstrap, negative):
    for values in (bootstrap["corners-shadows"], negative["corners-shadows"]):
        check(values, {"radii": [], "corner_style": "square", "shadow_count": 0,
                       "shadow_kinds": []})


def test_shadow_kinds_from_css():
    css = (b"<style>.a{box-shadow:4px 4px 0 #000}.b{box-shadow:0 0 20px #6366f1}"
           b".c{box-shadow:inset 0 1px 2px #000}.d{box-shadow:none}</style><p>x")
    values = run_extractors([e for e in WEBSITE if e.name ==
                             "website.corners-shadows"],
                            Inputs([InputFile("a.html", css)]))
    values = values["website.corners-shadows"][1]
    assert values["shadow_kinds"] == ["colored", "glow", "hard", "inset"]
    assert values["shadow_count"] == 3


# --- Gradients -------------------------------------------------------------------------------


def test_gradients_tailwind(tailwind_landing):
    check(tailwind_landing["gradients"], {
        "gradient_count": 2, "gradient_types": ["linear"],
        "gradient_directions": ["to-bottom-right", "to-right"],
        "gradient_hues": ["indigo", "pink", "purple", "yellow"],
        "gradient_pairs": ["indigo>purple", "pink>yellow"], "gradient_text": True,
        "gradient_targets": ["other", "text"],
    })


def test_gradients_plain_css(plain_css):
    check(plain_css["gradients"], {
        "gradient_count": 1, "gradient_directions": ["135deg"],
        "gradient_hues": ["blue", "violet"], "gradient_pairs": ["blue>violet"],
        "gradient_text": False, "gradient_targets": ["hero"],
    })


def test_gradients_react_and_none(react_spa, negative):
    check(react_spa["gradients"], {"gradient_pairs": ["violet>teal"],
                                   "gradient_text": True,
                                   "gradient_targets": ["text"]})
    check(negative["gradients"], {"gradient_count": 0, "gradient_types": [],
                                  "gradient_text": False})


def test_css_gradient_text():
    css = (b"<style>h1{background:radial-gradient(circle,red,#3b82f6);"
           b"-webkit-background-clip:text;color:transparent}</style><h1>x</h1>")
    values = run_extractors([e for e in WEBSITE if e.name == "website.gradients"],
                            Inputs([InputFile("a.html", css)]))["website.gradients"][1]
    assert values["gradient_text"] and values["gradient_types"] == ["radial"]
    assert values["gradient_pairs"] == ["red>blue"]


# --- Icons and emoji -------------------------------------------------------------------------


def test_icons_tailwind(tailwind_landing):
    check(tailwind_landing["icons-emoji"], {
        "icon_libraries": ["lucide"], "inline_svg_count": 0,
        "emoji": ["✨", "\U0001F33E", "\U0001F49A", "\U0001F680"],
        "emoji_count": 4, "emoji_led_headings": 0, "text_symbols": [],
        "icon_kinds": ["emoji", "library"], "favicon": "emoji",
    })


def test_icons_plain_and_bootstrap(plain_css, bootstrap, react_spa, negative):
    check(plain_css["icons-emoji"], {"icon_libraries": ["font-awesome"],
                                     "emoji": [], "favicon": "file",
                                     "icon_kinds": ["library"]})
    check(bootstrap["icons-emoji"], {"icon_libraries": ["bootstrap-icons"]})
    check(react_spa["icons-emoji"], {"icon_libraries": ["lucide"],
                                     "emoji": ["\U0001F4C8"], "favicon": "none"})
    check(negative["icons-emoji"], {"icon_libraries": [], "emoji": [],
                                    "emoji_count": 0, "icon_kinds": [],
                                    "favicon": "none", "text_symbols": []})


def test_emoji_led_headings_and_symbols():
    page = "<h2>\U0001F35E Our bread</h2><p>✓ Fresh → daily</p><svg></svg>"
    values = run_extractors([e for e in WEBSITE if e.name == "website.icons-emoji"],
                            Inputs([InputFile("a.html", page.encode())]))
    values = values["website.icons-emoji"][1]
    assert values["emoji_led_headings"] == 1
    assert values["text_symbols"] == ["→", "✓"]
    assert values["icon_kinds"] == ["emoji", "inline-svg", "symbol"]


# --- Stock phrases ---------------------------------------------------------------------------


def test_stock_phrases_tailwind(tailwind_landing):
    check(tailwind_landing["stock-phrases"], {
        "stock_phrases": ["construction-not-just", "cta-get-started",
                          "cta-learn-more", "placeholder-doe-names",
                          "placeholder-lorem-ipsum"],
        "stock_phrase_counts": {"construction-not-just": 1, "cta-get-started": 1,
                                "cta-learn-more": 1, "placeholder-doe-names": 1,
                                "placeholder-lorem-ipsum": 2},
        "stock_phrase_hits": 6,
        "stock_phrase_categories": ["construction", "cta", "placeholder"],
        "em_dash_count": 2, "exclamation_count": 0,
        "headings_checked": 5, "title_case_headings": 4,
    })


def test_stock_phrases_react(react_spa):
    check(react_spa["stock-phrases"], {
        "stock_phrases": ["marketing-filler-verbs"], "em_dash_count": 1,
        "headings_checked": 2, "title_case_headings": 0})


def test_stock_phrases_no_false_positives(negative, plain_css):
    check(negative["stock-phrases"], {"stock_phrases": [], "stock_phrase_hits": 0,
                                      "em_dash_count": 1})
    check(plain_css["stock-phrases"], {"stock_phrases": [], "em_dash_count": 0,
                                       "title_case_headings": 0})


def test_every_rule_has_a_source_url_and_matches_an_example():
    version, rules = stock_phrases.load_rules()
    assert version >= 1 and len(rules) >= 25
    examples = {
        "placeholder-bracketed": "[insert photo here]",
        "stat-round-plus": "10,000+ happy bakers",
        "marketing-faster-smarter": "build faster",
        "construction-no-no-just": "no fuss, no waiting, just bread",
    }
    for rule_id, _, regex in rules:
        if rule_id in examples:
            assert regex.search(examples[rule_id]), rule_id


@pytest.mark.parametrize("pattern", ["a*", "(?:ab)+", "x{1,500}", "(ab){2,3}",
                                     r"(a)\1", "x{3,}", "(?P<n>a)(?P=n)"])
def test_unsafe_patterns_are_refused(pattern):
    with pytest.raises(stock_phrases.RuleError):
        stock_phrases.check_pattern(pattern)


def test_rules_file_problems_are_refused(tmp_path):
    bad = tmp_path / "rules.json"
    bad.write_text(json.dumps({"version": 1, "sources": {}, "rules": [
        {"id": "x", "source": "nowhere", "phrases": ["a"]}]}))
    with pytest.raises(stock_phrases.RuleError):
        stock_phrases.load_rules(bad)


def test_title_case():
    assert stock_phrases.is_title_case("Lightning Fast Delivery")
    assert stock_phrases.is_title_case("The Art of Slow Bread")
    assert not stock_phrases.is_title_case("What our customers say")
    assert not stock_phrases.is_title_case("ABOUT THE BAKERY")
    assert not stock_phrases.is_title_case("Two Words")


# --- File structure --------------------------------------------------------------------------


def test_file_structure(tailwind_landing, plain_css, react_spa):
    check(tailwind_landing["file-structure"], {
        "file_count": 1, "file_kinds": {"html": 1}, "structure": "single-html",
        "folders": [], "entry_file": "index.html", "inline_script_blocks": 2,
        "inline_style_blocks": 0, "external_scripts": 2, "external_stylesheets": 1})
    check(plain_css["file-structure"], {
        "file_count": 4, "file_kinds": {"css": 1, "html": 1, "js": 1, "svg": 1},
        "structure": "html-css-js", "folders": ["css", "img", "js"], "max_depth": 1,
        "external_scripts": 1, "external_stylesheets": 2, "has_package_json": False})
    check(react_spa["file-structure"], {
        "file_count": 6,
        "file_kinds": {"css": 1, "html": 1, "js": 1, "json": 1, "jsx": 2},
        "structure": "component-project", "folders": ["src"],
        "has_package_json": True, "has_build_config": True})


def test_file_structure_counts_skipped_files(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "MAX_FILE_BYTES", 5)
    (tmp_path / "index.html").write_text("<p>hello world</p>")
    (tmp_path / "a.css").write_text("a{}")
    results = run_extractors(WEBSITE, Inputs.from_directory(tmp_path))
    structure = results["website.file-structure"][1]
    assert structure["status"] == "partial" and structure["skipped_files"] == 1
    assert structure["file_count"] == 2 and structure["structure"] == "html-css"


# --- Responsiveness ---------------------------------------------------------------------------


def test_responsiveness(tailwind_landing, plain_css, react_spa, negative):
    check(tailwind_landing["responsiveness"], {
        "viewport_meta": "device-width", "width_media_queries": 0,
        "tailwind_breakpoints": ["md"], "media_query_style": "mobile-first"})
    check(plain_css["responsiveness"], {
        "viewport_meta": "device-width", "width_media_queries": 2,
        "breakpoints_px": [480, 768], "media_query_style": "desktop-first",
        "fluid_techniques": ["auto-fit-grid", "clamp", "viewport-units"],
        "responsive_images": False})
    check(react_spa["responsiveness"], {"tailwind_breakpoints": ["sm", "lg"]})
    check(negative["responsiveness"], {
        "viewport_meta": "absent", "width_media_queries": 0, "breakpoints_px": [],
        "media_query_style": "none", "fluid_techniques": []})


def test_range_media_queries():
    css = b"<style>@media (width >= 40rem){a{b:c}} @media (900px > width){a{b:c}}" \
          b"</style><p>x"
    values = run_extractors([e for e in WEBSITE if e.name ==
                             "website.responsiveness"],
                            Inputs([InputFile("a.html", css)]))
    values = values["website.responsiveness"][1]
    assert values["breakpoints_px"] == [640, 900]
    assert values["media_query_style"] == "mixed"


# --- Dark mode --------------------------------------------------------------------------------


def test_dark_mode(tailwind_landing, plain_css, react_spa, negative):
    check(tailwind_landing["dark-mode"], {
        "dark_mode": "toggle",
        "mechanisms": ["tailwind-class-strategy", "tailwind-dark-variant",
                       "toggle-script"],
        "theme_toggle": True})
    check(plain_css["dark-mode"], {
        "dark_mode": "both",
        "mechanisms": ["dark-class-selector", "prefers-color-scheme-css",
                       "toggle-script"],
        "theme_toggle": True})
    check(react_spa["dark-mode"], {"dark_mode": "dark-only", "mechanisms": [],
                                   "theme_toggle": False})
    check(negative["dark-mode"], {"dark_mode": "none", "mechanisms": [],
                                  "theme_toggle": False})


# --- Accessibility -----------------------------------------------------------------------------


def test_accessibility_tailwind(tailwind_landing):
    check(tailwind_landing["accessibility"], {
        "html_lang": "present", "lang": "en", "images": 1, "images_missing_alt": 1,
        "alt_coverage": "none", "h1_count": 1, "heading_levels": [1, 2, 3],
        "heading_skips": 1, "main_landmark": False, "skip_link": False,
        "form_controls": 1, "unlabelled_controls": 1, "buttons_without_name": 1,
        "generic_link_text": 0, "focus_styles": True, "reduced_motion": False,
        "outline_removed": False})


def test_accessibility_plain_css(plain_css):
    check(plain_css["accessibility"], {
        "images": 4, "images_missing_alt": 0, "images_empty_alt": 1,
        "alt_coverage": "all", "heading_levels": [1, 2, 3], "heading_skips": 0,
        "main_landmark": True, "skip_link": True, "form_controls": 3,
        "unlabelled_controls": 1, "buttons_without_name": 0, "generic_link_text": 1,
        "aria_attributes": 1, "focus_styles": True, "reduced_motion": True})


def test_accessibility_negative_and_react(negative, react_spa):
    check(negative["accessibility"], {
        "html_lang": "absent", "lang": None, "alt_coverage": "all",
        "main_landmark": False, "focus_styles": False, "form_controls": 0})
    check(react_spa["accessibility"], {
        "alt_coverage": "no-images", "main_landmark": True, "h1_count": 1,
        "heading_skips": 0, "aria_attributes": 1})


# --- Hostile input --------------------------------------------------------------------------------


HOSTILE = {
    "unclosed-tags.html": b"<a " * 100_000,
    "deep.html": b"<div><section>" * 50_000,
    "attributes.html": b"<p " + b"data-x='1' " * 100_000 + b">",
    "nested.css": b"a{b:" + b"(" * 200_000,
    "rules.css": b".a{color:red}" * 100_000,
    "comments.js": b"/*" * 300_000,
    "strings.jsx": b"<div className={`" * 50_000,
    "binary.html": bytes(range(256)) * 4000,
    "emoji.html": "\U0001F35E‍".encode() * 100_000,
    "classes.html": b'<div class="' + b"bg-red-500 rounded-xl " * 50_000 + b'">',
}


def test_hostile_input_finishes_without_errors(tmp_path):
    for name, data in HOSTILE.items():
        (tmp_path / name).write_bytes(data)
    start = time.perf_counter()
    results = run_extractors(WEBSITE, Inputs.from_directory(tmp_path))
    elapsed = time.perf_counter() - start
    assert elapsed < 60, elapsed
    assert all(values["status"] in ("ok", "partial") for _, values in
               results.values()), {k: v.get("error") for k, (_, v) in results.items()}


def test_files_over_the_size_limit_are_skipped(tmp_path):
    (tmp_path / "huge.html").write_bytes(b"<p>x</p>" * (base.MAX_FILE_BYTES // 8 + 1))
    results = run_extractors(WEBSITE, Inputs.from_directory(tmp_path))
    palette = results["website.palette"][1]
    assert palette == {"skipped_files": 1, "status": "no-input"}
    structure = results["website.file-structure"][1]
    assert structure["status"] == "partial" and structure["file_count"] == 1


def test_meta_tags_in_head_are_read():
    page = (b'<html><head><meta name="theme-color" content="#336699">'
            b'<meta name="color-scheme" content="light dark"></head><body><p>x</p>'
            b"</body></html>")
    results = run_extractors(WEBSITE, Inputs([InputFile("index.html", page)]))
    assert results["website.palette"][1]["colors"] == ["#336699"]
    assert results["website.dark-mode"][1]["mechanisms"] == ["color-scheme-property"]
    assert results["website.dark-mode"][1]["dark_mode"] == "system"


def test_fontsource_imports():
    script = b'import "@fontsource/dm-sans/400.css";\nimport "@fontsource-variable/inter";'
    inputs = Inputs([InputFile("index.html", b"<p>x</p>"),
                     InputFile("main.js", script)])
    values = run_extractors([e for e in WEBSITE if e.name == "website.fonts"],
                            inputs)["website.fonts"][1]
    assert values["font_sources"] == ["fontsource"]
    assert values["loaded_families"] == ["dm sans", "inter"]
