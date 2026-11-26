"""Rendering in a real headless Chromium, with no network (T1.3)."""

import datetime
import gc
import json
import os
import socket
import threading
import time
from dataclasses import replace

import pytest

from renderer.browser import VARIANTS, BrowserUnavailable, Settings, render_page
from renderer_support import (
    PAGES, Png, TreeMemory, _descendants, require_chromium,
)

pytestmark = pytest.mark.browser

NAMES = ("desktop-light", "desktop-dark", "phone-light", "phone-dark")
DESKTOP, PHONE = VARIANTS[0], VARIANTS[2]


@pytest.fixture(scope="module", autouse=True)
def chromium():
    require_chromium()


def page(tmp_path, body, name="index.html"):
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    (site / name).write_text(
        '<!doctype html><meta name="viewport" content="width=device-width">'
        + body, encoding="utf-8")
    return site


# Long enough for a busy machine; tests of pages that never finish set their own.
PATIENT = 120.0
# A small cap for test pages, so a hostile one cannot use up the machine.
CAP = 1536


def one(site, tmp_path, variant=DESKTOP, timeout=PATIENT, memory_mb=CAP, **changes):
    settings = Settings(variants=(variant,), timeout=timeout, memory_mb=memory_mb,
                        **changes)
    result = render_page(site, "index.html", tmp_path / "out", settings)
    return result, result.variants[0]


def reports(result):
    """What a test page said about itself, through ``alert``."""
    return [d["message"] for d in result.dialogs]


# --- the three hand-made pages --------------------------------------------------


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    require_chromium()
    results = {}
    for name in ("bakery", "todo", "event"):
        out = tmp_path_factory.mktemp(name)
        results[name] = (render_page(PAGES / name, "index.html", out,
                                     Settings(timeout=PATIENT)), out)
    return results


@pytest.mark.parametrize("name", ["bakery", "todo", "event"])
def test_four_images_with_the_expected_dimensions(fixtures, name):
    result, out = fixtures[name]
    assert result.outcome == "ok", result
    assert [v.name for v in result.variants] == list(NAMES)
    assert sorted(p.name for p in out.iterdir()) == sorted(f"{n}.png" for n in NAMES)
    for variant in result.variants:
        width, scale, least = ((1440, 1, 900) if variant.name.startswith("desktop")
                               else (390, 2, 844))
        image = Png(out / variant.file)
        assert image.size == (variant.width, variant.height)
        assert image.width == width * scale
        assert image.height == max(least, variant.content_height) * scale
        assert not variant.truncated


def test_the_full_page_is_captured(fixtures):
    result, _ = fixtures["event"]
    assert all(v.content_height >= 2400 for v in result.variants)


@pytest.mark.parametrize("name, dark_mode", [("bakery", True), ("todo", True),
                                             ("event", False)])
def test_light_and_dark(fixtures, name, dark_mode):
    _, out = fixtures[name]
    for device in ("desktop", "phone"):
        light = (out / f"{device}-light.png").read_bytes()
        dark = (out / f"{device}-dark.png").read_bytes()
        assert (light != dark) is dark_mode
    if name == "bakery":
        assert Png(out / "desktop-light.png").pixel(5, 5) == (0xFB, 0xF6, 0xEE)
        assert Png(out / "desktop-dark.png").pixel(5, 5) == (0x17, 0x12, 0x0D)


def test_sections_revealed_on_scroll_are_visible(fixtures):
    _, out = fixtures["event"]
    image = Png(out / "desktop-light.png")
    # The rule under the last section is drawn only if it was revealed.
    assert image.pixel(700, image.height - 2) == (0x14, 0x21, 0x3D)


def test_blocked_and_missing_requests_are_recorded(fixtures):
    result, _ = fixtures["event"]
    assert result.blocked == ["https://fonts.googleapis.com/css2",
                              "https://cdn.example.com/confetti.js"]
    for name in ("bakery", "todo"):
        assert fixtures[name][0].blocked == []
        assert fixtures[name][0].missing == []


@pytest.mark.parametrize("name", ["todo", "event"])
def test_a_second_render_gives_the_same_images(fixtures, tmp_path, name):
    _, first = fixtures[name]
    render_page(PAGES / name, "index.html", tmp_path, Settings(timeout=PATIENT))
    for variant in NAMES:
        file = f"{variant}.png"
        assert (tmp_path / file).read_bytes() == (first / file).read_bytes(), variant


# --- clock, locale, timezone ------------------------------------------------------


def test_clock_locale_and_timezone_are_fixed(tmp_path):
    site = page(tmp_path, """<script>
      const start = new Date();
      setTimeout(() => alert([start.toISOString(), new Date().toISOString(),
        navigator.language, Intl.DateTimeFormat().resolvedOptions().timeZone,
        navigator.onLine].join(" ")), 4000);
    </script>""")
    result, _ = one(site, tmp_path)
    assert reports(result) == [
        "2027-03-09T12:00:00.000Z 2027-03-09T12:00:04.000Z en-US UTC false"]


def test_clock_locale_and_timezone_can_be_set(tmp_path):
    site = page(tmp_path, """<script>
      alert([new Date().toISOString(), navigator.language,
        Intl.DateTimeFormat().resolvedOptions().timeZone].join(" "))</script>""")
    result, _ = one(site, tmp_path, locale="de-DE", timezone="Asia/Tokyo",
                    clock=datetime.datetime(2030, 1, 2, 3, 4, 5,
                                            tzinfo=datetime.timezone.utc))
    assert reports(result) == ["2030-01-02T03:04:05.000Z de-DE Asia/Tokyo"]


def test_a_clock_without_a_time_zone_is_refused():
    with pytest.raises(ValueError):
        Settings(clock=datetime.datetime(2027, 3, 9, 12))


# --- isolation -------------------------------------------------------------------


class Listener:
    """Counts anything that reaches this machine over TCP or UDP."""

    def __init__(self):
        self.hits = []
        self.tcp = socket.socket()
        self.tcp.bind(("0.0.0.0", 0))
        self.tcp.listen(100)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("0.0.0.0", 0))
        self.tcp_port = self.tcp.getsockname()[1]
        self.udp_port = self.udp.getsockname()[1]
        for target in (self._accept, self._receive):
            threading.Thread(target=target, daemon=True).start()

    def _accept(self):
        while True:
            try:
                connection, _ = self.tcp.accept()
            except OSError:
                return
            self.hits.append("tcp")
            connection.close()

    def _receive(self):
        while True:
            try:
                data, _ = self.udp.recvfrom(2000)
            except OSError:
                return
            self.hits.append(f"udp {data[:20]!r}")

    def close(self):
        self.tcp.close()
        self.udp.close()


def addresses():
    """Loopback and, if there is one, this machine's network address."""
    found = ["127.0.0.1"]
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))  # sends nothing
        if probe.getsockname()[0] not in found:
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    return found


@pytest.fixture
def listener():
    server = Listener()
    yield server
    server.close()


def test_the_listener_hears_a_connection(listener):
    # Without this, "no hits" below would prove nothing.
    socket.create_connection(("127.0.0.1", listener.tcp_port)).close()
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender.sendto(b"hello", ("127.0.0.1", listener.udp_port))
    sender.close()
    deadline = time.monotonic() + 5
    while len(listener.hits) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(listener.hits) == 2


ATTACK = """
<link rel="stylesheet" href="http://HOST/css">
<link rel="preconnect" href="http://HOST">
<link rel="dns-prefetch" href="//localhost:TCP">
<link rel="prefetch" href="http://HOST/prefetch">
<link rel="preload" as="image" href="http://HOST/preload">
<link rel="prerender" href="http://HOST/prerender">
<link rel="modulepreload" href="http://HOST/module">
<link rel="icon" href="http://HOST/icon">
<link rel="manifest" href="http://HOST/manifest">
<script type="speculationrules">{"prerender":[{"source":"list","urls":["http://HOST/spec"]}],
 "prefetch":[{"source":"list","urls":["http://HOST/spec2"]}]}</script>
<style>@import url(http://HOST/import);
 @font-face { font-family: x; src: url(http://HOST/font); }
 body { font-family: x; background: url(http://HOST/bg); }</style>
<body>text
<img src="http://HOST/img" srcset="http://HOST/srcset 2x">
<video src="http://HOST/video" poster="http://HOST/poster" autoplay></video>
<iframe src="http://HOST/frame"></iframe>
<object data="http://HOST/object"></object>
<a id="ping" href="#x" ping="http://HOST/ping">a</a>
<a id="away" href="http://HOST/download" download>b</a>
<form id="form" action="http://HOST/form" method="post" target="_blank"><input name="a"></form>
<script>
const run = (f) => { try { const p = f(); if (p && p.catch) p.catch(() => {}); } catch (e) {} };
const frame = () => { const f = document.createElement("iframe");
  document.body.appendChild(f); return f.contentWindow; };
run(() => fetch("http://HOST/fetch"));
run(() => fetch("https://HOST/fetch-https", {mode: "no-cors", keepalive: true}));
run(() => { const x = new XMLHttpRequest(); x.open("GET", "http://HOST/xhr"); x.send(); });
run(() => navigator.sendBeacon("http://HOST/beacon", "data"));
run(() => new EventSource("http://HOST/events"));
run(() => new WebSocket("ws://HOST/socket?secret=1"));
run(() => { new (frame().WebSocket)("ws://HOST/frame-socket"); });
run(() => frame().fetch("http://HOST/frame-fetch"));
run(() => { const code = 'fetch("http://HOST/worker").catch(()=>{});'
  + 'try{new WebSocket("ws://HOST/worker-socket")}catch(e){}';
  const url = URL.createObjectURL(new Blob([code]));
  new Worker(url); new SharedWorker(url); });
run(() => navigator.serviceWorker.register("sw.js"));
for (const get of [() => window, frame]) {
  run(() => { const w = get();
    const peer = new (w.RTCPeerConnection || w.webkitRTCPeerConnection)({iceServers: [
      {urls: "stun:IP:UDP"},
      {urls: "turn:IP:TCP?transport=tcp", username: "a", credential: "b"},
      {urls: "turn:IP:UDP", username: "a", credential: "b"}]});
    peer.createDataChannel("d");
    // Also name the listener as the other end, so it is contacted directly.
    const other = new (w.RTCPeerConnection || w.webkitRTCPeerConnection)();
    return peer.createOffer().then(async (offer) => {
      await peer.setLocalDescription(offer);
      await other.setRemoteDescription(offer);
      const answer = await other.createAnswer();
      await peer.setRemoteDescription(answer);
      await peer.addIceCandidate({sdpMid: "0",
        candidate: "candidate:1 1 udp 2122260223 IP UDP typ host"}); }); });
}
run(() => new (frame().WebTransport)("https://IP:UDP/transport"));
run(() => new WebTransport("https://IP:UDP/transport"));
run(() => window.open("http://HOST/popup"));
run(() => window.open("index.html"));
run(() => document.getElementById("ping").click());
run(() => document.getElementById("away").click());
run(() => document.getElementById("form").submit());
setTimeout(() => { location.href = "http://HOST/leave"; }, 1000);
setTimeout(() => alert("still here " + location.href), 3000);
</script>
<meta http-equiv="refresh" content="1;url=http://HOST/refresh">
"""


def test_no_connection_leaves_the_browser(tmp_path, listener):
    for index, ip in enumerate(addresses()):
        host = f"{ip}:{listener.tcp_port}"
        body = (ATTACK.replace("HOST", host).replace("IP", ip)
                .replace("UDP", str(listener.udp_port))
                .replace("TCP", str(listener.tcp_port)))
        folder = tmp_path / str(index)
        folder.mkdir()
        result, variant = one(page(folder, body), folder)
        time.sleep(1)
        assert listener.hits == []
        assert variant.outcome == "ok", variant
        (said,) = reports(result)
        assert said.startswith("still here https://page.invalid/index.html")
        for vector in ("css", "fetch", "img", "popup", "leave"):
            assert f"http://{host}/{vector}" in result.blocked
        assert f"ws://{host}/socket" in result.blocked
        assert result.popups >= 1


def test_the_browser_flags_alone_stop_the_network(tmp_path, listener):
    """The second line of defence: with no request interception and no offline
    mode, the launch arguments still let nothing out."""
    from playwright.sync_api import sync_playwright

    from renderer.browser import launch_arguments

    ip = addresses()[-1]
    host = f"{ip}:{listener.tcp_port}"
    body = (ATTACK.replace("HOST", host).replace("IP", ip)
            .replace("UDP", str(listener.udp_port))
            .replace("TCP", str(listener.tcp_port)))
    body = body.split("<script>\nconst run")
    assert len(body) == 2
    # No navigation away: it would end the page before the rest has run.
    script = ("<script>\nconst run" + body[1]).split("run(() => window.open")[0]
    site = page(tmp_path, body[0] + script + "</script>")
    reserved = socket.socket()
    reserved.bind(("127.0.0.1", 0))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                chromium_sandbox=True,
                args=launch_arguments(reserved.getsockname()[1]))
            tab = browser.new_page()
            tab.goto((site / "index.html").as_uri(), wait_until="commit")
            tab.wait_for_timeout(5000)
            browser.close()
    finally:
        reserved.close()
    assert listener.hits == []


def test_files_outside_the_folder_cannot_be_read(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    site = page(tmp_path, """<body>
    <iframe src="SECRET"></iframe><img src="SECRET"><script src="SECRET"></script>
    <script>
    const tries = ["../secret.txt", "%2e%2e%2fsecret.txt", "..%5csecret.txt",
      "SECRET", "/%2e%2e/secret.txt", "ok.txt"];
    (async () => {
      const got = [];
      for (const url of tries) {
        try { const r = await fetch(url); got.push(r.status + ":" + await r.text()); }
        catch (e) { got.push("refused"); }
      }
      try { const x = new XMLHttpRequest(); x.open("GET", "SECRET", false); x.send();
            got.push("xhr:" + x.responseText); } catch (e) { got.push("refused"); }
      alert(JSON.stringify(got));
      location.href = "SECRET";
    })();
    </script>""".replace("SECRET", secret.as_uri()))
    (site / "ok.txt").write_text("fine", encoding="utf-8")
    result, variant = one(site, tmp_path)
    assert variant.outcome == "ok", variant
    (said,) = reports(result)
    assert "TOPSECRET" not in said
    assert json.loads(said)[-2:] == ["200:fine", "refused"]
    assert secret.as_uri() in result.blocked


def test_missing_local_files_are_recorded(tmp_path):
    site = page(tmp_path, '<link rel="stylesheet" href="style.css?v=1">'
                          '<img src="img/none.png">')
    result, variant = one(site, tmp_path)
    assert variant.outcome == "ok"
    assert result.missing == ["img/none.png", "style.css"]
    assert result.blocked == []


def test_another_page_of_the_folder_does_not_replace_the_entry(tmp_path):
    site = page(tmp_path, """<body style="background:#00ff00">
      <script>location.href = "other.html"</script>""")
    page(tmp_path, '<body style="background:#ff0000">', "other.html")
    _, variant = one(site, tmp_path)
    assert Png(tmp_path / "out" / variant.file).pixel(5, 5) == (0, 255, 0)


@pytest.mark.parametrize("leave", [
    'location.href = "https://example.com/a"',
    'location.replace("other.html")',
    'location.reload()',
    'setTimeout(() => document.forms[0].submit(), 0)',
    'document.head.insertAdjacentHTML("beforeend", '
    '"<meta http-equiv=refresh content=0;url=https://example.com/a>")',
], ids=["href", "replace", "reload", "form", "refresh"])
def test_leaving_while_loading_does_not_stop_the_render(tmp_path, leave):
    site = page(tmp_path, f"""<body style="margin:0">
      <form action="https://example.com/a"></form><script>{leave}</script>
      <div style="height:2000px;background:#00ff00"></div>""")
    (site / "other.html").write_text("<p>other", encoding="utf-8")
    _, variant = one(site, tmp_path)
    assert (variant.outcome, variant.height) == ("ok", 2000), variant
    assert Png(tmp_path / "out" / variant.file).pixel(5, 1500) == (0, 255, 0)


def test_a_form_sent_while_loading_still_gives_an_image(tmp_path):
    # The rest of the page may be lost, as the browser stops reading it.
    site = page(tmp_path, """<body style="background:#00ff00">
      <form action="https://example.com/a"></form>
      <script>document.forms[0].submit()</script>""")
    result, variant = one(site, tmp_path, timeout=40)
    assert variant.outcome == "ok", variant
    assert result.blocked == ["https://example.com/a"]
    assert Png(tmp_path / "out" / variant.file).pixel(5, 500) == (0, 255, 0)


def test_downloads_are_refused(tmp_path):
    site = page(tmp_path, """<body><a id="a" download="x.txt">x</a><script>
      const a = document.getElementById("a");
      a.href = URL.createObjectURL(new Blob(["data"])); a.click();</script>""")
    result, variant = one(site, tmp_path)
    assert variant.outcome == "ok"
    assert result.downloads == 1


def test_each_image_starts_from_a_fresh_browser(tmp_path):
    site = page(tmp_path, """<script>
      alert(String(localStorage.getItem("seen"))); localStorage.setItem("seen", "yes");
    </script>""")
    result = render_page(site, "index.html", tmp_path / "out",
                         Settings(timeout=PATIENT))
    assert reports(result) == ["null"]  # the same report each time, listed once
    assert result.dialog_count == 4


def test_the_chromium_sandbox_is_on(tmp_path):
    result, _ = one(page(tmp_path, "x"), tmp_path)
    assert "--proxy-server" in result.command_line
    assert "--no-sandbox" not in result.command_line


def test_images_of_an_earlier_render_are_removed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "desktop-light.png").write_bytes(b"old")
    _, variant = one(page(tmp_path, "<script>for (;;) {}</script>"), tmp_path,
                     timeout=3)
    assert variant.outcome == "failed"
    assert not (out / "desktop-light.png").exists()


def test_a_browser_that_cannot_start_is_not_a_page_result(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "empty"))
    with pytest.raises(BrowserUnavailable, match="playwright install chromium"):
        one(page(tmp_path, "x"), tmp_path)


# --- hostile pages -----------------------------------------------------------------


@pytest.mark.parametrize("body", [
    "<script>for (;;) {}</script>",
    "<body>x<script>setTimeout(() => { for (;;) {} }, 100)</script>",
    "<script>for (;;) alert('again')</script>",
    "<script>const spin = () => Promise.resolve().then(spin); onload = spin;</script>",
], ids=["loop", "loop-later", "alerts", "microtasks"])
def test_a_page_that_never_stops_is_given_up_on(tmp_path, body):
    started = time.monotonic()
    result, variant = one(page(tmp_path, body), tmp_path, timeout=6)
    assert time.monotonic() - started < 90
    assert (result.outcome, variant.outcome, variant.file) == ("failed", "failed", None)
    assert "6 seconds" in variant.error
    assert list((tmp_path / "out").glob("*.png")) == []


@pytest.mark.parametrize("script", [
    'setTimeout(() => { throw new Error("bug") }, 100)',
    'setInterval(() => { missing() }, 100)',
    'requestAnimationFrame(() => { throw new Error("bug") })',
    'setInterval(() => {}, 0)',
    'const again = () => setTimeout(again, 0); again()',
    'const frame = () => requestAnimationFrame(frame); frame()',
    'Object.defineProperty(document, "fonts", {value: null})',
    'throw new Error("bug")',
    'setTimeout(() => { throw new Error("Target crashed") }, 100)',
], ids=["timeout throws", "interval throws", "frame throws", "busy interval",
        "busy timeouts", "animation loop", "no fonts", "script throws",
        "speaks of a crash"])
def test_a_page_with_bugs_or_busy_timers_is_still_rendered(tmp_path, script):
    site = page(tmp_path, f"""<body style="margin:0"><script>{script}</script>
      <script>setTimeout(() => document.body.style.background = "#00ff00", 3000)
      </script>""")
    _, variant = one(site, tmp_path)
    assert variant.outcome == "ok", variant
    assert Png(tmp_path / "out" / variant.file).pixel(5, 500) == (0, 255, 0)


@pytest.mark.skipif(os.name != "nt", reason="the memory limit is Windows only")
def test_a_page_that_goes_on_past_the_cap_is_given_up_on(tmp_path):
    # Canvases until the cap refuses memory: a crash, or no end.
    site = page(tmp_path, """<script>const kept = []; for (;;) {
      const c = new OffscreenCanvas(8000, 8000).getContext("2d");
      c.fillRect(0, 0, 8000, 8000); c.getImageData(0, 0, 1, 1); kept.push(c); }
    </script>""")
    result, variant = one(site, tmp_path, memory_mb=700, timeout=30)
    assert (result.outcome, variant.outcome) == ("failed", "failed")
    assert "memory cap of 700 MB" in variant.error


def test_an_entry_with_an_awkward_name_loads(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    name = "my page (1) [é]#%.html"
    (site / name).write_text("<script>alert('loaded')</script>", encoding="utf-8")
    result = render_page(site, name, tmp_path / "out",
                         Settings(variants=(DESKTOP,), timeout=PATIENT))
    assert (result.outcome, reports(result)) == ("ok", ["loaded"])


def test_a_few_alerts_do_not_stop_a_render(tmp_path):
    site = page(tmp_path, "<script>alert(1); confirm(2); prompt(3)</script><h1>x</h1>")
    result, variant = one(site, tmp_path)
    assert variant.outcome == "ok"
    assert [d["type"] for d in result.dialogs] == ["alert", "confirm", "prompt"]


def test_a_huge_page_is_cut_at_the_height_cap(tmp_path):
    site = page(tmp_path, '<body style="margin:0"><div style="height:5000000px">x</div>'
                          '<div style="width:90000px;height:10px"></div>')
    _, variant = one(site, tmp_path)
    assert variant.outcome == "ok", variant
    assert (variant.width, variant.height, variant.truncated) == (1440, 8000, True)
    assert variant.content_height >= 5000000


def test_a_page_that_hides_its_size_still_renders(tmp_path):
    site = page(tmp_path, """<body><script>
      Object.defineProperty(Element.prototype, "scrollHeight", {get: () => NaN});
      window.scrollTo = () => { throw new Error("no") };</script>x""")
    _, variant = one(site, tmp_path)
    assert (variant.outcome, variant.width, variant.height) == ("ok", 1440, 900)


windows_only = pytest.mark.skipif(os.name != "nt",
                                  reason="the memory limit is Windows only")
# Room for what the sampling counts differently from the job.
SLACK = 100


@windows_only
def test_memory_is_limited(tmp_path):
    site = page(tmp_path, """<script>onload = () => setTimeout(() => {
      const kept = [];
      try { while (kept.length < 8) {
        const b = new Uint8Array(1 << 28); b.fill(1); kept.push(b); } }
      finally { alert("held " + kept.length); }
    }, 10)</script>""")
    result, variant = one(site, tmp_path, memory_mb=1024, timeout=40)
    assert result.memory_limited is True
    # Windows counts the refused request in the peak, so allow for one.
    assert 0 < result.peak_memory_mb <= 1024 + SLACK
    # Either the allocation failed under the limit, or the renderer died.
    for said in reports(result):
        assert int(said.split()[1]) * 256 < 1024
    assert reports(result) or variant.outcome == "failed"


@windows_only
def test_a_console_flood_stays_inside_the_memory_cap(tmp_path):
    # 40 messages of 16 MB from the page and as many from a worker, which has
    # its own console: bounded, so that even with no cap the machine copes.
    site = page(tmp_path, """<body><script>
      const flood = 'const s = "x".repeat(1 << 24);'
        + 'for (let i = 0; i < 40; i++) console.log(s + i);';
      new Worker(URL.createObjectURL(new Blob([flood])));
      eval(flood);
      const f = document.createElement("iframe"); document.body.appendChild(f);
      for (let i = 0; i < 10; i++) f.contentWindow.console.error("y".repeat(1 << 24));
    </script>""")
    with TreeMemory() as memory:
        result, variant = one(site, tmp_path, memory_mb=800, timeout=30)
    assert memory.own < 100  # the caller's process does not take the flood
    assert 0 < memory.started <= 800 + SLACK
    assert result.peak_memory_mb <= 800 + SLACK
    assert variant.outcome in ("ok", "failed"), variant


@windows_only
def test_errors_thrown_without_end_stay_inside_the_memory_cap(tmp_path):
    site = page(tmp_path, """<script>
      const s = "x".repeat(1 << 24); let n = 0;
      const again = () => { if (++n < 60) setTimeout(again, 10); throw new Error(s + n) };
      again();</script>""")
    with TreeMemory() as memory:
        result, variant = one(site, tmp_path, memory_mb=800, timeout=30)
    assert memory.own < 100
    assert memory.started <= 800 + SLACK
    assert variant.outcome in ("ok", "failed"), variant


@windows_only
def test_graphics_memory_stays_inside_the_cap(tmp_path):
    # 20 textures of 64 MB each, held by the graphics process.
    site = page(tmp_path, """<script>
      const kept = [];
      for (let i = 0; i < 20; i++) {
        const gl = document.createElement("canvas").getContext("webgl2");
        if (!gl) break;
        const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
        gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA8, 4096, 4096);
        const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0,
                                gl.TEXTURE_2D, t, 0);
        gl.clearColor(1, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT); gl.finish();
        kept.push(gl);
      }
      alert("contexts " + kept.length);</script>""")
    with TreeMemory() as memory:
        result, variant = one(site, tmp_path, memory_mb=800, timeout=40)
    assert 0 < memory.started <= 800 + SLACK
    assert result.peak_memory_mb <= 800 + SLACK
    assert variant.outcome in ("ok", "failed"), variant


def test_webgl_still_draws(tmp_path):
    site = page(tmp_path, """<body style="margin:0"><canvas width="100" height="100">
      </canvas><script>
      const gl = document.querySelector("canvas").getContext("webgl2",
        {preserveDrawingBuffer: true});
      gl.clearColor(0, 1, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);</script>""")
    _, variant = one(site, tmp_path)
    assert Png(tmp_path / "out" / variant.file).pixel(50, 50) == (0, 255, 0)


def test_the_console_is_silenced_in_every_frame(tmp_path):
    site = page(tmp_path, """<body><script>
      const f = document.createElement("iframe"); document.body.appendChild(f);
      alert([window, f.contentWindow].map((w) => ["log", "debug", "error", "table"]
        .map((n) => { const d = Object.getOwnPropertyDescriptor(w.console, n);
          return [d.writable, d.configurable, /native code/.test(String(d.value))]
            .join(); }).join(" ")).join(" "))</script>""")
    result, _ = one(site, tmp_path)
    assert reports(result) == [" ".join(["false,false,false"] * 8)]


def test_navigation_reports_are_limited(tmp_path):
    site = page(tmp_path, """<body><script>onload = () => {
      for (let i = 0; i < 500; i++) location.href = "https://example.com/" + i; };
    </script>""")
    result, variant = one(site, tmp_path)
    assert variant.outcome == "ok", variant
    assert 0 < len(result.blocked) + result.blocked_dropped <= 100


def test_timeouts_print_nothing(tmp_path, capfd):
    one(page(tmp_path, "<script>for (;;) {}</script>"), tmp_path, timeout=4)
    gc.collect()
    assert capfd.readouterr() == ("", "")


def test_the_bytes_served_to_one_image_are_bounded(tmp_path):
    site = page(tmp_path, """<script>(async () => {
      const got = await Promise.all(Array.from({length: 12}, (_, i) =>
        fetch("big.txt?" + i).then(async (r) => (await r.text()).length, () => 0)));
      alert(got.filter((n) => n === 1048576).length + " "
        + got.filter((n) => !n).length);
    })();</script>""")
    (site / "big.txt").write_bytes(b"x" * (1 << 20))
    result, variant = one(site, tmp_path, max_served_mb=5)
    assert variant.outcome == "ok", variant
    assert reports(result) == ["4 8"]  # the page itself uses part of the 5 MB
    assert result.over_budget == 8


def test_only_listed_files_are_served(tmp_path):
    site = page(tmp_path, """<script>(async () => {
      const got = [];
      for (const url of ["a.txt", "b.txt"]) got.push((await fetch(url)).status);
      alert(got.join(" "));
    })();</script>""")
    (site / "a.txt").write_text("a")
    (site / "b.txt").write_text("b")
    result = render_page(site, "index.html", tmp_path / "out",
                         Settings(variants=(DESKTOP,), timeout=PATIENT, memory_mb=CAP),
                         files=["index.html", "a.txt"])
    assert reports(result) == ["200 404"]
    assert result.missing == ["b.txt"]


@windows_only
def test_a_render_process_that_hangs_is_ended_with_all_it_started(
        tmp_path, monkeypatch):
    # The caller's own deadline, set to pass before the page's time limit.
    monkeypatch.setattr("renderer.browser.OVERHEAD", -55.0)
    site = page(tmp_path, "<script>for (;;) {}</script>")
    started = time.monotonic()
    _, variant = one(site, tmp_path, timeout=60)
    assert time.monotonic() - started < 40
    assert (variant.outcome, variant.file) == ("failed", None)
    assert "60 seconds" in variant.error
    deadline = time.monotonic() + 10
    while _descendants(os.getpid()) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert _descendants(os.getpid()) == set()


def test_the_batch_goes_on_after_a_hostile_page(tmp_path):
    bad = page(tmp_path, "<script>for (;;) {}</script>")
    settings = Settings(variants=(DESKTOP, PHONE), timeout=5, memory_mb=CAP)
    assert render_page(bad, "index.html", tmp_path / "a", settings).outcome == "failed"
    good = render_page(PAGES / "bakery", "index.html", tmp_path / "b",
                       replace(settings, timeout=PATIENT))
    assert good.outcome == "ok"


# --- phone layout --------------------------------------------------------------


def test_a_page_with_no_viewport_tag_is_shrunk_to_the_phone_width(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        '<!doctype html><body style="margin:0">'
        '<div style="display:flex;height:400px">'
        '<div style="flex:1;background:#ff0000"></div>'
        '<div style="flex:1;background:#0000ff"></div></div>', encoding="utf-8")
    _, variant = one(site, tmp_path, PHONE)
    assert variant.content_width == 980
    image = Png(tmp_path / "out" / variant.file)
    assert image.width == 780
    # Both halves of the wide layout are in the picture, as on a real phone.
    assert image.pixel(100, 100) == (255, 0, 0)
    assert image.pixel(700, 100) == (0, 0, 255)
    assert abs(image.height - 844 * 2) <= 4
