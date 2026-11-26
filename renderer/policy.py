"""What a page may read, and how what it may not read is written down.

A page is served from a made-up origin, :data:`ORIGIN`. No server exists for
it: the browser's requests are answered from the page's folder, through
:func:`local_file`, and every other request is refused.
"""

from pathlib import Path
from urllib.parse import unquote, urlsplit

from runner.record import _is_relative_path

HOST = "page.invalid"  # ".invalid" can never be a real name (RFC 2606)
ORIGIN = f"https://{HOST}/"  # https, so pages get the APIs of a secure context
MAX_URL = 200

CONTENT_TYPES = {
    "html": "text/html", "htm": "text/html", "css": "text/css",
    "js": "text/javascript", "mjs": "text/javascript", "json": "application/json",
    "svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg",
    "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "ico": "image/x-icon", "txt": "text/plain", "csv": "text/csv",
    "xml": "application/xml", "woff": "font/woff", "woff2": "font/woff2",
    "ttf": "font/ttf", "otf": "font/otf", "mp4": "video/mp4",
    "webm": "video/webm", "mp3": "audio/mpeg", "wav": "audio/wav",
    "wasm": "application/wasm",
}


def local_path(url):
    """The relative path an :data:`ORIGIN` URL asks for, or None if the URL is
    another origin's or the path is not a plain path inside the folder.

    A folder (a path ending ``/``) means its ``index.html``.
    """
    if not url.startswith(ORIGIN):
        return None
    path = url[len(ORIGIN):].split("#", 1)[0].split("?", 1)[0]
    path = unquote(path)
    if not path or path.endswith("/"):
        path += "index.html"
    return path if _is_relative_path(path) else None


def local_file(root, url):
    """The file under ``root`` that ``url`` may read, or None."""
    path = local_path(url)
    if path is None:
        return None
    try:
        base = Path(root).resolve()
        # resolve() follows links, so a link out of the folder is refused.
        target = base.joinpath(*path.split("/")).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            return None
    except (OSError, ValueError):
        return None
    return target


def content_type(path):
    kind = CONTENT_TYPES.get(Path(path).suffix[1:].lower(),
                             "application/octet-stream")
    textual = kind.startswith("text/") or kind in ("application/json",
                                                   "image/svg+xml")
    return kind + "; charset=utf-8" if textual else kind


def sanitize_url(url):
    """``url`` fit to be stored: no user name, query or fragment, at most
    :data:`MAX_URL` characters. For ``data:`` and other URLs without a host
    only the scheme is kept (``file:`` keeps its path)."""
    try:
        parts = urlsplit(url)
        if parts.scheme in ("http", "https", "ws", "wss", "ftp"):
            host = parts.netloc.rsplit("@", 1)[-1]
            text = f"{parts.scheme}://{host}{parts.path}"
        elif parts.scheme == "file":
            text = f"file://{parts.netloc}{parts.path}"
        else:
            text = f"{parts.scheme}:"
    except ValueError:
        return "(unreadable URL)"
    # Printable ASCII only: the page chose this text.
    return "".join(c if " " < c <= "~" else "?" for c in text)[:MAX_URL]


class BlockLog:
    """Distinct sanitized URLs in order of first use, at most ``limit``;
    ``dropped`` counts further distinct ones."""

    def __init__(self, limit=100):
        self.limit = limit
        self.entries = []
        self._seen = set()
        self.dropped = 0

    def add(self, url):
        self.add_text(sanitize_url(url))

    def add_text(self, text):
        if text in self._seen:
            return
        if len(self.entries) < self.limit:
            self._seen.add(text)
            self.entries.append(text)
            return
        # Remember only so many, however many a page invents.
        if len(self._seen) < self.limit * 100:
            self._seen.add(text)
            self.dropped += 1
