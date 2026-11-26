"""Accessibility basics that can be read from the source: language, alt
text, headings, landmarks, form labels, button names, focus styles and
reduced motion. Colour contrast needs rendering and is not measured here."""

import re

from extractors.base import Extractor
from extractors.website.site import get_site

NAME, VERSION = "website.accessibility", "1"
HEADINGS = {f"h{n}": n for n in range(1, 7)}
UNLABELLED_TYPES = frozenset({"hidden", "submit", "button", "image", "reset"})
GENERIC_LINKS = frozenset({"click here", "here", "read more", "learn more", "more",
                           "link", "this"})
_FOCUS = re.compile(r":focus(?:-visible|-within)?(?![\w-])")
_REDUCED = re.compile(r"prefers-reduced-motion")


def _has_name(element):
    return any(element.attrs.get(name, "").strip()
               for name in ("aria-label", "aria-labelledby", "title"))


def _alt_inside(doc):
    """For each element, whether an image with alt text is inside it."""
    found = [False] * len(doc.elements)
    for element in reversed(doc.elements):
        if element.parent >= 0 and (found[element.index] or (
                element.tag == "img" and element.attrs.get("alt", "").strip())):
            found[element.parent] = True
    return found


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup:
        return {"status": "no-input"}
    lang = None
    if site.entry is not None:
        htmls = site.entry.find("html")
        value = htmls[0].attrs.get("lang", "").strip() if htmls else ""
        lang = value.split("-")[0].lower() if value else ""
    images = missing = empty = 0
    levels, skips, previous = [], 0, None
    controls = unlabelled = nameless = generic = aria = roles = positive = 0
    main = skip = False
    for doc in site.docs:
        labels_for = {e.attrs.get("for") for e in doc.find("label")
                      if e.attrs.get("for")}
        alt_inside = None
        for element in doc.elements:
            if element.hidden or element.component:
                continue
            tag, attrs = element.tag, element.attrs
            aria += sum(1 for name in attrs if name.startswith("aria-"))
            roles += "role" in attrs
            if attrs.get("tabindex", "").strip().lstrip("+").isdigit() and \
                    int(attrs["tabindex"].strip().lstrip("+")) > 0:
                positive += 1
            if tag == "img":
                images += 1
                if "alt" not in attrs:
                    missing += 1
                elif not attrs["alt"].strip():
                    empty += 1
            elif tag in HEADINGS and not doc.fragment:
                level = HEADINGS[tag]
                levels.append(level)
                if previous is not None and level > previous + 1:
                    skips += 1
                previous = level
            elif tag == "main" or attrs.get("role") == "main":
                main = True
            elif tag in ("input", "select", "textarea"):
                if attrs.get("type", "").lower() in UNLABELLED_TYPES:
                    continue
                controls += 1
                labelled = _has_name(element) or (
                    attrs.get("id") and attrs["id"] in labels_for) or any(
                    a.tag == "label" for a in doc.ancestors(element))
                unlabelled += not labelled
            elif tag == "button" and not doc.jsx:
                text = doc.text_of(element, 200)
                if alt_inside is None:
                    alt_inside = _alt_inside(doc)
                inner_alt = alt_inside[element.index]
                if not text and not _has_name(element) and not inner_alt:
                    nameless += 1
            elif tag == "a":
                href = attrs.get("href", "")
                text = doc.text_of(element, 200).lower().strip(" .!>→»")
                if href.startswith("#") and "skip" in text:
                    skip = True
                if not doc.jsx and text in GENERIC_LINKS:
                    generic += 1
    focus = outline_removed = reduced = False
    for sheet in site.sheets:
        if any(_FOCUS.search(selector) for selector, _ in sheet.selectors):
            focus = True
        if any(keyword == "media" and _REDUCED.search(prelude.lower())
               for keyword, prelude, _ in sheet.at_rules):
            reduced = True
    for declaration in site.declarations():
        if declaration.prop == "outline" and declaration.text.lower() in (
                "none", "0", "0 none", "none 0"):
            outline_removed = True
        if any(_REDUCED.search(m) for m in declaration.media):
            reduced = True
    for utility, _, _ in site.utilities():
        if any(v in ("focus", "focus-visible", "focus-within") for v in
               utility.variants):
            focus = True
        if any(v in ("motion-reduce", "motion-safe") for v in utility.variants):
            reduced = True
        if utility.base == "outline-none" and not utility.variants:
            outline_removed = True
    if images == 0:
        coverage = "no-images"
    elif missing == 0:
        coverage = "all"
    else:
        coverage = "none" if missing == images else "some"
    return {
        "status": site.status(),
        "html_lang": None if lang is None else ("present" if lang else "absent"),
        "lang": lang or None,
        "images": images,
        "images_missing_alt": missing,
        "images_empty_alt": empty,
        "alt_coverage": coverage,
        "h1_count": levels.count(1),
        "heading_levels": sorted(set(levels)),
        "heading_skips": skips,
        "main_landmark": main,
        "skip_link": skip,
        "form_controls": controls,
        "unlabelled_controls": unlabelled,
        "buttons_without_name": nameless,
        "generic_link_text": generic,
        "aria_attributes": aria,
        "role_attributes": roles,
        "positive_tabindex": positive,
        "focus_styles": focus,
        "outline_removed": outline_removed,
        "reduced_motion": reduced,
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "lang, alt text, headings, labels, focus, reduced motion")
