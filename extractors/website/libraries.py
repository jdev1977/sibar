"""Libraries and frameworks: what the page loads or imports, and how."""

from urllib.parse import urlsplit

from extractors.base import Extractor
from extractors.website import catalog
from extractors.website.site import get_site

NAME, VERSION = "website.libraries", "1"


def found_libraries(site):
    """``(libraries {slug: set of deliveries}, hosts, unrecognised)``."""
    libraries, hosts, unrecognised = {}, set(), set()
    for reference in site.references:
        if reference.kind == "link" and not any(
                word in reference.rel for word in ("stylesheet", "preload",
                                                   "modulepreload")):
            continue  # icons, canonical, preconnect...
        slug, delivery, unknown = catalog.resolve(reference.target, reference.kind)
        if delivery == "cdn":
            try:
                host = urlsplit(reference.target if not reference.target.startswith(
                    "//") else "https:" + reference.target).hostname
            except ValueError:
                host = None
            if host:
                hosts.add(host.lower())
        if slug:
            libraries.setdefault(slug, set()).add(delivery)
        elif unknown:
            unrecognised.add(unknown)
    for sheet in site.sheets:
        for target in sheet.imports:
            slug, delivery, unknown = catalog.resolve(target, "css-import")
            if slug:
                libraries.setdefault(slug, set()).add(delivery)
            elif unknown:
                unrecognised.add(unknown)
            if delivery == "cdn":
                try:
                    host = urlsplit(target if not target.startswith("//")
                                    else "https:" + target).hostname
                except ValueError:
                    host = None
                if host:
                    hosts.add(host.lower())
    if site.tailwind == "referenced":
        libraries.setdefault("tailwindcss", set())
    return libraries, hosts, unrecognised


def extract(inputs):
    site = get_site(inputs)
    if not inputs.files:
        return {"status": "no-input"}
    libraries, hosts, unrecognised = found_libraries(site)
    names = sorted(libraries)
    framework = next((f for f in catalog.FRAMEWORKS if f in libraries), "none")
    css_framework = next((f for f in catalog.CSS_FRAMEWORKS if f in libraries), None)
    if css_framework is None:
        css_framework = "tailwindcss" if site.tailwind == "classes-only" else "none"
    return {
        "status": site.status(),
        "libraries": names,
        "library_count": len(names),
        "delivery": sorted({d for found in libraries.values() for d in found}),
        "cdn_hosts": sorted(hosts),
        "framework": framework,
        "css_framework": css_framework,
        "tailwind_usage": site.tailwind,
        "tailwind_evidence": site.tailwind_evidence,
        "unrecognised": sorted(unrecognised),
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "libraries, frameworks and CDNs referenced or imported")
