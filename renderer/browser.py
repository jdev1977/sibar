"""Screenshots of one untrusted page in headless Chromium, with no network.

Four layers keep the page in (docs/renderer.md): every request is answered
from the page's folder or refused; the browser is in offline mode; its launch
arguments resolve no host name, send everything to a proxy that is not there
and allow no WebRTC traffic outside it; and the Chromium sandbox stays on.

Every image is made by a browser of its own, which is thrown away afterwards.
"""

import asyncio
import base64
import datetime
import math
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import quote

from renderer.limits import ProcessLimit
from renderer.policy import ORIGIN, BlockLog, content_type, local_file, local_path

# Noon on March 9, 2027: see prompts/website/leak-check.md and docs/leak-check.md.
DEFAULT_CLOCK = datetime.datetime(2027, 3, 9, 12, tzinfo=datetime.timezone.utc)
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_DIALOGS = 20
MAX_TEXT = 300
# A phone browser zooms out at most this far to fit a page that is too wide.
MAX_SHRINK = 4
LOCAL_REFUSAL = "Not allowed to load local resource: "
# The init script's console message for a navigation it stopped.
LEFT = "renderer-stopped-navigation:"
MIN_TIMER_MS = 4  # as browsers do for repeated timers

# Playwright's own words for a dead renderer, after the name of the call. An
# error thrown by the page comes after "Error:", so it cannot pass for this.
_CRASH = re.compile(r"[\w.]+: (Target|Page) crashed")

# Runs in every frame before the page's own scripts.
INIT_SCRIPT = """(() => {
  for (const name of ["RTCPeerConnection", "webkitRTCPeerConnection",
                      "WebTransport"]) {
    Object.defineProperty(window, name,
                          {value: undefined, writable: false, configurable: false});
  }
  // The page stays on its document: leaving is stopped before it starts, as a
  // refused request halfway through loading can leave the browser waiting.
  if (window === top && window.navigation) {
    navigation.addEventListener("navigate", (event) => {
      if (event.cancelable && !event.destination.sameDocument
          && event.downloadRequest === null) {
        event.preventDefault();
        console.debug("%s" + event.destination.url);
      }
    });
  }
  // The same "random" numbers every time (mulberry32).
  let state = 0x2545f491;
  Math.random = () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
})();""" % LEFT


# Runs after the stand-in clock is installed. Without a floor, a 0 ms
# interval would stop the stand-in clock's time from moving.
TIMER_SCRIPT = """(() => {
  for (const name of ["setTimeout", "setInterval"]) {
    const original = window[name];
    window[name] = (handler, delay, ...rest) =>
      original(handler, Math.max(Number(delay) || 0, %d), ...rest);
  }
})();""" % MIN_TIMER_MS


@dataclass(frozen=True)
class Variant:
    name: str
    width: int  # viewport, in CSS pixels
    height: int
    scale: int  # device pixels per CSS pixel
    mobile: bool
    scheme: str  # prefers-color-scheme


VARIANTS = tuple(
    Variant(f"{device}-{scheme}", width, height, scale, mobile, scheme)
    for device, width, height, scale, mobile in (
        ("desktop", 1440, 900, 1, False), ("phone", 390, 844, 2, True))
    for scheme in ("light", "dark"))


@dataclass(frozen=True)
class Settings:
    clock: datetime.datetime = DEFAULT_CLOCK
    timezone: str = "UTC"
    locale: str = "en-US"
    settle_ms: int = 5000  # page time run after loading
    timeout: float = 30.0  # seconds for one image
    max_height: int = 8000  # CSS pixels of the screen
    memory_mb: int = 4096  # for all processes of one browser (Windows)
    variants: Tuple[Variant, ...] = VARIANTS

    def __post_init__(self):
        if self.clock.utcoffset() is None:
            raise ValueError("clock: needs a time zone")
        if not (self.timeout > 0 and math.isfinite(self.timeout)):
            raise ValueError("timeout: must be more than 0 seconds")
        if self.settle_ms < 0 or self.max_height < 1 or self.memory_mb < 256:
            raise ValueError("settle_ms must be at least 0, max_height at least 1 "
                             "and memory_mb at least 256")


@dataclass(frozen=True)
class VariantResult:
    name: str
    outcome: str  # "ok", "failed" (the page's doing) or "error" (ours)
    file: Optional[str] = None  # name in the output directory
    width: Optional[int] = None  # image size, in pixels
    height: Optional[int] = None
    content_width: Optional[int] = None  # page size, in CSS pixels
    content_height: Optional[int] = None
    truncated: bool = False  # the page is taller than the image
    error: Optional[str] = None


@dataclass
class PageResult:
    variants: list = field(default_factory=list)
    blocked: list = field(default_factory=list)  # refused URLs, shortened
    blocked_dropped: int = 0
    missing: list = field(default_factory=list)  # asked for, not in the folder
    dialogs: list = field(default_factory=list)  # distinct {"type", "message"}
    dialog_count: int = 0
    popups: int = 0
    downloads: int = 0
    browser_version: str = ""
    command_line: str = ""  # holds local paths: not for storing
    memory_limited: bool = False

    @property
    def outcome(self):
        outcomes = {variant.outcome for variant in self.variants}
        if "error" in outcomes:
            return "error"
        return "failed" if "failed" in outcomes else "ok"


class BrowserUnavailable(Exception):
    """Chromium cannot be started safely: no page can be rendered."""


def launch_arguments(proxy_port):
    """Chromium arguments that cut the browser off from every network."""
    return [
        "--host-resolver-rules=MAP * ~NOTFOUND",
        # Nothing listens on this port. "<-loopback>" sends even this
        # machine's own addresses to it.
        f"--proxy-server=http://127.0.0.1:{proxy_port}",
        "--proxy-bypass-list=<-loopback>",
        # Both spellings: builds differ in which they read.
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-quic",
        "--dns-prefetch-disable",
        "--no-pings",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--js-flags=--max-old-space-size=512",
        "--enable-automation",  # lets the sandbox check read the command line
    ]


class _Log:
    """What the page did, over all its images."""

    def __init__(self):
        self.result = PageResult()
        self.blocked = BlockLog()
        self.missing = BlockLog()

    def dialog(self, kind, message):
        self.result.dialog_count += 1
        entry = {"type": kind, "message": _printable(message)}
        if len(self.result.dialogs) < MAX_DIALOGS and entry not in self.result.dialogs:
            self.result.dialogs.append(entry)

    def finish(self):
        self.result.blocked = self.blocked.entries
        self.result.blocked_dropped = self.blocked.dropped
        self.result.missing = sorted(self.missing.entries)
        return self.result


def _printable(text):
    """Page-chosen text fit to store: cut, with no lone surrogates."""
    return text[:MAX_TEXT].encode("utf-8", "replace").decode("utf-8")


async def _guard(context, page, root, entry_url, log):
    """Answer every request of ``context`` from ``root`` or refuse it."""
    from playwright.async_api import Error

    entered = False

    async def handle(route):
        nonlocal entered
        request = route.request
        url = request.url
        navigation = request.is_navigation_request()
        try:
            frame = request.frame
            own = frame.page == page
        except Error:  # a popup or worker with no page of ours
            frame, own = None, False
        try:
            if navigation and own and frame == page.main_frame:
                # The entry loads once; the page may not go anywhere else.
                if entered or url != entry_url:
                    log.blocked.add(url)
                    await route.fulfill(status=204)  # stay on this document
                    return
                entered = True
            path = local_file(root, url) if own else None
            if (path is not None and request.method in ("GET", "HEAD")
                    and path.stat().st_size <= MAX_FILE_BYTES):
                await route.fulfill(
                    status=200, body=path.read_bytes(),
                    headers={"content-type": content_type(path),
                             "cache-control": "no-store"})
                return
            wanted = local_path(url) if own else None
            if wanted is not None:
                if wanted != "favicon.ico":  # the browser asks by itself
                    log.missing.add_text(wanted[:MAX_TEXT])
                await route.fulfill(status=404, body="")
                return
            log.blocked.add(url)
            if navigation:
                await route.fulfill(status=204)
            else:
                await route.abort("blockedbyclient")
        except (Error, OSError):
            try:
                await route.abort("failed")
            except Error:
                pass  # the page or browser has gone

    async def socket_opened(web_socket):
        # Never connected to a server.
        log.blocked.add(web_socket.url)
        await web_socket.close()

    def console(message):
        # Chromium refuses file: URLs itself, before any request is made.
        if message.text.startswith(LOCAL_REFUSAL):
            log.blocked.add(message.text[len(LOCAL_REFUSAL):].strip())
        elif message.text.startswith(LEFT):
            log.blocked.add(message.text[len(LEFT):].strip())

    async def dialog(box):
        log.dialog(box.type, box.message)
        try:
            await box.dismiss()
        except Error:
            pass

    async def popup(other):
        if other == page:
            return
        log.result.popups += 1
        try:
            await other.close()
        except Error:
            pass

    def download(_):
        log.result.downloads += 1

    await context.route("**/*", handle)
    await context.route_web_socket(lambda url: True, socket_opened)
    context.on("page", popup)
    page.on("console", console)
    page.on("dialog", dialog)
    page.on("download", download)


async def _shrink(browser, png, variant, width, height):
    """``png``, a picture ``width`` CSS pixels wide, scaled to the phone."""
    shown = max(1, round(height * variant.width / width))
    context = await browser.new_context(
        viewport={"width": variant.width, "height": shown},
        device_scale_factor=variant.scale)
    page = await context.new_page()
    await page.set_content(
        "<style>html,body{margin:0}img{display:block}</style>"
        f'<img width="{variant.width}" height="{shown}" '
        f'src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}">')
    return await page.screenshot()


async def _capture(browser, root, entry, variant, settings, log, crashed):
    """Load the page and return ``(png, content size, truncated)``."""
    from playwright.async_api import Error, TimeoutError as PlaywrightTimeout

    context = await browser.new_context(
        viewport={"width": variant.width, "height": variant.height},
        device_scale_factor=variant.scale, is_mobile=variant.mobile,
        has_touch=variant.mobile, color_scheme=variant.scheme,
        reduced_motion="no-preference", locale=settings.locale,
        timezone_id=settings.timezone, offline=True, service_workers="block",
        accept_downloads=False)
    await context.add_init_script(INIT_SCRIPT)
    page = await context.new_page()
    page.on("crash", lambda _: crashed.set())
    entry_url = ORIGIN + quote(entry)
    await _guard(context, page, root, entry_url, log)
    # Page time stands still except when run_for moves it.
    await page.clock.install(time=settings.clock - datetime.timedelta(seconds=1))
    await page.clock.pause_at(settings.clock)
    await page.add_init_script(TIMER_SCRIPT)

    async def tolerate(call):
        """Await ``call``, passing over errors that are the page's own, such as
        a timer that throws (time moves on) or a replaced browser function."""
        try:
            await call
        except PlaywrightTimeout:
            raise
        except Error as error:
            if page.is_closed() or crashed.is_set() or _CRASH.match(str(error)):
                raise

    await page.goto(entry_url, wait_until="commit", timeout=settings.timeout * 1000)
    try:
        # Half the time for loading leaves half for the picture.
        await page.wait_for_load_state("load", timeout=settings.timeout * 500)
    except PlaywrightTimeout:
        pass  # a refused navigation can hide the event; a stuck page fails below
    await tolerate(page.evaluate("document.fonts.ready.then(() => true)"))
    await tolerate(page.clock.run_for(settings.settle_ms))

    devtools = await context.new_cdp_session(page)

    async def measure():
        # From the browser itself: the page's scripts cannot change these.
        metrics = await devtools.send("Page.getLayoutMetrics")
        view, content = metrics["cssLayoutViewport"], metrics["cssContentSize"]
        width = variant.width
        if variant.mobile:
            width = min(max(view["clientWidth"], width), width * MAX_SHRINK)
        screen = max(view["clientHeight"], variant.height) if variant.mobile \
            else variant.height
        cap = settings.max_height * width // variant.width
        return (width, screen, cap, math.ceil(content["width"]),
                math.ceil(content["height"]))

    async def scroll_to(y):
        await tolerate(page.evaluate(
            "y => window.scrollTo({top: y, left: 0, behavior: 'instant'})", y))
        await asyncio.sleep(0.05)  # real time, for scroll observers
        await tolerate(page.clock.run_for(100))

    # Scroll through the page, so that parts shown on scroll are shown.
    position = 0
    while True:
        _, screen, cap, _, tall = await measure()
        position += screen
        if position >= min(tall, cap):
            break
        await scroll_to(position)
    await scroll_to(0)
    await tolerate(page.clock.run_for(1000))
    await asyncio.sleep(0.1)

    width, screen, cap, content_width, content_height = await measure()
    height = min(max(content_height, screen), cap)
    png = await page.screenshot(
        full_page=True, clip={"x": 0, "y": 0, "width": width, "height": height},
        animations="disabled", caret="hide", timeout=settings.timeout * 1000)
    if width > variant.width:
        png = await _shrink(browser, png, variant, width, height)
    return png, (content_width, content_height), content_height > cap


async def _render_variant(playwright, root, entry, out, variant, settings, proxy_port,
                          log):
    from playwright.async_api import Error, TimeoutError as PlaywrightTimeout

    try:
        browser = await playwright.chromium.launch(
            headless=True, chromium_sandbox=True,
            args=launch_arguments(proxy_port))
    except Error as error:
        raise BrowserUnavailable(
            "Chromium did not start; install it with `python -m playwright "
            f"install chromium` ({str(error).splitlines()[0]})") from error
    limit, closed = None, False
    try:
        devtools = await browser.new_browser_cdp_session()
        command = await devtools.send("Browser.getBrowserCommandLine")
        log.result.command_line = " ".join(command["arguments"])
        if "--no-sandbox" in command["arguments"]:
            raise BrowserUnavailable("Chromium started without its sandbox")
        processes = await devtools.send("SystemInfo.getProcessInfo")
        pid = next(p["id"] for p in processes["processInfo"] if p["type"] == "browser")
        limit = ProcessLimit(pid, settings.memory_mb)
        log.result.memory_limited = limit.memory_limited
        log.result.browser_version = browser.version

        crashed = asyncio.Event()
        browser.on("disconnected", lambda _: crashed.set())
        work = asyncio.ensure_future(
            _capture(browser, root, entry, variant, settings, log, crashed))
        crash = asyncio.ensure_future(crashed.wait())
        done, _ = await asyncio.wait(
            {work, crash}, timeout=settings.timeout,
            return_when=asyncio.FIRST_COMPLETED)
        failure = None
        if work not in done:
            work.cancel()
            failure = ("the page crashed" if crash in done else
                       f"the page did not finish within {settings.timeout:g} seconds")
        crash.cancel()
        if failure is None:
            try:
                png, (content_width, content_height), truncated = work.result()
            except PlaywrightTimeout:
                failure = (f"the page did not finish within {settings.timeout:g} "
                           "seconds")
            except Error as error:
                if crashed.is_set() or _CRASH.match(str(error)):
                    failure = "the page crashed"
                else:
                    raise
        if failure is not None:
            # End the browser first: it releases the cancelled call.
            closed = await _close(browser)
            limit.end(closed)
            limit, closed = None, True
            await asyncio.wait({work}, timeout=5)
            if work.done() and not work.cancelled():
                work.exception()  # seen: it is the failure reported here
            return VariantResult(variant.name, "failed", error=failure)
        name = f"{variant.name}.png"
        (out / name).write_bytes(png)
        return VariantResult(
            variant.name, "ok", file=name,
            width=int.from_bytes(png[16:20], "big"),
            height=int.from_bytes(png[20:24], "big"),
            content_width=content_width, content_height=content_height,
            truncated=truncated)
    except Error as error:
        message = str(error).splitlines()[0].replace(str(root), "<folder>")
        return VariantResult(variant.name, "error", error=_printable(message))
    finally:
        closed = closed or await _close(browser)
        if limit is not None:
            limit.end(closed)


async def _close(browser):
    """Close ``browser``; False if it did not answer in time."""
    try:
        await asyncio.wait_for(browser.close(), 5)
    except Exception:
        return False
    return True


async def _render(root, entry, out, settings):
    from playwright.async_api import async_playwright

    log = _Log()
    # A port that stays bound but never listens: the browser's proxy.
    nowhere = socket.socket()
    try:
        nowhere.bind(("127.0.0.1", 0))
        async with async_playwright() as playwright:
            for variant in settings.variants:
                log.result.variants.append(await _render_variant(
                    playwright, root, entry, out, variant, settings,
                    nowhere.getsockname()[1], log))
    finally:
        nowhere.close()
    return log.finish()


def render_page(root, entry, out_dir, settings=Settings()):
    """Render ``entry`` (a ``/`` separated path under ``root``) into
    ``out_dir``, one ``<variant>.png`` per variant; return a :class:`PageResult`.

    The page can read the files under ``root`` and nothing else. Images of an
    earlier render in ``out_dir`` are removed first. Raises
    :class:`BrowserUnavailable` if Chromium cannot be used.
    """
    root = Path(root).resolve()
    if local_file(root, ORIGIN + quote(entry)) is None:
        raise ValueError(f"{entry!r} is not a file in the page's folder")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for variant in VARIANTS:
        (out / f"{variant.name}.png").unlink(missing_ok=True)
    return asyncio.run(_render(root, entry, out, settings))
