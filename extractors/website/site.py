"""One website output, parsed once and shared by every website extractor.

:func:`get_site` reads the :class:`~extractors.base.Inputs` into a
:class:`Site`: HTML documents (from ``.html``, ``.vue``, ``.svelte`` and
``.astro`` files, JSX in scripts, and HTML held in JavaScript strings),
stylesheets (files, ``<style>`` elements, ``style`` attributes), scripts,
references to other files and packages, ``package.json``, class names and the
page's visible text.
"""

import json
import re
from dataclasses import dataclass, field

from extractors.website import tailwind
from extractors.website.css import (
    TAILWIND_AT_RULES, parse_css, parse_style_attribute,
)
from extractors.website.html import parse_html
from extractors.website.js import scan

HTML_SUFFIXES = frozenset({"html", "htm", "xhtml"})
TEMPLATE_SUFFIXES = frozenset({"vue", "svelte", "astro"})
CSS_SUFFIXES = frozenset({"css"})
PREPROCESSOR_SUFFIXES = frozenset({"scss", "sass", "less"})
SCRIPT_SUFFIXES = frozenset({"js", "mjs", "cjs", "ts", "mts", "cts"})
JSX_SUFFIXES = frozenset({"jsx", "tsx"})
JSX_TYPES = frozenset({"text/babel", "text/jsx", "text/tsx"})
SCRIPT_TYPES = frozenset({"", "module", "text/javascript", "application/javascript",
                          "text/ecmascript", "application/ecmascript",
                          "text/typescript"}) | JSX_TYPES
TEMPLATE_TYPES = frozenset({"text/template", "text/x-template", "text/html",
                            "text/x-handlebars-template"})
MAX_FRAGMENTS = 500
MAX_NESTED = 2
ATTRIBUTE_TEXT = ("alt", "placeholder", "title", "aria-label")
_TAILWIND_REFERENCE = re.compile(
    r"(?:^|[/@.])tailwindcss(?:$|[/@.])|cdn\.tailwindcss\.com|@tailwindcss/")
_TAILWIND_CONFIG = re.compile(r"(?:^|/)tailwind\.config\.(?:js|cjs|mjs|ts)$")
_HTML_DOCUMENT = re.compile(r"<!doctype\s+html|<html[\s>]", re.IGNORECASE)


@dataclass(frozen=True)
class Reference:
    """A reference to another file or package.

    ``kind`` is ``script`` (``<script src>``), ``link`` (``<link href>``, with
    ``rel`` its rel), ``css-import`` (``@import``), ``module`` (an import or
    require in a script), ``importmap`` or ``package`` (``package.json``).
    """

    kind: str
    target: str
    origin: str
    rel: str = ""


@dataclass
class Site:
    files: tuple = ()
    docs: list = field(default_factory=list)  # every parsed document
    entry: object = None  # the main HTML page, as the renderer chooses it
    sheets: list = field(default_factory=list)
    style_attributes: list = field(default_factory=list)  # Declarations
    scripts: list = field(default_factory=list)
    references: list = field(default_factory=list)
    package: dict = None
    truncated: bool = False
    tailwind_evidence: list = field(default_factory=list)
    tailwind: str = "none"  # "referenced", "classes-only" or "none"

    # --- What extractors read ------------------------------------------------

    @property
    def has_markup(self):
        return any(not doc.fragment for doc in self.docs)

    @property
    def has_styles(self):
        return bool(self.sheets or self.style_attributes or self.class_tokens())

    def status(self):
        return "partial" if self.truncated else "ok"

    def declarations(self):
        """Every CSS declaration: stylesheets first, then style attributes."""
        found = [d for sheet in self.sheets for d in sheet.declarations]
        return found + self.style_attributes

    def page_docs(self):
        """Documents that make up the page's structure: the entry page, and
        component files (JSX, Vue, Svelte, Astro); not HTML fragments."""
        docs = [self.entry] if self.entry is not None else []
        return docs + [d for d in self.docs if d is not self.entry and not d.fragment
                       and (d.jsx or d.path.rsplit(".", 1)[-1].lower()
                            in TEMPLATE_SUFFIXES)]

    def elements(self):
        """``(doc, element)`` for every element outside hidden parts."""
        for doc in self.docs:
            for element in doc.elements:
                if not element.hidden:
                    yield doc, element

    def class_tokens(self):
        """``(token, doc, element)`` for every class name used: in markup,
        given in scripts (doc and element None) and in ``@apply``."""
        if "_classes" not in self.__dict__:
            found = []
            for doc, element in self.elements():
                found += [(token, doc, element) for token in element.classes]
            for script in self.scripts:
                if script.jsx:
                    continue  # its className values are read from the markup
                for text in script.class_strings():
                    found += [(token, None, None) for token in text.split()]
            for sheet in self.sheets:
                found += [(token, None, None) for token in sheet.applied]
            self.__dict__["_classes"] = found
        return self.__dict__["_classes"]

    def utilities(self):
        """``(utility, doc, element)`` for class tokens read as Tailwind
        utilities; empty unless the site uses Tailwind."""
        if self.tailwind == "none":
            return []
        found = []
        for token, doc, element in self.class_tokens():
            utility = tailwind.split(token)
            if utility is not None:
                found.append((utility, doc, element))
        return found

    def copy_texts(self):
        """The page's visible text: text in markup (JSX included) and
        strings in scripts that read as prose."""
        texts = [t for doc in self.docs for t in doc.copy_texts()]
        for script in self.scripts:
            texts += script.prose_strings()
        return texts

    def meta(self, name):
        """The ``content`` of each ``<meta name=...>`` in the HTML pages."""
        return [element.attrs.get("content", "") for doc in self.docs
                if not doc.fragment for element in doc.find("meta")
                if element.attrs.get("name", "").strip().lower() == name]

    def attribute_texts(self):
        """Text in ``alt``, ``placeholder``, ``title`` and ``aria-label``."""
        return [element.attrs[name] for _, element in self.elements()
                for name in ATTRIBUTE_TEXT if element.attrs.get(name)]


def _entry(candidates):
    """The renderer's choice of page: index.html (shallowest), then a whole
    document, then the shallowest, the largest, the first by name."""
    def order(item):
        doc, size, text = item
        name = doc.path.rsplit("/", 1)[-1].lower()
        depth = doc.path.count("/")
        if name in ("index.html", "index.htm"):
            return (0, depth, 0, 0, doc.path)
        whole = 0 if _HTML_DOCUMENT.search(text) else 1
        return (1, whole, depth, -size, doc.path)
    return min(candidates, key=order)[0] if candidates else None


class _Builder:
    def __init__(self, site):
        self.site = site
        self.fragments = 0

    def reference(self, kind, target, origin, rel=""):
        target = (target or "").strip()
        if target and len(target) <= 2000:
            self.site.references.append(Reference(kind, target, origin, rel))

    def document(self, doc, nested=0):
        site = self.site
        site.docs.append(doc)
        site.truncated |= doc.truncated
        for element in doc.elements:
            style = element.attrs.get("style")
            if style and not style.startswith("{"):
                site.style_attributes += parse_style_attribute(
                    style, f"{doc.path}#style-attribute", element)
            if element.component:
                continue
            if element.tag == "link":
                self.reference("link", element.attrs.get("href"), doc.path,
                               element.attrs.get("rel", "").lower())
            elif element.tag == "script" and element.attrs.get("src"):
                self.reference("script", element.attrs["src"], doc.path)
        for owner, content in doc.raws:
            element = doc.elements[owner]
            if element.tag == "style":
                sheet = parse_css(content, f"{doc.path}#style")
                site.sheets.append(sheet)
                site.truncated |= sheet.truncated
            elif element.tag == "script" and content.strip():
                kind = element.attrs.get("type", "").strip().lower()
                if kind == "importmap":
                    self.importmap(content, doc.path)
                elif kind in SCRIPT_TYPES:
                    self.script(content, f"{doc.path}#script", kind in JSX_TYPES,
                                nested)
                elif kind in TEMPLATE_TYPES and nested < MAX_NESTED:
                    self.fragment(content, f"{doc.path}#template", nested + 1)

    def fragment(self, text, origin, nested):
        if self.fragments >= MAX_FRAGMENTS:
            self.site.truncated = True
            return
        self.fragments += 1
        self.document(parse_html(text, origin, fragment=True), nested)

    def importmap(self, content, origin):
        try:
            data = json.loads(content)
        except ValueError:
            return
        imports = data.get("imports") if isinstance(data, dict) else None
        if isinstance(imports, dict):
            for name in sorted(imports):
                self.reference("importmap", name, origin)
                if isinstance(imports[name], str):
                    self.reference("importmap", imports[name], origin)

    def script(self, text, origin, jsx, nested=0):
        script = scan(text, origin)
        self.site.scripts.append(script)
        self.site.truncated |= script.truncated
        for spec in script.imports():
            self.reference("module", spec, origin)
        if jsx or script.looks_like_jsx():
            script.jsx = True
            self.document(parse_html(text, origin, jsx=True), MAX_NESTED)
        if nested < MAX_NESTED:
            for markup in script.html_strings():
                self.fragment(markup, f"{origin}#string", nested + 1)

    def package(self, file):
        try:
            data = json.loads(file.text)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        self.site.package = data
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            deps = data.get(key)
            if isinstance(deps, dict):
                for name in sorted(deps):
                    self.reference("package", name, file.path)


def build_site(inputs):
    site = Site(files=inputs.files)
    builder = _Builder(site)
    pages = []
    for file in inputs.files:
        suffix = file.suffix
        name = file.path.rsplit("/", 1)[-1].lower()
        if suffix in HTML_SUFFIXES:
            doc = parse_html(file.text, file.path)
            builder.document(doc)
            pages.append((doc, len(file.data), file.text))
        elif suffix in TEMPLATE_SUFFIXES:
            builder.document(parse_html(file.text, file.path))
        elif suffix in CSS_SUFFIXES or suffix in PREPROCESSOR_SUFFIXES:
            sheet = parse_css(file.text, file.path, suffix in PREPROCESSOR_SUFFIXES)
            site.sheets.append(sheet)
            site.truncated |= sheet.truncated
        elif suffix in SCRIPT_SUFFIXES or suffix in JSX_SUFFIXES:
            builder.script(file.text, file.path, suffix in JSX_SUFFIXES)
        elif name == "package.json":
            builder.package(file)
    site.entry = _entry(pages)
    _find_tailwind(site, inputs)
    return site


def _find_tailwind(site, inputs):
    evidence = set()
    for reference in site.references:
        if _TAILWIND_REFERENCE.search(reference.target.lower()):
            evidence.add("package" if reference.kind == "package" else "reference")
    for sheet in site.sheets:
        if any(keyword in TAILWIND_AT_RULES for keyword, _, _ in sheet.at_rules):
            evidence.add("css-directive")
        if any(_TAILWIND_REFERENCE.search(target.lower()) for target in sheet.imports):
            evidence.add("css-directive")
    if any(_TAILWIND_CONFIG.search(f.path.lower()) for f in inputs.files):
        evidence.add("config-file")
    if any("tailwind.config" in script.code for script in site.scripts):
        evidence.add("inline-config")
    site.tailwind_evidence = sorted(evidence)
    if evidence:
        site.tailwind = "referenced"
        return
    signs = {token for token, _, _ in site.class_tokens()
             if (u := tailwind.split(token)) is not None and tailwind.is_sign(u)}
    site.tailwind = "classes-only" if len(signs) >= tailwind.SIGNS_NEEDED else "none"


def get_site(inputs):
    """The parsed :class:`Site` of ``inputs``, built once."""
    return inputs.cached("website.site", lambda: build_site(inputs))
