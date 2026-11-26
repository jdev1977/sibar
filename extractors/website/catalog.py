"""Known libraries, icon sets and font services, and how references name them.

A reference (a ``<script src>``, ``<link href>``, ``@import``, module import
or ``package.json`` dependency) is resolved to a library slug by
:func:`resolve`:

- an npm package name, taken from a bare import (``react``,
  ``@heroicons/react``, ``aos/dist/aos.css``) or from a CDN URL that names it
  (jsDelivr ``/npm/<pkg>``, unpkg, esm.sh, Skypack, JSPM, cdnjs and Google's
  ``/ajax/libs/<name>/``), looked up in :data:`PACKAGES`;
- a host that serves one library (``cdn.tailwindcss.com``,
  ``code.jquery.com``, ``kit.fontawesome.com``...), in :data:`HOSTS`;
- for a local file, its name with ``.min`` and version numbers removed
  (``js/jquery-3.7.1.min.js`` is ``jquery``).

Packages are mapped to one slug per library: ``react-dom`` is ``react``,
``lucide-react`` is ``lucide``. Anything not in the tables is reported as
unrecognised (package name, or host for a URL) so the tables can grow.
"""

import re
from urllib.parse import urlsplit

PACKAGES = {
    # CSS frameworks and resets
    "tailwindcss": "tailwindcss", "@tailwindcss/browser": "tailwindcss",
    "@tailwindcss/vite": "tailwindcss", "@tailwindcss/postcss": "tailwindcss",
    "@tailwindcss/forms": "tailwindcss", "@tailwindcss/typography": "tailwindcss",
    "bootstrap": "bootstrap", "twitter-bootstrap": "bootstrap",
    "bulma": "bulma", "foundation-sites": "foundation", "foundation": "foundation",
    "materialize-css": "materialize", "materialize": "materialize",
    "@picocss/pico": "pico", "picocss": "pico", "pico": "pico",
    "daisyui": "daisyui", "flowbite": "flowbite", "uikit": "uikit",
    "semantic-ui-css": "semantic-ui", "fomantic-ui": "semantic-ui",
    "@shoelace-style/shoelace": "shoelace", "normalize.css": "normalize.css",
    "normalize": "normalize.css", "modern-normalize": "normalize.css",
    "water.css": "water.css", "animate.css": "animate.css",
    "@mui/material": "mui", "@chakra-ui/react": "chakra-ui", "antd": "antd",
    "@headlessui/react": "headlessui", "@headlessui/vue": "headlessui",
    # frameworks
    "react": "react", "react-dom": "react", "next": "next", "vue": "vue",
    "nuxt": "nuxt", "svelte": "svelte", "@sveltejs/kit": "sveltekit",
    "@angular/core": "angular", "angular": "angular", "preact": "preact",
    "solid-js": "solid", "lit": "lit", "alpinejs": "alpinejs", "htmx.org": "htmx",
    "htmx": "htmx", "jquery": "jquery", "astro": "astro", "vite": "vite",
    "@babel/standalone": "babel-standalone", "babel-standalone": "babel-standalone",
    "react-router-dom": "react-router", "react-router": "react-router",
    "@reduxjs/toolkit": "redux", "redux": "redux", "zustand": "zustand",
    "@tanstack/react-query": "tanstack-query",
    # utilities, charts, motion
    "chart.js": "chart.js", "chartjs": "chart.js", "d3": "d3", "three": "three",
    "three.js": "three", "gsap": "gsap", "animejs": "anime.js", "anime.js": "anime.js",
    "aos": "aos", "swiper": "swiper", "framer-motion": "framer-motion",
    "motion": "framer-motion", "lodash": "lodash", "lodash.js": "lodash",
    "axios": "axios", "dayjs": "dayjs", "moment": "moment", "moment.js": "moment",
    "date-fns": "date-fns", "recharts": "recharts", "apexcharts": "apexcharts",
    "echarts": "echarts", "plotly.js": "plotly", "plotly": "plotly",
    "leaflet": "leaflet", "mapbox-gl": "mapbox", "marked": "marked",
    "highlight.js": "highlight.js", "prismjs": "prism", "prism": "prism",
    "katex": "katex", "mathjax": "mathjax", "typed.js": "typed.js",
    "particles.js": "particles.js", "tsparticles": "tsparticles",
    "lottie-web": "lottie", "@lottiefiles/lottie-player": "lottie",
    "lenis": "lenis", "@studio-freight/lenis": "lenis",
    "locomotive-scroll": "locomotive-scroll", "scrollreveal": "scrollreveal",
    "glightbox": "glightbox", "sortablejs": "sortablejs", "sortable": "sortablejs",
    "canvas-confetti": "canvas-confetti", "clsx": "clsx",
    "class-variance-authority": "class-variance-authority",
    "tailwind-merge": "tailwind-merge", "sweetalert2": "sweetalert2",
    "toastify-js": "toastify", "flatpickr": "flatpickr", "vanta": "vanta",
    "splitting": "splitting", "vanilla-tilt": "vanilla-tilt",
    "@splidejs/splide": "splide", "slick-carousel": "slick",
    # icon sets
    "lucide": "lucide", "lucide-react": "lucide", "lucide-static": "lucide",
    "lucide-vue-next": "lucide", "lucide-svelte": "lucide",
    "@heroicons/react": "heroicons", "@heroicons/vue": "heroicons",
    "heroicons": "heroicons", "@fortawesome/fontawesome-free": "font-awesome",
    "@fortawesome/fontawesome-svg-core": "font-awesome",
    "@fortawesome/free-solid-svg-icons": "font-awesome",
    "@fortawesome/react-fontawesome": "font-awesome", "font-awesome": "font-awesome",
    "fontawesome": "font-awesome", "feather-icons": "feather",
    "react-feather": "feather", "feather": "feather",
    "bootstrap-icons": "bootstrap-icons", "ionicons": "ionicons",
    "@phosphor-icons/web": "phosphor", "@phosphor-icons/react": "phosphor",
    "phosphor-icons": "phosphor", "remixicon": "remixicon",
    "@tabler/icons": "tabler-icons", "@tabler/icons-react": "tabler-icons",
    "@tabler/icons-webfont": "tabler-icons", "boxicons": "boxicons",
    "iconify-icon": "iconify", "@iconify/react": "iconify",
    "@iconify/iconify": "iconify", "material-icons": "material-icons",
    "material-symbols": "material-symbols", "@mui/icons-material": "material-icons",
    "react-icons": "react-icons", "@radix-ui/react-icons": "radix-icons",
}
PREFIXES = {"@radix-ui/": "radix-ui", "@tsparticles/": "tsparticles",
            "@fortawesome/": "font-awesome", "@tabler/icons": "tabler-icons",
            "@fontsource/": "fontsource", "@fontsource-variable/": "fontsource"}
HOSTS = {
    "cdn.tailwindcss.com": "tailwindcss", "code.jquery.com": "jquery",
    "kit.fontawesome.com": "font-awesome", "use.fontawesome.com": "font-awesome",
    "ka-f.fontawesome.com": "font-awesome", "cdn.plot.ly": "plotly",
    "d3js.org": "d3", "unpkg.com/lucide": "lucide",
}
ICON_SETS = frozenset({
    "lucide", "heroicons", "font-awesome", "feather", "bootstrap-icons", "ionicons",
    "phosphor", "remixicon", "tabler-icons", "boxicons", "iconify",
    "material-icons", "material-symbols", "react-icons", "radix-icons"})
FONT_SERVICES = {
    "fonts.googleapis.com": "google-fonts", "fonts.gstatic.com": "google-fonts",
    "fonts.bunny.net": "bunny-fonts", "use.typekit.net": "adobe-fonts",
    "p.typekit.net": "adobe-fonts", "api.fontshare.com": "fontshare",
    "cdn.fontshare.com": "fontshare", "rsms.me": "rsms-inter",
}
CSS_FRAMEWORKS = ("tailwindcss", "bootstrap", "bulma", "foundation", "materialize",
                  "pico", "uikit", "semantic-ui", "mui", "chakra-ui", "antd",
                  "water.css", "shoelace")
FRAMEWORKS = ("next", "nuxt", "sveltekit", "astro", "react", "vue", "svelte",
              "angular", "solid", "preact", "lit", "alpinejs", "htmx", "jquery")
_NPM_PATH = re.compile(r"/(?:npm[/:])?((?:@[\w.-]{1,80}/)?[\w.-]{1,80})")
_LIBS_PATH = re.compile(r"/ajax/libs/([\w.-]{1,80})/")
_NPM_CDNS = frozenset({"cdn.jsdelivr.net", "unpkg.com", "esm.sh", "cdn.skypack.dev",
                       "ga.jspm.io", "jspm.dev", "cdn.esm.sh", "esm.run"})
_LIBS_CDNS = frozenset({"cdnjs.cloudflare.com", "ajax.googleapis.com"})
# One trailing ".min", "-3.7.1", "@2", "-v4.0.0-beta" or "-1.2.3.min" at a time.
_STEM_NOISE = re.compile(r"(?:[.-]min|[.@_-]v?\d{1,6}(?:\.\d{1,6}){0,3}"
                         r"(?:-[a-z]{1,10}\.?\d{0,6})?)$")
MAX_NAME = 200
_BUILTIN = frozenset({"fs", "path", "url", "http", "https", "os", "crypto", "util",
                      "events", "stream", "child_process", "process", "buffer"})


def package_name(specifier):
    """The npm package of a bare specifier: ``aos/dist/aos.css`` gives
    ``aos``; ``@scope/name/x`` gives ``@scope/name``."""
    parts = specifier.split("/")
    if specifier.startswith("@") and len(parts) > 1:
        return "/".join(parts[:2]).lower()
    return parts[0].lower()


def library_of_package(name):
    name = name.lower()
    if name in PACKAGES:
        return PACKAGES[name]
    for prefix, slug in PREFIXES.items():
        if name.startswith(prefix):
            return slug
    return None


def _from_url(url):
    """``(slug or None, host)`` for an absolute URL."""
    try:
        parts = urlsplit(url if not url.startswith("//") else "https:" + url)
    except ValueError:
        return None, ""
    host = (parts.hostname or "").lower()
    path = parts.path
    for key, slug in HOSTS.items():
        known_host, _, prefix = key.partition("/")
        if host == known_host and (not prefix
                                   or path.lower().startswith("/" + prefix)):
            return slug, host
    if host in _NPM_CDNS:
        match = _NPM_PATH.match(path)
        if match:
            return library_of_package(match.group(1)), host
    if host in _LIBS_CDNS:
        match = _LIBS_PATH.match(path)
        if match:
            return library_of_package(match.group(1)), host
    if host.endswith("bootstrapcdn.com"):
        lowered = path.lower()
        if "font-awesome" in lowered or "fontawesome" in lowered:
            return "font-awesome", host
        if "bootstrap" in lowered:
            return "bootstrap", host
    # A file name that names a library (https://example.com/js/jquery.min.js).
    return _from_file_name(path), host


def _from_file_name(path):
    name = path.rstrip("/").rsplit("/", 1)[-1].lower()
    stem = name.rsplit(".", 1)[0] if name.endswith((".js", ".css", ".mjs")) else name
    if len(stem) > MAX_NAME:
        return None
    for _ in range(4):
        shorter = _STEM_NOISE.sub("", stem)
        if shorter == stem:
            break
        stem = shorter
    if not stem:
        return None
    first = stem.split(".")[0]  # bootstrap.bundle, three.module, chart.umd
    return (library_of_package(stem) or library_of_package(first)
            or library_of_package(first + ".js"))


def is_url(target):
    lowered = target.lower()
    return lowered.startswith(("http://", "https://", "//"))


def font_service(target):
    """The web font service a URL loads from, or None."""
    if not is_url(target):
        return None
    try:
        host = (urlsplit(target if not target.startswith("//")
                         else "https:" + target).hostname or "").lower()
    except ValueError:
        return None
    return FONT_SERVICES.get(host)


def resolve(target, kind):
    """``(slug or None, delivery, unrecognised name or None)`` for a reference.

    ``delivery`` is ``cdn`` (an absolute URL), ``package`` (a bare module
    name or ``package.json`` entry), ``local`` (a relative path) or ``other``
    (``data:`` and similar). Font-service URLs give no library.
    """
    target = target.strip()
    lowered = target.lower()
    if is_url(target):
        if font_service(target):
            return None, "cdn", None
        slug, host = _from_url(target)
        return slug, "cdn", (None if slug else host or None)
    if lowered.startswith(("data:", "blob:", "javascript:", "mailto:", "#")) or \
            ":" in lowered.split("/")[0]:
        return None, "other", None
    if kind in ("module", "package", "importmap") and not lowered.startswith(
            (".", "/")):
        name = package_name(target)
        if name in _BUILTIN or name.startswith(("node:", "~", "$", "@/", "#"))                 or not name:
            return None, "package", None
        slug = library_of_package(name)
        return slug, "package", (None if slug else name)
    if kind in ("module",):
        return None, "local", None  # the output's own modules
    return _from_file_name(urlsplit(target).path if "?" in target else target), \
        "local", None
