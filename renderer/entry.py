"""Which HTML file of an output is the page to render."""

import re
from pathlib import Path

_HTML_SUFFIXES = (".html", ".htm")
_DOCUMENT = re.compile(rb"<!doctype\s+html|<html[\s>]", re.IGNORECASE)


def find_entry(directory, only=None):
    """``(entry, candidates)`` for the HTML files under ``directory``.

    Paths are relative and use ``/``. ``only`` limits the choice to those
    paths. The entry is None when there is no HTML file; otherwise it is the
    first of this order:

    1. ``index.html`` or ``index.htm``, the shallowest one;
    2. a complete document (it has a doctype or an ``<html>`` tag) before a
       fragment;
    3. the shallowest;
    4. the largest;
    5. the first by name.
    """
    root = Path(directory)
    paths = (only if only is not None
             else (p.relative_to(root).as_posix() for p in root.rglob("*")))
    candidates = sorted(
        path for path in paths
        if path.lower().endswith(_HTML_SUFFIXES)
        and root.joinpath(*path.split("/")).is_file())

    def order(path):
        data = root.joinpath(*path.split("/")).read_bytes()
        name = path.rsplit("/", 1)[-1].lower()
        depth = path.count("/")
        if name in ("index.html", "index.htm"):
            return (0, depth, 0, 0, path)
        return (1, 0 if _DOCUMENT.search(data) else 1, depth, -len(data), path)

    return (min(candidates, key=order) if candidates else None), candidates
