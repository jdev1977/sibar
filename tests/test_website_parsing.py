"""The website extractors' readers: HTML, CSS, JavaScript, colours,
Tailwind utilities and the library catalogue (T1.4)."""

import time

import pytest
import tinycss2

from extractors.website import catalog, colors, tailwind
from extractors.website.css import parse_css, parse_style_attribute
from extractors.website.emoji import find_emoji
from extractors.website.html import parse_html
from extractors.website.js import looks_like_prose, scan

# --- HTML ----------------------------------------------------------------------


def test_html_tree_attributes_and_text():
    doc = parse_html('<!doctype html><html lang=en><head><title>A &amp; B</title>'
                     '<style>a{}</style></head><body><p>one<p>two'
                     '<div id="x" class="a  b">in <b>bold</b> tail</div>'
                     '<img src=a.png alt=""><ul><li>1<li>2</ul></body></html>')
    tags = [e.tag for e in doc.elements]
    assert tags == ["html", "head", "title", "style", "body", "p", "p", "div", "b",
                    "img", "ul", "li", "li"]
    div = doc.find("div")[0]
    assert div.attrs == {"id": "x", "class": "a  b"} and div.classes == ["a", "b"]
    assert doc.elements[div.parent].tag == "body"  # <p> closed by <div>
    assert doc.text_of(div) == "in bold tail"
    assert doc.find("img")[0].attrs["alt"] == ""
    assert [doc.elements[e.parent].tag for e in doc.find("li")] == ["ul", "ul"]
    assert doc.copy_texts() == ["one", "two", "in", "bold", "tail", "1", "2", "A & B"]
    assert not doc.unterminated


def test_html_raw_text_and_comments_hide_markup():
    doc = parse_html("<script>if (a<b) document.write('<div>')</script><!-- <p> -->"
                     "<STYLE>p{}</STYLE ><p>x</p>")
    assert [e.tag for e in doc.elements] == ["script", "style", "p"]
    assert doc.raws[0][1] == "if (a<b) document.write('<div>')"


def test_jsx_mode():
    doc = parse_html('function App() { const ok = a < b; return (<div className="p-4 '
                     'bg-white" onClick={() => go(a > b)}><Button>Go {name}</Button>'
                     '<label htmlFor="e">Email</label>'
                     '<p className={clsx("m-2", on && "flex")}>{t}</p></div>); }',
                     jsx=True)
    div, button, label, p = doc.elements
    assert div.classes == ["p-4", "bg-white"]
    assert button.component and button.tag == "button"
    assert label.attrs["for"] == "e"
    assert p.classes == ["m-2", "flex"]
    assert doc.copy_texts() == ["Go", "Email"]


@pytest.mark.parametrize("text", [
    "<a " * 50_000, "</" * 200_000, "<!" * 200_000, "<!--" + "x" * 500_000,
    "<div>" * 200_000, "<a b='" + "x" * 500_000, "<" * 500_000, "&#" * 200_000,
    "<script>" + "</scrip" * 100_000, '<a x={' * 100_000,
])
def test_hostile_html_parses_quickly(text):
    start = time.perf_counter()
    for jsx in (False, True):
        parse_html(text, jsx=jsx)
    assert time.perf_counter() - start < 5


def test_element_and_depth_limits(monkeypatch):
    from extractors.website import html
    monkeypatch.setattr(html, "MAX_ELEMENTS", 10)
    doc = parse_html("<i>" * 50)
    assert len(doc.elements) == 10 and doc.truncated
    deep = parse_html("<div>" * 2000)
    assert max(e.depth for e in deep.elements) <= html.MAX_DEPTH


# --- CSS -----------------------------------------------------------------------


def test_css_declarations_with_context():
    sheet = parse_css('@import url("a.css"); @import "b.css";'
                      ":root{--brand:#6366f1}"
                      "/* body{color:red} */"
                      "@media (max-width:600px){ .x{ padding:1rem } }"
                      ".card{border-radius:8px; &:hover{box-shadow:0 0 4px red}}"
                      "@font-face{font-family:Foo;src:url(f.woff2)}"
                      "@tailwind base; .btn{@apply px-4 rounded-lg}", "s.css")
    found = [(d.prop, d.text, d.selector, d.media) for d in sheet.declarations]
    assert found == [
        ("--brand", "#6366f1", ":root", ()),
        ("padding", "1rem", ".x", ("media (max-width:600px)",)),
        ("border-radius", "8px", ".card", ()),
        ("box-shadow", "0 0 4px red", ".card:hover", ()),
        ("font-family", "Foo", "@font-face", ()),
        ("src", "url(f.woff2)", "@font-face", ()),
    ]
    assert sheet.imports == ["a.css", "b.css"]
    assert sheet.applied == ["px-4", "rounded-lg"]


def test_preprocessor_variables_count_as_custom_properties():
    sheet = parse_css("$brand: #ff0000;\n.a { color: $brand; }", "s.scss",
                      preprocessor=True)
    assert sheet.declarations[0].prop == "--brand"
    assert sheet.declarations[0].text == "#ff0000"


def test_style_attribute():
    declarations = parse_style_attribute("color: red; padding: 2px", "a", None)
    assert [(d.prop, d.text) for d in declarations] == [("color", "red"),
                                                       ("padding", "2px")]


@pytest.mark.parametrize("text", [
    "a{b:" + "(" * 100_000 + "}", "a{" * 20_000, '"' * 500_000,
    "a{b:url(" * 50_000, "@media x{" * 20_000, "a{color:" + "rgb(" * 50_000,
])
def test_hostile_css_parses_quickly(text):
    start = time.perf_counter()
    parse_css(text, "x.css")
    assert time.perf_counter() - start < 5


# --- JavaScript ------------------------------------------------------------------


def test_js_scan_finds_imports_classes_markup_and_prose():
    script = scan('import React from "react"; import "aos/dist/aos.css";\n'
                  "const x = require('lodash'); // import 'nope'\n"
                  "/* 'block' */ el.innerHTML = `<li class=\"p-2 ${c}\">${t}</li>`;\n"
                  "el.className = 'flex gap-4'; el.classList.toggle(\"dark\");\n"
                  "const s = \"Fresh bread, every morning\"; const bad = \"open\n"
                  "const m = import('./m.js'); export { a } from './b';")
    assert script.imports() == ["react", "aos/dist/aos.css", "lodash", "./m.js",
                                "./b"]
    assert script.class_strings() == ["flex gap-4", "dark"]
    assert script.html_strings() == ['<li class="p-2  "> </li>']
    assert "Fresh bread, every morning" in script.prose_strings()


@pytest.mark.parametrize("text,expected", [
    ("Get started", True), ("Menu", True), ("flex items-center gap-4", False),
    ("useState", False), ("https://example.com/a b", False), ("#fff", False),
    ("Hello, world!", True), ("\U0001F35E", True), ("a.b.c", False),
])
def test_prose(text, expected):
    assert looks_like_prose(text) is expected


@pytest.mark.parametrize("text", [
    "/*" * 200_000, '"' * 500_000, "`" + "x" * 500_000, "'\\" * 200_000,
    "import " * 100_000,
])
def test_hostile_js_scans_quickly(text):
    start = time.perf_counter()
    script = scan(text)
    script.imports(), script.class_strings(), script.prose_strings()
    assert time.perf_counter() - start < 5


# --- Colours -----------------------------------------------------------------------


def function(text):
    return colors.parse_function(tinycss2.parse_one_component_value(text))


@pytest.mark.parametrize("text,expected", [
    ("rgb(255 0 0 / 50%)", ("#ff0000", 0.5)), ("rgba(0,0,0,.5)", ("#000000", 0.5)),
    ("hsl(240 100% 50%)", ("#0000ff", 1.0)), ("hsl(120deg,100%,25%)", ("#008000", 1.0)),
    ("hwb(0 0% 0%)", ("#ff0000", 1.0)), ("rgb(100% 0% 0%)", ("#ff0000", 1.0)),
    ("oklch(62.3% 0.214 259.815)", ("#2b7fff", 1.0)),
    ("oklab(1 0 0)", ("#ffffff", 1.0)), ("rgb(var(--x))", None),
    ("lab(50 0 0)", None),
])
def test_colour_functions(text, expected):
    assert function(text) == expected


@pytest.mark.parametrize("hex_color,expected", [
    ("#ffffff", "white"), ("#000000", "black"), ("#6366f1", "indigo-mid"),
    ("#4f46e5", "indigo-mid"), ("#a855f7", "purple-mid"), ("#8b5cf6", "violet-mid"),
    ("#3b82f6", "blue-mid"), ("#f59e0b", "orange-mid"), ("#8b4513", "brown-dark"),
    ("#fdf6e3", "yellow-light"), ("#6b7280", "gray-mid"), ("#f9fafb", "white"),
    ("#0f172a", "black"), ("#111111", "black"), ("#ef4444", "red-mid"),
    ("#64748b", "gray-mid"), ("#334155", "gray-dark"), ("#1e3a8a", "blue-dark"),
    ("#14213d", "blue-dark"), ("#667eea", "blue-mid"),
    ("#10b981", "green-mid"), ("#14b8a6", "teal-mid"), ("#ec4899", "pink-mid"),
])
def test_colour_classes(hex_color, expected):
    assert colors.classify(hex_color) == expected


def test_hex_and_named():
    assert colors.parse_hex("#ABC") == ("#aabbcc", 1.0)
    assert colors.parse_hex("#11223380")[1] == pytest.approx(128 / 255)
    assert colors.parse_hex("#12345") is None and colors.parse_hex("#ggg") is None
    assert colors.named("RebeccaPurple") == "#663399"
    assert len(colors.NAMED) == 148


# --- Tailwind ------------------------------------------------------------------------


def test_tailwind_utilities():
    u = tailwind.split("md:hover:!bg-indigo-600/90")
    assert u.variants == ("md", "hover") and u.base == "bg-indigo-600/90"
    assert tailwind.color(tailwind.split("bg-indigo-600/90")) == (
        "bg", "indigo-600", "#4f46e5")
    assert tailwind.color(tailwind.split("text-xl")) is None
    assert tailwind.color(tailwind.split("border-t-[#ff0000]"))[2] == "#ff0000"
    assert tailwind.radius(tailwind.split("rounded-2xl")) == 16
    assert tailwind.radius(tailwind.split("rounded-t-lg")) == 8
    assert tailwind.radius(tailwind.split("rounded-full")) == "full"
    assert tailwind.radius(tailwind.split("rounded")) == 4
    assert tailwind.radius(tailwind.split("rounded-[10px]")) == "10px"
    assert tailwind.shadow(tailwind.split("shadow-xl")) == "soft"
    assert tailwind.gradient(tailwind.split("bg-gradient-to-br")) == (
        "linear", "to-bottom-right")
    assert tailwind.font(tailwind.split("font-['Playfair_Display']")) == \
        "Playfair Display"
    assert tailwind.font(tailwind.split("font-bold")) is None
    assert tailwind.split("group-[.is-open]:block").variants == ("group-[.is-open]",)
    assert tailwind.split("x" * 300) is None


# --- Catalogue and emoji ----------------------------------------------------------------


@pytest.mark.parametrize("target,kind,expected", [
    ("https://cdn.tailwindcss.com?plugins=forms", "script", ("tailwindcss", "cdn", None)),
    ("https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4", "script",
     ("tailwindcss", "cdn", None)),
    ("https://unpkg.com/aos@2.3.1/dist/aos.css", "link", ("aos", "cdn", None)),
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css", "link",
     ("font-awesome", "cdn", None)),
    ("https://fonts.googleapis.com/css2?family=Inter", "link", (None, "cdn", None)),
    ("js/jquery-3.7.1.min.js", "script", ("jquery", "local", None)),
    ("react-dom/client", "module", ("react", "package", None)),
    ("./App", "module", (None, "local", None)),
    ("@/components/ui/button", "module", (None, "package", None)),
    ("https://example.org/x.js", "script", (None, "cdn", "example.org")),
    ("left-pad", "package", (None, "package", "left-pad")),
    ("data:text/javascript,1", "script", (None, "other", None)),
])
def test_catalogue(target, kind, expected):
    assert catalog.resolve(target, kind) == expected


def test_emoji_sequences_and_symbols():
    text = ("Fresh \U0001F35E and ☕ ❤️ \U0001F469‍\U0001F4BB "
            "\U0001F44D\U0001F3FD \U0001F1EC\U0001F1E7 1️⃣ ✓ → "
            "© ™")
    emoji, symbols = find_emoji(text)
    assert emoji == ["\U0001F35E", "☕", "❤️",
                     "\U0001F469‍\U0001F4BB", "\U0001F44D\U0001F3FD",
                     "\U0001F1EC\U0001F1E7", "1️⃣"]
    assert symbols == ["✓", "→"]


def test_hostile_file_names_and_jsx_braces_are_quick():
    start = time.perf_counter()
    assert catalog.resolve("js/a" + "-1.1" * 60 + "!.js", "script")[0] is None
    assert catalog.resolve("vendor/bootstrap.bundle.min.js", "script")[0] == \
        "bootstrap"
    parse_html("<p>" + "{" * 50_000 + "x" + "}" * 50_000 + "</p>", jsx=True)
    assert time.perf_counter() - start < 5
