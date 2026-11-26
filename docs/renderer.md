# Renderer

`renderer/` (task T1.3) takes screenshots of a generated web page in headless
Chromium with no network: desktop and phone width, light and dark. The pages
are untrusted model output.

## Setup

After `pip install -r requirements.txt`, fetch Chromium once. It goes to
Playwright's cache in the user profile; nothing is installed system-wide.

    .venv/Scripts/python -m playwright install chromium

## Use

    python -m renderer --records data/runs/<batch-id>/records.jsonl
    python -m renderer --records FILE --record-id ID --force
    python -m renderer --dir FOLDER [--out FOLDER] [--entry PATH]

| Option | Meaning | Default |
|---|---|---|
| `--records FILE` | Render the records of a record file | |
| `--record-id ID` | Only this record, of any project type (repeatable) | `website` records with status `ok` or `truncated` |
| `--force` | Render again records that already have a render | off |
| `--dir FOLDER` | Render the one page in a folder | |
| `--out FOLDER` | With `--dir`: where the images and `render.json` go; not inside the page's folder | `<folder>-render` beside it |
| `--entry PATH` | With `--dir`: the HTML file to open | chosen as below |
| `--clock` | The page's date and time, with a time zone | `2027-03-09T12:00:00+00:00` |
| `--timezone`, `--locale` | | `UTC`, `en-US` |
| `--settle-ms` | Page time run after loading | 5000 |
| `--timeout` | Real seconds allowed for each image | 30 |
| `--max-height` | Tallest image, in CSS pixels of the screen | 8000 |
| `--memory-mb` | Memory cap for one browser (Windows only) | 4096 |

Exit codes: 0 every render is `ok`; 1 some are `failed` or `error`; 2 nothing
(more) could be rendered: bad options, a bad or busy record file, or no usable
Chromium.

Render a whole batch with the same settings. The settings are stored with each
render, so a mix can be found, but images made with different settings should
not be compared.

## The entry file

The first of these among the `.html` and `.htm` files:

1. `index.html` or `index.htm`, the shallowest one;
2. a complete document (it has a doctype or an `<html>` tag) before a fragment;
3. the shallowest;
4. the largest;
5. the first by name.

With no HTML file the render is `failed` with the error `no HTML file`. The
chosen file and the candidates (up to 20) are stored, so a wrong choice among
several pages can be seen. For a record, only the files listed in the record
are considered, and the page sees only its `extracted/` folder.

## The images

| Name | Viewport (CSS px) | Device pixels per CSS px | Image width |
|---|---|---|---|
| `desktop-light`, `desktop-dark` | 1440 x 900 | 1 | 1440 |
| `phone-light`, `phone-dark` | 390 x 844, mobile and touch emulation | 2 | 780 |

Light and dark set `prefers-color-scheme`. A page with only a manual theme
switch looks the same in both.

**Full page, not just the first screen.** Each image shows the whole page from
the top: at least one screen high, at most `--max-height` (so 8000 px on
desktop and 16000 px on a phone). A taller page is cut and marked
`truncated`. The first screen is the top of the image. `vh` units keep the
viewport's value. Content inside the page's own scrolling boxes is not
unrolled.

Width is fixed. On desktop, content wider than the screen is cut off
(`content_width` records how wide it was). A page that is wider than a phone,
usually because it has no viewport `<meta>` tag, is shown shrunk to fit, as a
phone browser shows it, down to a quarter of its size.

## Making renders repeatable

- **Clock.** The page's time starts at `--clock` (noon on March 9, 2027, as
  [leak-check.md](leak-check.md) suggests: the dated briefs then show a mix of
  overdue and upcoming items). It stands still while loading, then runs
  `--settle-ms` of page time, 100 ms at each scroll step and 1000 ms before
  the screenshot. Timers and animation frames follow this clock. Timer delays
  below 4 ms are raised to 4 ms.
- **Scrolling.** The page is scrolled to the bottom one screen at a time and
  back, so that sections shown on scroll appear.
- **Animations.** Taken with Playwright's `animations="disabled"`: finite CSS
  animations and transitions jump to their end, endless ones return to their
  start. `prefers-reduced-motion` stays `no-preference`.
- **Random numbers.** `Math.random` is replaced by a seeded generator
  (not inside workers; `crypto` random numbers are not changed).
- Fixed locale, time zone, viewport and scale; hidden text cursor.

Two renders on the same machine give the same bytes for the test pages. This is
not guaranteed for every page (video, canvas drawn from real elapsed time,
workers), and **not across machines**: installed fonts and the Chromium build
change the pixels. The Playwright and Chromium versions are stored.

## Isolation

The page is served from the made-up origin `https://page.invalid/`. It may read
the files in its own folder and nothing else. It cannot open the network, other
files, other pages or windows, or downloads.

| Layer | What it does |
|---|---|
| Request interception | Every request is answered from the folder or refused. Paths with `..`, backslashes, drive letters or links leading out are refused. Popups get nothing; WebSockets are closed without connecting |
| Offline mode | The browser context is offline; service workers are blocked; no permissions are granted |
| Launch arguments | No host name resolves; all traffic goes to a proxy port where nothing listens (loopback included); WebRTC may not send outside the proxy; QUIC, DNS prefetch, pings and background networking are off |
| Script setup | `RTCPeerConnection` and `WebTransport` are removed; leaving the page is cancelled before it starts |
| Chromium sandbox | On (Playwright's default is off). A browser that reports `--no-sandbox` is not used |
| Disposable browser | Each image has a new browser and profile, ended afterwards |
| Limits | A time limit per image; on Windows a job object caps the memory of the browser's processes; JavaScript heap capped; downloads refused; dialogs dismissed; files over 25 MB not served |

The tests check with a TCP and UDP listener on this machine that nothing
arrives, both normally and with only the launch arguments in force.

Limits of this protection: it relies on Chromium's sandbox for anything that
breaks out of the page, so keep Playwright current. The memory cap is applied
just after the browser starts and only on Windows; elsewhere the time limit and
Chromium's own limits apply. This is not a virtual machine: do not point the
renderer at pages built to attack the browser itself.

## What blocked resources do to the images

**Pages that load anything from the web (CSS frameworks from a CDN, web fonts,
icon sets, chart or animation libraries, remote images) do not look as they
would online.** Text falls back to local fonts, a page styled by a CDN
framework may be nearly unstyled, and a script that needs a missing library
stops. Nothing is downloaded or substituted. Extractors and reviewers must
read `blocked` before judging a screenshot: it lists each refused URL without
user name, query or fragment, cut to 200 characters (the first 100 distinct
ones; `blocked_dropped` counts the rest).

`missing` lists files the page asked for in its own folder that are not there.
This often means a code block had no file name and was saved as `block-NN.css`
(see [record-format.md](record-format.md) and `runner/files.py`), or that a
name was changed to make it safe.

## What is stored

For a record, images go to `files/<record_id>/render/` beside the record file,
and the record gets one entry in `checks`, replacing an earlier render:

| Key | Value |
|---|---|
| `name`, `tool`, `tool_version` | `render`, `renderer`, the renderer's version |
| `outcome` | `ok`: all four images. `failed`: the page's doing (no HTML file, never finished, crashed); not tried again without `--force`, so after a run on an overloaded machine, re-render time-outs with `--record-id ID --force`. `error`: the renderer's doing (stored files missing or changed, an unexpected browser error); tried again on the next run |
| `files` | The images made (a render can have some of the four) |
| `detail` | `entry`, `candidates`, `candidate_count`, `settings`, `playwright`, `browser`, `memory_limited`, `variants` (per image: outcome, viewport, scale, image and content size, `truncated`, error), `blocked`, `blocked_dropped`, `missing`, `dialogs` (up to 20 distinct), `dialog_count`, `popups`, `downloads`, and `error` when there is one |

`dialogs` and URLs are text chosen by the page. Treat them as untrusted.

With `--dir`, the same entry is written to `render.json` in the output folder.

The record file is rewritten after each record, under the same lock the runner
takes, so the renderer refuses a file a run is writing, and the reverse. It
also refuses a file with bad or unfinished lines rather than drop them.

## Tests

    .venv/Scripts/python -m pytest -k renderer
    .venv/Scripts/python -m pytest -m "not browser"

Tests marked `browser` are skipped with a message when Chromium cannot start.
The three hand-made pages are in `tests/fixtures/pages/`.
