"""Gradients: how many, which kinds, their colours and directions, and
gradient-filled text."""

import re

from extractors.base import Extractor
from extractors.website import colors, tailwind
from extractors.website.css import is_page_selector, significant, walk
from extractors.website.site import get_site
from extractors.website.values import Resolver, color_nodes, visible

NAME, VERSION = "website.gradients", "1"
GRADIENTS = {"linear-gradient": "linear", "radial-gradient": "radial",
             "conic-gradient": "conic", "repeating-linear-gradient": "linear",
             "repeating-radial-gradient": "radial",
             "repeating-conic-gradient": "conic",
             "-webkit-linear-gradient": "linear", "-webkit-radial-gradient": "radial"}
_HERO = re.compile(r"hero|banner|jumbotron|masthead")
_BUTTON = re.compile(r"\bbutton\b|btn|cta")


def _direction(function):
    """``135deg``, ``to-right`` or None (the default) for a linear gradient."""
    args = significant(function.arguments)
    first = []
    for node in args:
        if node.type == "literal" and node.value == ",":
            break
        first.append(node)
    if not first:
        return None
    if first[0].type == "dimension" and first[0].lower_unit in ("deg", "turn",
                                                                "rad", "grad"):
        factor = {"deg": 1, "turn": 360, "rad": 57.29577951308232,
                  "grad": 0.9}[first[0].lower_unit]
        return f"{round(first[0].value * factor) % 360}deg"
    words = [n.lower_value for n in first if n.type == "ident"]
    if words and words[0] == "to":
        return "-".join(words)
    return None


def _target(selector, element):
    """Where a gradient is used: page, hero, button or other."""
    if element is not None:
        names = " ".join([element.tag, element.attrs.get("id", "")] + element.classes)
        if element.tag in ("html", "body"):
            return "page"
    else:
        if is_page_selector(selector):
            return "page"
        names = selector.lower()
    if _HERO.search(names):
        return "hero"
    if _BUTTON.search(names):
        return "button"
    return "other"


def _pair(hexes):
    if not hexes:
        return None
    first, last = (colors.hue_of(colors.classify(h)) for h in (hexes[0], hexes[-1]))
    return f"{first}>{last}"


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup and not site.sheets:
        return {"status": "no-input"}
    resolver = Resolver(site.declarations())
    count, types, directions, pairs, hues, targets = 0, set(), set(), set(), set(), set()
    text = False
    clip_rules = set()
    for declaration in site.declarations():
        if declaration.prop in ("background-clip", "-webkit-background-clip") and \
                "text" in declaration.text.lower():
            clip_rules.add((declaration.selector, id(declaration.element)))
    gradient_rules = set()
    for declaration in site.declarations():
        for node in walk(declaration.value):
            if node.type != "function" or node.lower_name not in GRADIENTS:
                continue
            count += 1
            kind = GRADIENTS[node.lower_name]
            types.add(kind)
            if kind == "linear":
                direction = _direction(node)
                directions.add(direction or "to-bottom")
            found, _ = color_nodes(node.arguments, "background-image", resolver)
            hexes = visible(found)
            hues.update(colors.hue_of(colors.classify(h)) for h in hexes)
            pair = _pair(hexes)
            if pair:
                pairs.add(pair)
            targets.add(_target(declaration.selector, declaration.element))
            gradient_rules.add((declaration.selector, id(declaration.element)))
    if clip_rules & gradient_rules:
        text = True
    by_element = {}
    for utility, _, element in site.utilities():
        by_element.setdefault(id(element) if element is not None else None,
                              (element, []))[1].append(utility)
    for key, (element, utilities) in by_element.items():
        if key is None:
            continue
        bases = {u.base for u in utilities}
        stops = {}
        gradient = None
        for utility in utilities:
            found = tailwind.gradient(utility)
            if found:
                gradient = found
            hit = tailwind.color(utility)
            if hit and hit[0] in ("from", "via", "to"):
                stops.setdefault(hit[0], hit[2])
        if gradient is None:
            continue
        count += 1
        types.add(gradient[0])
        if gradient[0] == "linear":
            directions.add(gradient[1] or "to-bottom")
        hexes = [stops[k] for k in ("from", "via", "to") if k in stops]
        hues.update(colors.hue_of(colors.classify(h)) for h in hexes)
        pair = _pair(hexes)
        if pair:
            pairs.add(pair)
        if "bg-clip-text" in bases:
            text = True
            targets.add("text")
        else:
            targets.add(_target("", element))
    if text:
        targets.add("text")
    return {
        "status": site.status(),
        "gradient_count": count,
        "gradient_types": sorted(types),
        "gradient_directions": sorted(directions),
        "gradient_hues": sorted(hues),
        "gradient_pairs": sorted(pairs),
        "gradient_text": text,
        "gradient_targets": sorted(targets),
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "gradients: kinds, colours, directions, gradient text")
