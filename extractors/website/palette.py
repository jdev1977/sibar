"""Palette: the colours a page declares, named in a coarse vocabulary."""

from collections import Counter

from extractors.base import Extractor
from extractors.website import colors, tailwind
from extractors.website.css import is_dark_page_selector, is_page_selector
from extractors.website.site import get_site
from extractors.website.values import (
    Resolver, color_nodes, most_common, parse_color_text, visible,
)

NAME, VERSION = "website.palette", "3"
COLOR_ATTRIBUTES = ("fill", "stroke", "stop-color", "color", "bgcolor")
BACKGROUND_PROPERTIES = ("background", "background-color")
FULL_HEIGHT = frozenset({"min-h-screen", "h-screen", "min-h-full", "min-h-dvh",
                         "h-dvh", "min-h-svh"})
MAX_UNKNOWN = 50


def _tailwind_background(site, element, dark):
    """The ``bg-*`` colour of ``element``: the last plain one, or with
    ``dark`` the last ``dark:bg-*`` when there is one. ``(hex, found)``,
    where hex is None for a theme colour that is not a plain colour."""
    plain = forced = None
    found_plain = found_forced = False
    for utility in filter(None, map(tailwind.split, element.classes)):
        hit = site.color(utility)
        if not hit or hit[0] != "bg":
            continue
        if not utility.variants:
            plain, found_plain = hit[2], True
        elif dark and utility.variants == ("dark",):
            forced, found_forced = hit[2], True
    if dark and found_forced:
        return forced, True
    return plain, found_plain


def page_background(site, resolver=None):
    """``(hex or None, how)``: the page's background colour.

    ``how`` is ``declared`` (a colour was found), ``default`` (nothing sets
    one, so the browser's white shows) or ``unknown`` (set, but through a
    value that could not be read, such as an unresolved ``var()``).

    Looked for, first found wins: a Tailwind ``bg-*`` class on ``<body>`` or
    ``<html>``; the last ``background`` or ``background-color`` outside
    ``@media`` on ``html``, ``body`` or ``:root`` (or in their ``style``);
    a ``bg-*`` class on the first full-height wrapper (``min-h-screen``) of
    the page or its components. When the page starts in its dark theme
    (:meth:`Site.forced_dark`), ``dark:bg-*`` classes and rules on
    ``.dark`` or ``[data-theme="dark"]`` page selectors win.
    """
    dark = site.forced_dark()
    resolver = resolver or Resolver(site.declarations(), dark=dark)
    entry_tags = []
    if site.entry is not None:
        entry_tags = [e for e in site.entry.elements if e.tag in ("html", "body")]
    unknown = False
    if site.tailwind != "none":
        for element in reversed(entry_tags):  # body before html
            hex_color, found = _tailwind_background(site, element, dark)
            if found and hex_color:
                return hex_color, "declared"
            unknown |= found  # a theme colour that could not be read
    candidates = [d for d in site.declarations()
                  if d.prop in BACKGROUND_PROPERTIES and not d.media
                  and (is_page_selector(d.selector)
                       or dark and is_dark_page_selector(d.selector)
                       if d.element is None
                       else any(d.element is e for e in entry_tags))]
    if dark:
        candidates.sort(key=lambda d: d.element is None and is_dark_page_selector(
            d.selector))  # stable: dark rules last, so they win
    if candidates:
        last = candidates[-1]
        found, unread = color_nodes(last.value, last.prop, resolver)
        shown = visible(found)
        if shown:
            return shown[0], "declared"
        if unread:
            unknown = True
    if site.tailwind != "none":
        for doc in site.page_docs():
            for element in doc.elements:
                if element.hidden or element.tag in ("html", "body", "head"):
                    continue
                if set(element.classes) & FULL_HEIGHT:
                    hex_color, found = _tailwind_background(site, element, dark)
                    if found and hex_color:
                        return hex_color, "declared"
                    unknown |= found
                    break
    return (None, "unknown") if unknown else (None, "default")


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup and not site.sheets:
        return {"status": "no-input"}
    resolver = Resolver(site.declarations())
    uses, unread = Counter(), 0
    for declaration in site.declarations():
        found, missing = color_nodes(declaration.value, declaration.prop, resolver)
        uses.update(visible(found))
        unread += missing
    for _, element in site.elements():
        for name in COLOR_ATTRIBUTES:
            hex_color = parse_color_text(element.attrs.get(name))
            if hex_color:
                uses[hex_color] += 1
    for content in site.meta("theme-color"):
        hex_color = parse_color_text(content)
        if hex_color:
            uses[hex_color] += 1
    tailwind_names, unknown = set(), set()
    for utility, _, _ in site.utilities():
        hit = site.color(utility)
        if hit:
            tailwind_names.add(hit[1])
            if hit[2]:
                uses[hit[2]] += 1
            else:
                unread += 1
            continue
        name = tailwind.unknown_color(utility, site.theme.colors,
                                      site.theme.other_names)
        if name:
            unknown.add(name)
    classes, hues, accents = Counter(), Counter(), Counter()
    for hex_color, count in uses.items():
        name = colors.classify(hex_color)
        classes[name] += count
        if colors.is_chromatic(name):
            hues[colors.hue_of(name)] += count
            if colors.chroma_of(hex_color) >= colors.ACCENT_CHROMA:
                accents[colors.hue_of(name)] += count
    background, how = page_background(site)
    if background is not None:
        scheme = "dark" if colors.lightness_of(background) < 50 else "light"
        background_class = colors.classify(background)
    elif how == "default":
        scheme, background_class = "light", "default"
    else:
        scheme = background_class = None
    return {
        "status": site.status(),
        "colors": sorted(uses),
        "color_count": len(uses),
        "color_classes": sorted(classes),
        "hues": sorted(hues),
        "dominant_hue": most_common(accents) or "none",
        "tailwind_colors": sorted(tailwind_names),
        "unknown_color_utilities": len(unknown),
        "unknown_color_names": sorted(unknown)[:MAX_UNKNOWN],
        "background": background_class,
        "background_hex": background,
        "base_scheme": scheme,
        "unparsed_colors": unread,
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "colours declared in CSS, attributes and utility classes")
