"""Corners and shadows: border radii, box and text shadows, backdrop blur."""

from collections import Counter

import tinycss2

from extractors.base import Extractor
from extractors.website import colors, tailwind
from extractors.website.css import significant
from extractors.website.site import get_site
from extractors.website.values import (
    Resolver, color_nodes, most_common, px_text, substitute_vars, to_px, visible,
)

NAME, VERSION = "website.corners-shadows", "6"
FULL_PX = 999  # a radius this large draws a pill or circle
SOFT_BLUR_PX = 10


def _radius_values(nodes):
    """Radii in a border-radius value, as text: ``8px``, ``full`` or ``0px``.
    Values after ``/`` (elliptical) are read as well."""
    found = []
    for node in significant(nodes):
        if node.type == "percentage":
            found.append("full" if node.value >= 50 else f"{node.value:g}%")
            continue
        px = to_px(node)
        if px is not None:
            found.append("full" if px >= FULL_PX else px_text(px))
    return found


def _sort_key(text):
    if text == "full":
        return (2, 0.0)
    if text.endswith("%"):
        return (1, float(text[:-1]))
    return (0, float(text[:-2]))


def corner_style(radius):
    """``square``, ``subtle`` (up to 4px), ``rounded`` (up to 12px),
    ``very-rounded`` or ``pill``."""
    if radius in (None, "0px"):
        return "square"
    if radius == "full":
        return "pill"
    if radius.endswith("%"):
        return "rounded"
    px = float(radius[:-2])
    return "subtle" if px <= 4 else "rounded" if px <= 12 else "very-rounded"


def _layers(nodes):
    """The comma-separated layers of a shadow value."""
    layers, current = [], []
    for node in significant(nodes):
        if node.type == "literal" and node.value == ",":
            layers.append(current)
            current = []
        else:
            current.append(node)
    return layers + [current]


def shadow_kinds(declaration, resolver):
    """Kinds of each layer of a box-shadow: ``inset``, ``hard`` (no blur,
    offset), ``glow`` (no offset, blurred), ``subtle`` (blur under 10px),
    ``soft``; plus ``colored`` when its colour is not neutral. ``var()`` is
    followed first."""
    kinds = set()
    for layer in _layers(substitute_vars(declaration.value, resolver)):
        if not layer or (len(layer) == 1 and layer[0].type == "ident"
                         and layer[0].lower_value == "none"):
            continue
        lengths = [to_px(n) for n in layer if n.type in ("dimension", "number")]
        lengths = [n for n in lengths if n is not None]
        if any(n.type == "ident" and n.lower_value == "inset" for n in layer):
            kinds.add("inset")
        elif len(lengths) >= 2:
            x, y = lengths[0], lengths[1]
            blur = lengths[2] if len(lengths) > 2 else 0.0
            if blur == 0 and (x or y):
                kinds.add("hard")
            elif not x and not y and blur > 0:
                kinds.add("glow")
            else:
                kinds.add("subtle" if blur < SOFT_BLUR_PX else "soft")
        found, _ = color_nodes(layer, "box-shadow", resolver)
        if any(colors.is_chromatic(colors.classify(c)) for c in visible(found)):
            kinds.add("colored")
    return kinds


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup and not site.sheets:
        return {"status": "no-input"}
    resolver = Resolver(site.declarations())
    radii = Counter()
    shadows, kinds = 0, set()
    text_shadow = backdrop = False
    for declaration in site.declarations():
        prop = declaration.prop
        if prop == "border-radius" or (prop.startswith("border-") and
                                       prop.endswith("-radius")):
            radii.update(_radius_values(substitute_vars(declaration.value,
                                                        resolver)))
        elif prop == "box-shadow":
            found = shadow_kinds(declaration, resolver)
            if found:
                shadows += 1
                kinds |= found
        elif prop == "text-shadow" and declaration.text.lower() != "none":
            text_shadow = True
        elif prop in ("backdrop-filter", "-webkit-backdrop-filter") and \
                "blur(" in declaration.text.lower():
            backdrop = True
    for utility, _, _ in site.utilities():
        radius = tailwind.radius(utility)
        if radius is not None:
            if isinstance(radius, str) and radius != "full":
                try:
                    radius = _radius_values(
                        tinycss2.parse_component_value_list(radius))
                except Exception:  # noqa: BLE001 - malformed arbitrary value
                    radius = []
                radii.update(radius)
            else:
                radii["full" if radius == "full" else px_text(radius)] += 1
            continue
        kind = tailwind.shadow(utility)
        if kind is not None and kind != "none":
            shadows += 1
            kinds.add(kind)
        elif utility.base.startswith("shadow-") and site.color(utility):
            hex_color = site.color(utility)[2]
            if hex_color is None or colors.is_chromatic(colors.classify(hex_color)):
                kinds.add("colored")
        elif utility.base.startswith("backdrop-blur"):
            backdrop = True
        elif utility.base.startswith("text-shadow") and utility.base != \
                "text-shadow-none":
            text_shadow = True
    nonzero = Counter({k: v for k, v in radii.items() if k != "0px"})
    common = most_common(Counter({k: v for k, v in nonzero.items() if k != "full"}),
                         prefer=_sort_key)
    if common is None and nonzero:
        common = "full"
    return {
        "status": site.status(),
        "radii": sorted(radii, key=_sort_key),
        "common_radius": common or "none",
        "corner_style": corner_style(common),
        "pill_shapes": "full" in radii,
        "shadow_count": shadows,
        "shadow_kinds": sorted(kinds),
        "text_shadow": text_shadow,
        "backdrop_blur": backdrop,
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "border radii, box and text shadows, backdrop blur")
