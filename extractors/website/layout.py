"""Layout: the page's sequence of sections, landmarks, grid and flex use,
repeated card groups, the navigation bar's position and container widths."""

import re
from collections import Counter

from extractors.base import Extractor
from extractors.website import tailwind
from extractors.website.css import selector_parts, significant
from extractors.website.site import get_site
from extractors.website.values import to_px

NAME, VERSION = "website.layout", "1"
MAX_SECTIONS = 30
MAX_UNWRAP = 6
MIN_CARDS = 3
MIN_CONTAINER_PX = 480
LANDMARKS = ("header", "nav", "main", "footer", "aside", "section", "article")
TAG_KINDS = {"header": "header", "nav": "nav", "footer": "footer",
             "aside": "sidebar", "form": "form"}
# Elements never counted as a block of the page: inline and invisible ones.
NOT_BLOCKS = frozenset({"script", "style", "noscript", "template", "link", "meta",
                        "a", "span", "br", "i", "b", "em", "strong", "img", "button",
                        "input", "label", "small", "svg", "wbr"})
# Repeated siblings that are page structure or rows, not cards.
NOT_CARDS = frozenset({"tr", "option", "li", "a", "span", "br", "img", "section",
                       "header", "footer", "main", "nav", "form", "p", "h1", "h2",
                       "h3", "h4", "h5", "h6"})
WRAPPERS = frozenset({"div", "main", "section", "article", "span", "app", "body"})
SECTION_WORDS = {
    "hero": "hero banner jumbotron masthead splash",
    "features": "features feature benefits services highlights why advantages",
    "pricing": "pricing plans plan prices tiers price",
    "testimonials": "testimonials testimonial reviews review quotes",
    "faq": "faq faqs questions",
    "cta": "cta call-to-action signup get-started",
    "contact": "contact location visit find-us map directions",
    "about": "about story mission",
    "menu": "menu products product shop catalog catalogue",
    "gallery": "gallery photos portfolio projects showcase",
    "team": "team people staff speakers",
    "stats": "stats statistics numbers metrics kpi kpis",
    "schedule": "schedule agenda timeline program programme itinerary hours",
    "newsletter": "newsletter subscribe subscription",
    "blog": "blog posts articles news",
    "skills": "skills experience resume education",
    "logos": "logos clients partners sponsors brands trusted",
    "steps": "how-it-works steps process",
    "order": "order pre-order preorder booking reserve reservation register "
             "registration tickets rsvp checkout",
    "dashboard": "dashboard charts chart overview analytics",
    "app": "todo todos tasks task",
    "header": "header topbar navbar",
    "nav": "nav navigation",
    "footer": "footer",
    "sidebar": "sidebar",
}
WORD_KIND = {word: kind for kind, words in SECTION_WORDS.items()
             for word in words.split()}
_IGNORED = frozenset({"section", "container", "wrapper", "wrap", "inner", "content",
                      "block", "area", "main", "page", "site", "box", "row", "col",
                      "grid", "flex", "py", "px", "bg", "mx", "auto", "w", "full"})
_SPLIT = re.compile(r"[-_\s:/]+|(?<=[a-z])(?=[A-Z])")
_TESTIMONIAL = re.compile(r"\bwhat (?:our |people |they |customers |clients )?"
                          r"(?:customers |clients |people |guests )?(?:say|are saying)")
_NAV_SELECTOR = re.compile(
    r"(?:^|[\s>+~.#])(?:header|nav|navbar|navigation|topbar|top-bar|site-header|"
    r"main-nav|menu-bar|masthead)(?![\w-])")
_REPEAT = re.compile(r"repeat\(\s*(auto-fit|auto-fill|\d{1,2})\s*,")


def _words(text):
    return [w.lower() for w in _SPLIT.split(text or "") if w]


def _kind_from_words(words, joined=""):
    for phrase in ("how-it-works", "call-to-action", "get-started", "find-us",
                   "pre-order"):
        if phrase in joined:
            return WORD_KIND[phrase]
    for word in words:
        if word not in _IGNORED and word in WORD_KIND:
            return WORD_KIND[word]
    return None


def _first_heading(doc, element):
    for item in doc.descendants(element):
        if item.tag in ("h1", "h2", "h3") and not item.component:
            return item
    return None


def classify_block(doc, element):
    """The kind of one top-level block of a page, or None if unknown."""
    if element.component:
        return _kind_from_words(_words(element.name), element.name.lower())
    if element.tag in TAG_KINDS:
        return TAG_KINDS[element.tag]
    element_id = element.attrs.get("id", "")
    kind = _kind_from_words(_words(element_id), element_id.lower())
    if kind is None:
        classes = " ".join(c for c in element.classes if ":" not in c)
        kind = _kind_from_words(_words(classes), classes.lower())
    if kind is None:
        label = element.attrs.get("aria-label", "")
        kind = _kind_from_words(_words(label), label.lower())
    if kind is None:
        heading = _first_heading(doc, element)
        if heading is not None:
            text = doc.text_of(heading, 200).lower()
            if _TESTIMONIAL.search(text):
                return "testimonials"
            kind = _kind_from_words(_words(text), text)
    return kind


def _children(doc, element):
    return [doc.elements[i] for i in element.children
            if not doc.elements[i].hidden and (doc.elements[i].component or
                                                doc.elements[i].tag not in NOT_BLOCKS)]


def blocks(doc):
    """The top-level blocks of a document: the children of ``<body>`` (or of
    the top level of a component), unwrapping single wrappers and ``<main>``."""
    bodies = doc.find("body")
    if bodies:
        items = _children(doc, bodies[0])
    else:
        items = [doc.elements[i] for i in doc.roots if not doc.elements[i].hidden
                 and doc.elements[i].tag not in ("html", "head", "script", "style")]
        if doc.jsx and items:
            # The component that lays out the page renders other components.
            best = max(items, key=lambda e: sum(
                doc.elements[i].component for i in e.children))
            if sum(doc.elements[i].component for i in best.children) >= 2:
                items = _children(doc, best)
        if not doc.jsx:
            htmls = doc.find("html")
            if htmls:
                items = [e for e in _children(doc, htmls[0]) if e.tag != "head"]
    for _ in range(MAX_UNWRAP):
        if len(items) == 1 and not items[0].component and items[0].tag in WRAPPERS \
                and classify_block(doc, items[0]) is None and items[0].children:
            items = _children(doc, items[0])
        else:
            break
    flat = []
    for item in items:
        if item.tag == "main" and not item.component:
            flat += _children(doc, item)
        else:
            flat.append(item)
    return flat


def sections(site):
    """The page's block kinds, in order: from the entry page when it has
    two or more blocks, otherwise from the component file with the most."""
    candidates = []
    for doc in site.page_docs():
        found = blocks(doc)
        candidates.append((doc, found))
    if not candidates:
        return []
    doc, found = candidates[0]
    if len(found) < 2:
        doc, found = max(candidates, key=lambda c: len(c[1]))
    kinds, seen_content = [], False
    for element in found[:MAX_SECTIONS]:
        kind = classify_block(doc, element)
        if kind is None and not seen_content and _first_heading(doc, element) and \
                any(d.tag == "h1" for d in doc.descendants(element)):
            kind = "hero"
        if kind not in ("header", "nav"):
            seen_content = True
        kinds.append(kind or "other")
    return kinds


def _signature(element):
    return element.tag, tuple(sorted(element.classes))


def _holds_text(doc):
    """For each element, whether a heading or paragraph is inside it."""
    holds = [False] * len(doc.elements)
    for element in reversed(doc.elements):
        if element.parent >= 0 and (holds[element.index] or element.tag in (
                "h2", "h3", "h4", "h5", "h6", "p")):
            holds[element.parent] = True
    return holds


def card_groups(site):
    """Sizes of groups of three or more sibling elements with the same tag and
    classes, each holding a heading or paragraph."""
    sizes = []
    for doc in site.docs:
        holds = None
        for element in doc.elements:
            if element.hidden or len(element.children) < MIN_CARDS:
                continue
            holds = holds or _holds_text(doc)
            groups = Counter()
            for index in element.children:
                child = doc.elements[index]
                if child.tag in NOT_CARDS or child.component:
                    continue
                if holds[index]:
                    groups[_signature(child)] += 1
            best = max(groups.values(), default=0)
            if best >= MIN_CARDS:
                sizes.append(best)
    return sorted(sizes)


def _track_count(declaration):
    text = declaration.text.lower()
    match = _REPEAT.search(text)
    if match:
        return match.group(1)
    if "(" in text or "[" in text or "/" in text:
        return None
    parts = [n for n in significant(declaration.value)]
    return str(len(parts)) if 0 < len(parts) <= 12 else None


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup:
        return {"status": "no-input"}
    kinds = sections(site)
    landmarks = sorted({e.tag for doc in site.page_docs() for e in doc.elements
                        if e.tag in LANDMARKS and not e.component and not e.hidden})
    systems, columns, widths = set(), set(), set()
    nav = None
    for declaration in site.declarations():
        prop, text = declaration.prop, declaration.text.lower()
        if prop == "display":
            if "grid" in text:
                systems.add("grid")
            if "flex" in text:
                systems.add("flex")
        elif prop == "float" and text in ("left", "right", "inline-start",
                                          "inline-end"):
            systems.add("float")
        elif prop in ("columns", "column-count") and text not in ("auto", "1"):
            systems.add("columns")
        elif prop == "grid-template-columns":
            count = _track_count(declaration)
            if count:
                columns.add(count)
        elif prop == "max-width" and not declaration.media:
            for node in significant(declaration.value):
                px = to_px(node)
                if px is not None and px >= MIN_CONTAINER_PX:
                    widths.add(int(px))
        elif prop == "position" and text in ("sticky", "fixed", "-webkit-sticky"):
            parts = selector_parts(declaration.selector)
            if declaration.element is not None:
                hit = declaration.element.tag in ("header", "nav")
            else:
                hit = any(_NAV_SELECTOR.search(part.split()[-1] if part.split()
                                               else part) for part in parts)
            if hit:
                nav = "sticky" if "sticky" in text else (nav or "fixed")
    for utility, _, element in site.utilities():
        system = tailwind.layout(utility)
        if system:
            systems.add(system)
        count = tailwind.grid_columns(utility)
        if count:
            columns.add(count)
        width = tailwind.max_width(utility)
        if width and width >= MIN_CONTAINER_PX:
            widths.add(width)
        if utility.base == "container":
            widths.add("container")
        if element is not None and element.tag in ("header", "nav") and \
                utility.base in ("sticky", "fixed") and not utility.variants:
            nav = "sticky" if utility.base == "sticky" else (nav or "fixed")
    has_nav = any(e.tag in ("header", "nav") for doc in site.page_docs()
                  for e in doc.elements if not e.component)
    groups = card_groups(site)
    return {
        "status": site.status(),
        "sections": kinds,
        "section_kinds": sorted(set(kinds)),
        "section_count": len(kinds),
        "hero": "hero" in kinds,
        "landmarks": landmarks,
        "layout_systems": sorted(systems),
        "grid_columns": sorted(columns, key=lambda c: (not c.isdigit(),
                                                       int(c) if c.isdigit() else 0,
                                                       c)),
        "card_groups": len(groups),
        "card_group_sizes": groups,
        "nav_position": nav or ("static" if has_nav else "none"),
        "max_widths_px": sorted(w for w in widths if isinstance(w, int)),
        "container_class": "container" in widths,
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "section sequence, landmarks, grids, card groups, nav bar")
