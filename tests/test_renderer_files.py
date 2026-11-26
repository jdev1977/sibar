"""Entry file choice and the file and URL rules of the renderer (T1.3)."""

import pytest

from renderer.entry import find_entry
from renderer.policy import ORIGIN, BlockLog, local_file, sanitize_url


def make(root, files):
    for path, content in files.items():
        target = root.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


FULL = "<!doctype html><html><body>x</body></html>"


# --- the entry file ----------------------------------------------------------


@pytest.mark.parametrize(
    "files, expected",
    [
        # index.html wins, whatever else there is
        ({"a.html": FULL * 9, "index.html": "<p>"}, "index.html"),
        ({"Index.HTM": "<p>", "a.html": FULL}, "Index.HTM"),
        # the shallowest index.html, before any other page
        ({"b/c/index.html": FULL, "z/index.html": "<p>", "a.html": FULL}, "z/index.html"),
        # a single page, whatever its name
        ({"block-01.html": "<p>", "style.css": "p{}"}, "block-01.html"),
        # several, no index: a whole document before a fragment
        ({"a.html": "<div>" * 50, "b.html": FULL}, "b.html"),
        # then the shallowest
        ({"a/deep.html": FULL * 3, "top.html": FULL}, "top.html"),
        # then the largest
        ({"a.html": FULL, "b.html": FULL + "<!-- more -->"}, "b.html"),
        # then the name
        ({"b.html": FULL, "a.html": FULL}, "a.html"),
    ],
)
def test_entry_choice(tmp_path, files, expected):
    entry, candidates = find_entry(make(tmp_path, files))
    assert entry == expected
    assert candidates == sorted(p for p in files if not p.endswith(".css"))


def test_no_html_file_means_no_entry(tmp_path):
    assert find_entry(make(tmp_path, {"main.py": "print(1)"})) == (None, [])


def test_entry_choice_can_be_limited_to_listed_files(tmp_path):
    make(tmp_path, {"index.html": FULL, "page.html": FULL})
    assert find_entry(tmp_path, ["page.html", "gone.html"]) == ("page.html", ["page.html"])


# --- which file a URL may read ------------------------------------------------


@pytest.fixture
def site(tmp_path):
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    return make(tmp_path / "site", {
        "index.html": FULL, "css/a b.css": "p{}", "docs/index.html": FULL})


@pytest.mark.parametrize(
    "path, expected",
    [
        ("index.html", "index.html"),
        ("css/a%20b.css?v=2#x", "css/a b.css"),
        ("", "index.html"),
        ("docs/", "docs/index.html"),
    ],
)
def test_url_reads_a_file_in_the_folder(site, path, expected):
    assert local_file(site, ORIGIN + path) == site.resolve().joinpath(*expected.split("/"))


@pytest.mark.parametrize(
    "url",
    [
        ORIGIN + "../secret.txt",
        ORIGIN + "%2e%2e/secret.txt",
        ORIGIN + "css/%2e%2e%2f%2e%2e%2fsecret.txt",
        ORIGIN + "..%5csecret.txt",
        ORIGIN + "%2f%2fserver/share/x",
        ORIGIN + "C:/Windows/win.ini",
        ORIGIN + "C%3a%5cWindows%5cwin.ini",
        ORIGIN + "index.html%00.css",
        ORIGIN + "index.html::$DATA",
        ORIGIN + "NUL",
        ORIGIN + "missing.css",
        "https://example.com/index.html",
        "http://page.invalid/index.html",
        "https://page.invalid.example.com/index.html",
        "https://page.invalid:444/index.html",
        "file:///C:/Windows/win.ini",
    ],
)
def test_url_cannot_read_anything_else(site, url):
    assert local_file(site, url) is None


def test_a_link_that_leaves_the_folder_is_refused(site, tmp_path):
    try:
        (site / "link.txt").symlink_to(tmp_path / "secret.txt")
    except OSError:
        pytest.skip("this system does not allow making symbolic links")
    assert local_file(site, ORIGIN + "link.txt") is None


# --- recording blocked URLs ----------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://cdn.example.com/lib.js?data=" + "A" * 5000 + "#frag",
         "https://cdn.example.com/lib.js"),
        ("http://user:password@example.com:81/a", "http://example.com:81/a"),
        ("wss://example.com/socket?t=1", "wss://example.com/socket"),
        ("file:///C:/Windows/win.ini", "file:///C:/Windows/win.ini"),
        ("data:text/html,<p>" + "A" * 5000, "data:"),
        ("mailto:someone@example.com", "mailto:"),
        ("https://[broken", "(unreadable URL)"),
    ],
)
def test_blocked_urls_are_shortened(url, expected):
    assert sanitize_url(url) == expected


def test_a_long_blocked_url_is_cut():
    assert len(sanitize_url("https://example.com/" + "a" * 5000)) == 200


def test_block_log_removes_repeats_and_is_bounded():
    log = BlockLog(limit=3)
    for number in (1, 1, 2, 3, 4, 5):
        log.add(f"https://example.com/{number}?q={number}")
    assert log.entries == [f"https://example.com/{n}" for n in (1, 2, 3)]
    assert log.dropped == 2
