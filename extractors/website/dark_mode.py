"""Dark mode: whether the page has one, how it is switched on (the system
setting, a toggle, or both), and whether it is dark only."""

import re

from extractors.base import Extractor
from extractors.website import colors
from extractors.website.palette import page_background
from extractors.website.site import get_site

NAME, VERSION = "website.dark-mode", "4"
_DARK_CLASS = re.compile(r"\.(?:dark|dark-mode|dark-theme|theme-dark)(?![\w-])")
_DARK_ATTRIBUTE = re.compile(r"\[data-(?:theme|mode|bs-theme|color-scheme)"
                             r"\s*=\s*['\"]?dark")
_PREFERS_DARK = re.compile(r"prefers-color-scheme\s*:\s*dark")
_CONTROL = re.compile(r"theme|dark|mode-toggle|color-scheme|night")
_CLASS_STRATEGY = re.compile(r"darkMode\s*:\s*\[?\s*\"§(\d+)\"")
CONTROL_TAGS = frozenset({"button", "input", "a", "label", "select", "div", "span"})


def mechanisms(site):
    found = set()
    for sheet in site.sheets:
        for keyword, prelude, _ in sheet.at_rules:
            if keyword == "media" and _PREFERS_DARK.search(prelude.lower()):
                found.add("prefers-color-scheme-css")
            if keyword == "custom-variant" and prelude.lower().startswith("dark"):
                found.add("tailwind-class-strategy")
        for selector, _ in sheet.selectors:
            lowered = selector.lower()
            if _DARK_CLASS.search(lowered):
                found.add("dark-class-selector")
            if _DARK_ATTRIBUTE.search(lowered):
                found.add("data-theme-attribute")
    for declaration in site.declarations():
        text = declaration.text.lower()
        if declaration.prop == "color-scheme" and "dark" in text:
            found.add("color-scheme-property")
        if "light-dark(" in text:
            found.add("light-dark-function")
    if any("dark" in content.lower() for content in site.meta("color-scheme")):
        found.add("color-scheme-property")
    for script in site.scripts:
        strings = [s.lower() for s in script.strings]
        if any(_PREFERS_DARK.search(s) for s in strings):
            found.add("prefers-color-scheme-js")
        if any(token in ("dark", "dark-mode", "dark-theme", "theme-dark")
               for text in script.class_strings() for token in text.split()):
            found.add("toggle-script")
        if any(s in ("data-theme", "data-bs-theme", "data-mode") for s in strings) and \
                any(s == "dark" for s in strings):
            found.add("toggle-script")
        for match in _CLASS_STRATEGY.finditer(script.code):
            if script.strings[int(match.group(1))].lower() in ("class", "selector"):
                found.add("tailwind-class-strategy")
    if any("dark" in u.variants for u, _, _ in site.utilities()):
        found.add("tailwind-dark-variant")
    return found


def has_toggle_control(site):
    for _, element in site.elements():
        if element.tag not in CONTROL_TAGS or element.component:
            continue
        names = " ".join([element.attrs.get("id", ""), element.attrs.get("class", ""),
                          element.attrs.get("aria-label", ""),
                          element.attrs.get("title", "")]).lower()
        if element.tag in ("div", "span") and "toggle" not in names:
            continue
        if _CONTROL.search(names):
            return True
    return False


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup and not site.sheets:
        return {"status": "no-input"}
    found = mechanisms(site)
    system = bool(found & {"prefers-color-scheme-css", "prefers-color-scheme-js",
                           "color-scheme-property", "light-dark-function"})
    toggle = bool(found & {"dark-class-selector", "data-theme-attribute",
                           "toggle-script", "tailwind-class-strategy"})
    if "tailwind-dark-variant" in found:
        if "tailwind-class-strategy" in found or "toggle-script" in found:
            toggle = True
        else:
            system = True  # Tailwind's dark: variant follows the system by default
    background, _ = page_background(site)
    control = has_toggle_control(site)
    forced = site.forced_dark()
    can_switch = control or "toggle-script" in found
    if forced and not can_switch:
        mode = "dark-only"  # starts dark, and nothing switches it back
    elif system and toggle:
        mode = "both"
    elif system:
        mode = "system"
    elif toggle:
        mode = "toggle"
    elif background is not None and colors.lightness_of(background) < 50:
        mode = "dark-only"
    else:
        mode = "none"
    return {
        "status": site.status(),
        "dark_mode": mode,
        "mechanisms": sorted(found),
        "forced_dark": forced,
        "theme_toggle": control or "toggle-script" in found,
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "dark mode by system setting, toggle, both or dark only")
