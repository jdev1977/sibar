"""File structure: which files the output has and how the page is split
between them."""

import re
from collections import Counter

from extractors.base import Extractor
from extractors.website.site import (
    HTML_SUFFIXES, JSX_SUFFIXES, PREPROCESSOR_SUFFIXES, SCRIPT_SUFFIXES,
    TEMPLATE_SUFFIXES, get_site,
)

NAME, VERSION = "website.file-structure", "1"
_BUILD_CONFIG = re.compile(
    r"(?:^|/)(?:vite|webpack|rollup|next|nuxt|svelte|astro|tailwind|postcss|tsconfig)"
    r"(?:\.config)?\.(?:js|cjs|mjs|ts|json)$")
_README = re.compile(r"(?:^|/)readme(?:\.[a-z]{1,8})?$")


def structure(suffixes, names):
    """``single-html``, ``html-css``, ``html-js``, ``html-css-js``,
    ``component-project`` or ``no-html``."""
    if suffixes & (JSX_SUFFIXES | TEMPLATE_SUFFIXES) or "package.json" in names:
        return "component-project"
    has_html = bool(suffixes & HTML_SUFFIXES)
    css = bool(suffixes & ({"css"} | PREPROCESSOR_SUFFIXES))
    js = bool(suffixes & SCRIPT_SUFFIXES)
    if not has_html:
        return "no-html"
    return {(False, False): "single-html", (True, False): "html-css",
            (False, True): "html-js", (True, True): "html-css-js"}[(css, js)]


def extract(inputs):
    if not inputs.files and not inputs.skipped:
        return {"status": "no-input"}
    site = get_site(inputs)
    paths = [f.path for f in inputs.files] + [path for path, _ in inputs.skipped]
    kinds = Counter()
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        stem, dot, ext = name.rpartition(".")
        kinds[ext.lower() if dot and stem else "none"] += 1
    names = {p.rsplit("/", 1)[-1].lower() for p in paths}
    pages = [doc for doc in site.docs if not doc.fragment and not doc.jsx
             and doc.path.rsplit(".", 1)[-1].lower() in HTML_SUFFIXES]
    style_blocks = script_blocks = scripts = stylesheets = style_attributes = 0
    for doc in pages:
        for owner, content in doc.raws:
            tag = doc.elements[owner].tag
            style_blocks += tag == "style"
            script_blocks += tag == "script" and bool(content.strip())
        for element in doc.elements:
            if element.tag == "script" and element.attrs.get("src"):
                scripts += 1
            elif element.tag == "link" and "stylesheet" in element.attrs.get(
                    "rel", "").lower():
                stylesheets += 1
            if "style" in element.attrs:
                style_attributes += 1
    return {
        "status": "partial" if site.truncated else "ok",
        "file_count": len(paths),
        "file_kinds": {key: kinds[key] for key in sorted(kinds)},
        "structure": structure(set(kinds), names),
        "folders": sorted({p.split("/")[0].lower() for p in paths if "/" in p}),
        "max_depth": max((p.count("/") for p in paths), default=0),
        "entry_file": site.entry.path if site.entry is not None else None,
        "html_files": len(pages),
        "inline_style_blocks": style_blocks,
        "inline_script_blocks": script_blocks,
        "external_scripts": scripts,
        "external_stylesheets": stylesheets,
        "style_attributes": style_attributes,
        "has_package_json": "package.json" in names,
        "has_readme": any(_README.search(p.lower()) for p in paths),
        "has_build_config": any(_BUILD_CONFIG.search(p.lower()) for p in paths),
        "total_bytes": sum(len(f.data) for f in inputs.files),
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "files, folders, and inline against separate CSS and JS")
