"""Icons and emoji: icon sets used, inline SVG, emoji and icon-like text
symbols, and the favicon."""

import re
from urllib.parse import unquote

from extractors.base import Extractor
from extractors.website import catalog
from extractors.website.emoji import find_emoji, starts_with_emoji
from extractors.website.libraries import found_libraries
from extractors.website.site import get_site

NAME, VERSION = "website.icons-emoji", "1"
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_CLASS_SETS = (
    # (icon set, a class that marks the set, a class naming the icon)
    ("font-awesome", re.compile(r"fa[srlbdt]?|fa-(?:solid|regular|brands|light|thin|"
                                r"duotone|sharp)"), re.compile(r"fa-[a-z0-9-]{1,60}")),
    ("bootstrap-icons", re.compile(r"bi"), re.compile(r"bi-[a-z0-9-]{1,60}")),
    ("boxicons", re.compile(r"bx[sl]?"), re.compile(r"bx[sl]?-[a-z0-9-]{1,60}")),
    ("tabler-icons", re.compile(r"ti"), re.compile(r"ti-[a-z0-9-]{1,60}")),
    ("phosphor", re.compile(r"ph(?:-(?:bold|fill|light|thin|duotone))?"),
     re.compile(r"ph-[a-z0-9-]{1,60}")),
)
_REMIX = re.compile(r"ri-[a-z0-9-]{1,60}-(?:line|fill)")
_MATERIAL = re.compile(r"material-(icons|symbols)(?:-[a-z]{1,10})?")
_LUCIDE = re.compile(r"lucide(?:-[a-z0-9-]{1,60})?")
_SVG_FILE = re.compile(r"\.svg(?:[?#]|$)", re.IGNORECASE)


def icon_sets(site):
    """Icon sets found from references, classes, attributes and tags."""
    libraries, _, _ = found_libraries(site)
    found = {name for name in libraries if name in catalog.ICON_SETS}
    for reference in site.references:
        if catalog.font_service(reference.target):
            lowered = unquote(reference.target).lower().replace("+", " ")
            if "material icons" in lowered:
                found.add("material-icons")
            if "material symbols" in lowered:
                found.add("material-symbols")
    for _, element in site.elements():
        classes = set(element.classes)
        for name, marker, icon in _CLASS_SETS:
            if any(marker.fullmatch(c) for c in classes) and any(
                    icon.fullmatch(c) for c in classes):
                found.add(name)
        for token in classes:
            if _REMIX.fullmatch(token):
                found.add("remixicon")
            match = _MATERIAL.fullmatch(token)
            if match:
                found.add(f"material-{match.group(1)}")
            if _LUCIDE.fullmatch(token) and element.tag in ("svg", "i", "span"):
                found.add("lucide")
        if "data-lucide" in element.attrs:
            found.add("lucide")
        if "data-feather" in element.attrs:
            found.add("feather")
        if element.tag == "ion-icon":
            found.add("ionicons")
        if element.tag == "iconify-icon" or ("iconify" in classes
                                             and "data-icon" in element.attrs):
            found.add("iconify")
    return sorted(found)


def favicon(site):
    """``none``, ``file``, ``external``, ``data-uri`` or ``emoji`` (an inline
    SVG favicon drawing an emoji)."""
    docs = [site.entry] if site.entry is not None else []
    for doc in docs:
        for element in doc.find("link"):
            rel = element.attrs.get("rel", "").lower().split()
            href = element.attrs.get("href", "")
            if "icon" not in rel or not href:
                continue
            if href.lower().startswith("data:"):
                emoji, _ = find_emoji(unquote(href[:5000]))
                return "emoji" if emoji else "data-uri"
            return "external" if catalog.is_url(href) else "file"
    return "none"


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup:
        return {"status": "no-input"}
    emoji, symbols = [], []
    for text in site.copy_texts():
        found, marks = find_emoji(text)
        emoji += found
        symbols += marks
    svgs = svg_images = led = 0
    for doc, element in site.elements():
        if element.component:
            continue
        if element.tag == "svg":
            svgs += 1
        elif element.tag == "img" and _SVG_FILE.search(element.attrs.get("src", "")):
            svg_images += 1
        elif element.tag in HEADINGS and starts_with_emoji(doc.text_of(element, 40)):
            led += 1
    sets = icon_sets(site)
    kinds = set()
    if sets:
        kinds.add("library")
    if svgs:
        kinds.add("inline-svg")
    if emoji:
        kinds.add("emoji")
    if svg_images:
        kinds.add("svg-image")
    if symbols:
        kinds.add("symbol")
    return {
        "status": site.status(),
        "icon_libraries": sets,
        "inline_svg_count": svgs,
        "svg_image_count": svg_images,
        "emoji": sorted(set(emoji)),
        "emoji_count": len(emoji),
        "emoji_led_headings": led,
        "text_symbols": sorted(set(symbols)),
        "icon_kinds": sorted(kinds),
        "favicon": favicon(site),
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "icon sets, inline SVG, emoji, text symbols, favicon")
