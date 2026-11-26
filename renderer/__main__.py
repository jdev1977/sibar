"""Command line of the renderer (T1.3): ``python -m renderer``.

    python -m renderer --records data/runs/<batch>/records.jsonl [--record-id ID]
    python -m renderer --dir FOLDER [--out FOLDER] [--entry PATH]

See ``docs/renderer.md``.
"""

import argparse
import datetime
import sys
from pathlib import Path

from renderer.browser import BrowserUnavailable, Settings
from renderer.records import RenderRefused, render_directory, render_file

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2


def build_parser():
    defaults = Settings()
    parser = argparse.ArgumentParser(
        prog="python -m renderer",
        description="Screenshot generated web pages offline: desktop and phone, "
                    "light and dark.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", metavar="FILE",
                        help="a record file; renders its website records")
    source.add_argument("--dir", metavar="FOLDER", help="a folder holding one page")
    parser.add_argument("--record-id", action="append", default=[], metavar="ID",
                        help="with --records: render this record only (repeatable)")
    parser.add_argument("--force", action="store_true",
                        help="with --records: render again records already rendered")
    parser.add_argument("--out", metavar="FOLDER",
                        help="with --dir: where the images go (default "
                             "<folder>-render beside it)")
    parser.add_argument("--entry", metavar="PATH",
                        help="with --dir: the HTML file to open")
    parser.add_argument("--clock", default=defaults.clock.isoformat(),
                        help="the page's date and time, with a time zone "
                             "(default %(default)s)")
    parser.add_argument("--timezone", default=defaults.timezone,
                        help="default %(default)s")
    parser.add_argument("--locale", default=defaults.locale,
                        help="default %(default)s")
    parser.add_argument("--settle-ms", type=int, default=defaults.settle_ms,
                        help="page time to run after loading (default %(default)s)")
    parser.add_argument("--timeout", type=float, default=defaults.timeout,
                        help="seconds allowed for each image (default %(default)s)")
    parser.add_argument("--max-height", type=int, default=defaults.max_height,
                        help="tallest image, in CSS pixels (default %(default)s)")
    parser.add_argument("--memory-mb", type=int, default=defaults.memory_mb,
                        help="memory cap of one browser, Windows only "
                             "(default %(default)s)")
    return parser


def _settings(args):
    try:
        clock = datetime.datetime.fromisoformat(args.clock)
    except ValueError:
        raise RenderRefused(f"--clock: {args.clock!r} is not a date and time such "
                            "as 2027-03-09T12:00:00Z") from None
    try:
        return Settings(clock=clock, timezone=args.timezone, locale=args.locale,
                        settle_ms=args.settle_ms, timeout=args.timeout,
                        max_height=args.max_height, memory_mb=args.memory_mb)
    except ValueError as error:
        raise RenderRefused(str(error)) from None


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    wrong = (("--out", args.out), ("--entry", args.entry)) if args.records else (
        ("--record-id", args.record_id), ("--force", args.force))
    for option, value in wrong:
        if value:
            parser.error(f"{option} cannot be used with "
                         f"{'--records' if args.records else '--dir'}")
    try:
        settings = _settings(args)
        if args.records:
            counts = render_file(args.records, settings, args.record_id, args.force)
            print(", ".join(f"{number} {outcome}"
                            for outcome, number in sorted(counts.items()))
                  or "no records to render")
            bad = counts["failed"] + counts["error"]
        else:
            folder = Path(args.dir).resolve()
            out = args.out or folder.with_name(folder.name + "-render")
            check = render_directory(args.dir, out, settings, args.entry)
            error = check["detail"].get("error")
            print(f"{check['outcome']}: {len(check['files'])} images in {out}"
                  + (f" ({error})" if error else ""))
            for url in check["detail"].get("blocked", []):
                print(f"blocked: {url}")
            bad = check["outcome"] != "ok"
    except (RenderRefused, BrowserUnavailable, ValueError, OSError) as error:
        print(f"refused: {error}")
        return EXIT_REFUSED
    except KeyboardInterrupt:
        print("interrupted; finished renders are saved")
        return 130
    return EXIT_FAILED if bad else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
