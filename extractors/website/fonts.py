"""Fonts: the families a page names, where it loads them from, and the
families of its body text and headings."""

import re
from urllib.parse import parse_qs, urlsplit

from extractors.base import Extractor
from extractors.website import catalog, tailwind
from extractors.website.css import selector_parts, significant
from extractors.website.site import get_site
from extractors.website.values import Resolver, substitute_vars

NAME, VERSION = "website.fonts", "4"
GENERIC = frozenset({"serif", "sans-serif", "monospace", "cursive", "fantasy",
                     "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace",
                     "ui-rounded", "math", "emoji", "fangsong"})
SYSTEM = frozenset({"system-ui", "-apple-system", "blinkmacsystemfont",
                    "ui-sans-serif", "segoe ui"})
KEYWORDS = frozenset({"inherit", "initial", "unset", "revert", "revert-layer"})
PAGE_PARTS = frozenset({"html", "body", ":root", "*"})
_SIZE_WORDS = frozenset({"xx-small", "x-small", "small", "medium", "large", "x-large",
                         "xx-large", "xxx-large", "smaller", "larger"})
_ICON_FONT = re.compile(r"icon|awesome|symbols|glyph")
_HEADING = re.compile(r"(?:^|[\s>+~,(])h[1-3](?![\w-])")
_FONTSHARE = re.compile(r"f\[\]=([a-z0-9-]{1,60})")

CATEGORY_NAMES = {
    "sans": """inter|roboto|open sans|lato|montserrat|poppins|nunito|nunito sans|
        raleway|source sans pro|source sans 3|work sans|dm sans|manrope|
        plus jakarta sans|outfit|figtree|ibm plex sans|noto sans|ubuntu|mulish|
        rubik|karla|barlow|archivo|space grotesk|sora|lexend|quicksand|
        josefin sans|cabin|hind|heebo|pt sans|fira sans|geist|helvetica|
        helvetica neue|arial|verdana|tahoma|trebuchet ms|segoe ui|sf pro display|
        sf pro text|avenir|avenir next|futura|gill sans|urbanist|be vietnam pro|
        red hat display|red hat text|albert sans|onest|instrument sans|satoshi|
        general sans|cabinet grotesk|switzer|epilogue|roboto condensed|
        public sans|assistant|overpass|exo 2|titillium web|libre franklin|
        source sans|noto sans display|schibsted grotesk|hanken grotesk|
        bricolage grotesque|space grotesk|mona sans|hubot sans""",
    "serif": """playfair display|merriweather|lora|georgia|times new roman|times|
        garamond|eb garamond|cormorant|cormorant garamond|libre baskerville|
        crimson text|crimson pro|pt serif|source serif pro|source serif 4|
        noto serif|dm serif display|dm serif text|fraunces|instrument serif|
        spectral|bitter|roboto slab|zilla slab|arvo|prata|young serif|newsreader|
        literata|baskerville|bodoni moda|libre caslon text|ibm plex serif|
        gelasio|alegreya|vollkorn|besley|playfair|cardo|old standard tt|
        noto serif display|gloock|dm serif|marcellus""",
    "mono": """fira code|jetbrains mono|courier new|courier|menlo|monaco|consolas|
        ibm plex mono|source code pro|space mono|roboto mono|dm mono|inconsolata|
        ubuntu mono|sf mono|geist mono|cascadia code|fira mono|overpass mono|
        red hat mono|share tech mono|courier prime|anonymous pro|vt323|
        lucida console|sfmono-regular|liberation mono|martian mono""",
    "script": """pacifico|dancing script|great vibes|caveat|lobster|satisfy|
        sacramento|parisienne|allura|kaushan script|amatic sc|shadows into light|
        indie flower|permanent marker|homemade apple|patrick hand|
        playwrite|yellowtail|cookie|courgette|comic sans ms""",
    "display": """bebas neue|oswald|anton|archivo black|clash display|syne|
        abril fatface|cinzel|league spartan|unbounded|righteous|fredoka|
        fredoka one|comfortaa|press start 2p|orbitron|audiowide|bungee|
        black ops one|alfa slab one|staatliches|teko|big shoulders display|
        dela gothic one|monoton|chakra petch|rajdhani|russo one|archivo narrow|
        barlow condensed|fjalla one|passion one|space age""",
}
CATEGORIES = {}
for _category, _names in CATEGORY_NAMES.items():
    for _name in _names.replace("\n", "").split("|"):
        CATEGORIES.setdefault(" ".join(_name.split()), _category)
for _name in SYSTEM | {"ui-rounded"}:
    CATEGORIES[_name] = "system"
GENERIC_CATEGORY = {"serif": "serif", "ui-serif": "serif", "sans-serif": "sans",
                    "monospace": "mono", "ui-monospace": "mono", "cursive": "script",
                    "fantasy": "display", "system-ui": "system",
                    "ui-sans-serif": "system", "ui-rounded": "system"}


def normalise(name):
    return " ".join(name.replace('"', " ").replace("'", " ").split()).lower()


def category(name):
    return CATEGORIES.get(name) or GENERIC_CATEGORY.get(name) or "unknown"


def families_of(nodes, shorthand=False):
    """The family names of a ``font-family`` (or ``font``) value, in order."""
    items = significant(nodes)
    if shorthand:
        start = None
        for index, node in enumerate(items):
            if node.type in ("dimension", "percentage") or (
                    node.type == "ident" and node.lower_value in _SIZE_WORDS):
                start = index + 1
                if start < len(items) and items[start].type == "literal" and \
                        items[start].value == "/":
                    start += 2
                break
        if start is None:
            return []
        items = items[start:]
    names, current = [], []
    for node in items + [None]:
        if node is None or (node.type == "literal" and node.value == ","):
            if current:
                names.append(normalise(" ".join(current)))
            current = []
        elif node.type == "string":
            current.append(node.value)
        elif node.type == "ident":
            current.append(node.value)
        elif node.type == "function":
            current = []  # var(), env(): not a name
    return [n for n in names if n and n not in KEYWORDS]


def _service_families(url):
    """Families named in a Google Fonts, Bunny Fonts or Fontshare URL."""
    try:
        parts = urlsplit(url if not url.startswith("//") else "https:" + url)
    except ValueError:
        return []
    found = []
    for value in parse_qs(parts.query).get("family", []):
        for item in value.split("|"):
            found.append(normalise(item.split(":")[0]))
    found += [normalise(m.group(1).replace("-", " "))
              for m in _FONTSHARE.finditer(parts.query)]
    if (parts.hostname or "").endswith("rsms.me"):
        found.append("inter")
    return [f for f in found if f]


def _tailwind_family(utility, config):
    base = utility.base
    if base.startswith("font-") and base[5:] in config:
        return config[base[5:]]
    family = tailwind.font(utility)
    if family in ("sans-serif", "serif", "monospace"):
        key = {"sans-serif": "sans", "serif": "serif", "monospace": "mono"}[family]
        return config.get(key, family)
    return normalise(family) if family else None


def _first_heading_family(site, config):
    for doc in site.page_docs():
        for element in doc.find("h1"):
            for utility in filter(None, map(tailwind.split, element.classes)):
                if not utility.variants:
                    family = _tailwind_family(utility, config)
                    if family:
                        return family
            return None
    return None


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup and not site.sheets:
        return {"status": "no-input"}
    declared, loaded, sources = set(), set(), set()
    primary = heading = None
    resolver = Resolver(site.declarations())
    for declaration in site.declarations():
        if declaration.prop not in ("font-family", "font"):
            continue
        names = families_of(substitute_vars(declaration.value, resolver),
                            declaration.prop == "font")
        if declaration.selector == "@font-face":
            loaded.update(names)
            continue
        declared.update(names)
        if not names or declaration.media:
            continue
        if declaration.element is not None:
            if declaration.element.tag in ("html", "body"):
                primary = names[0]
            continue
        parts = selector_parts(declaration.selector)
        if parts and all(part in PAGE_PARTS for part in parts):
            primary = names[0]
        if any(_HEADING.search(" " + part) for part in parts):
            heading = names[0]
    for declaration in site.declarations():
        if declaration.selector == "@font-face" and declaration.prop == "src":
            urls = [n.value for n in declaration.value if n.type == "url"] + [
                a.value for n in declaration.value
                if n.type == "function" and n.lower_name == "url"
                for a in n.arguments if a.type == "string"]
            if any(not catalog.font_service(url) for url in urls):
                sources.add("self-hosted")
    for reference in site.references:
        service = catalog.font_service(reference.target)
        if service:
            sources.add(service)
            loaded.update(_service_families(reference.target))
        elif reference.kind in ("package", "module") and \
                reference.target.startswith(("@fontsource/", "@fontsource-variable/")):
            sources.add("fontsource")
            family = catalog.package_name(reference.target).split("/")[1]
            loaded.add(normalise(family.replace("-", " ")))
    for sheet in site.sheets:
        for target in sheet.imports:
            service = catalog.font_service(target)
            if service:
                sources.add(service)
                loaded.update(_service_families(target))
    config = dict(site.theme.fonts) if site.tailwind != "none" else {}
    if site.tailwind != "none":
        for utility, _, _ in site.utilities():
            family = _tailwind_family(utility, config)
            if family:
                declared.add(family)
        if primary is None and site.entry is not None:
            for element in site.entry.find("html", "body"):
                for utility in filter(None, map(tailwind.split, element.classes)):
                    family = _tailwind_family(utility, config)
                    if family and not utility.variants:
                        primary = family
        if primary is None and "sans" in config:
            primary = config["sans"]
        if heading is None:
            heading = _first_heading_family(site, config)
    declared.update(config.values())
    text_fonts = {n for n in declared | loaded if not _ICON_FONT.search(n)}
    named = sorted(n for n in text_fonts if n not in GENERIC)
    generic = sorted(n for n in declared if n in GENERIC)
    every = named + generic
    return {
        "status": site.status(),
        "families": named,
        "family_count": len(named),
        "generic_families": generic,
        "loaded_families": sorted(n for n in loaded if not _ICON_FONT.search(n)),
        "font_categories": sorted({category(n) for n in every}),
        "font_sources": sorted(sources),
        "primary_font": primary or "default",
        "primary_category": category(primary) if primary else "default",
        "heading_font": heading or "same",
        "heading_category": category(heading) if heading else "same",
        "system_stack": any(n in SYSTEM for n in declared),
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "font families named and loaded; body and heading fonts")
