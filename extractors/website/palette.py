"""Palette: the colours a page declares, named in a coarse vocabulary."""

from collections import Counter

from extractors.base import Extractor
from extractors.website import colors, tailwind
from extractors.website.css import is_page_selector
from extractors.website.site import get_site
from extractors.website.values import (
    Resolver, color_nodes, most_common, parse_color_text, visible,
)

NAME, VERSION = "website.palette", "1"
COLOR_ATTRIBUTES = ("fill", "stroke", "stop-color", "color", "bgcolor")
BACKGROUND_PROPERTIES = ("background", "background-color")
FULL_HEIGHT = frozenset({"min-h-screen", "h-screen", "min-h-full", "min-h-dvh",
                         "h-dvh", "min-h-svh"})


def _tailwind_background(utilities):
    """The last plain ``bg-*`` colour among ``utilities`` (no variants)."""
    found = None
    for utility in utilities:
        hit = tailwind.color(utility)
        if hit and hit[0] == "bg" and not utility.variants:
            found = hit[2]
    return found


def page_background(site, resolver=None):
    """``(hex or None, how)``: the page's background colour.

    ``how`` is ``declared`` (a colour was found), ``default`` (nothing sets
    one, so the browser's white shows) or ``unknown`` (set, but through a
    value that could not be read, such as an unresolved ``var()``).

    Looked for, first found wins: a Tailwind ``bg-*`` class on ``<body>`` or
    ``<html>``; the last ``background`` or ``background-color`` outside
    ``@media`` on ``html``, ``body`` or ``:root`` (or in their ``style``);
    a ``bg-*`` class on the first full-height wrapper (``min-h-screen``) of
    the page or its components.
    """
    resolver = resolver or Resolver(site.declarations())
    entry_tags = []
    if site.entry is not None:
        entry_tags = [e for e in site.entry.elements if e.tag in ("html", "body")]
    if site.tailwind != "none":
        for element in entry_tags:
            found = _tailwind_background(
                u for u in map(tailwind.split, element.classes) if u)
            if found:
                return found, "declared"
    candidates = [d for d in site.declarations()
                  if d.prop in BACKGROUND_PROPERTIES and not d.media
                  and (is_page_selector(d.selector) if d.element is None
                       else any(d.element is e for e in entry_tags))]
    if candidates:
        last = candidates[-1]
        found, unread = color_nodes(last.value, last.prop, resolver)
        shown = visible(found)
        if shown:
            return shown[0], "declared"
        if unread:
            return None, "unknown"
    if site.tailwind != "none":
        for doc in site.page_docs():
            for element in doc.elements:
                if element.hidden or element.tag in ("html", "body", "head"):
                    continue
                classes = set(element.classes)
                if classes & FULL_HEIGHT:
                    found = _tailwind_background(
                        u for u in map(tailwind.split, element.classes) if u)
                    if found:
                        return found, "declared"
                    break
    return None, "default"


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
    tailwind_names = set()
    for utility, _, _ in site.utilities():
        hit = tailwind.color(utility)
        if hit:
            uses[hit[2]] += 1
            tailwind_names.add(hit[1])
    classes = Counter()
    for hex_color, count in uses.items():
        classes[colors.classify(hex_color)] += count
    hues = Counter()
    for name, count in classes.items():
        if colors.is_chromatic(name):
            hues[colors.hue_of(name)] += count
    background, how = page_background(site, resolver)
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
        "dominant_hue": most_common(hues) or "none",
        "tailwind_colors": sorted(tailwind_names),
        "background": background_class,
        "background_hex": background,
        "base_scheme": scheme,
        "unparsed_colors": unread,
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "colours declared in CSS, attributes and utility classes")
