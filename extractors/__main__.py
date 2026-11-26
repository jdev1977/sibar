"""Command line of the extractors (T1.4): ``python -m extractors``.

    python -m extractors --records FILE [--record-id ID] [--only NAME]
    python -m extractors --dir FOLDER [--type website] [--only NAME]
    python -m extractors --list

``--records`` adds features to the records of a record file and rewrites it;
``--dir`` prints the features of the files in a folder as JSON. See
``docs/extractors.md``.
"""

import argparse
import json
import sys

from extractors.base import Inputs, run_extractors
from extractors.records import ExtractRefused, extract_file
from extractors.registry import all_extractors, by_name, extractors_for

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m extractors",
        description="Extract countable features from generated outputs, "
                    "without running them.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", metavar="FILE",
                        help="a record file: add features and rewrite it")
    source.add_argument("--dir", metavar="FOLDER",
                        help="a folder of output files: print its features")
    source.add_argument("--list", action="store_true",
                        help="list the extractors and their versions")
    parser.add_argument("--record-id", action="append", default=[], metavar="ID",
                        help="with --records: this record only (repeatable)")
    parser.add_argument("--only", action="append", default=[], metavar="NAME",
                        help="run only this extractor (repeatable)")
    parser.add_argument("--type", default="website",
                        help="with --dir: the project type (default %(default)s)")
    return parser


def _directory(args):
    extractors = list(extractors_for(args.type))
    if args.only:
        known = by_name()
        unknown = sorted(set(args.only) - set(known))
        if unknown:
            raise ExtractRefused(f"no extractor named {', '.join(unknown)}")
        extractors = [e for e in extractors if e.name in set(args.only)]
    if not extractors:
        raise ExtractRefused(f"no extractors for type {args.type!r}")
    results = run_extractors(extractors, Inputs.from_directory(args.dir))
    shown = {name: {"version": version, "values": values}
             for name, (version, values) in results.items()}
    print(json.dumps(shown, indent=2, ensure_ascii=True))
    return any(values["status"] == "error" for _, values in results.values())


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.list:
            for extractor in all_extractors():
                print(f"{extractor.name} {extractor.version} "
                      f"({extractor.project_type}): {extractor.summary}")
            return EXIT_OK
        if args.dir:
            return EXIT_FAILED if _directory(args) else EXIT_OK
        counts = extract_file(args.records, args.record_id, args.only)
        print(f"{counts['records']} records, {counts['error']} extractor errors")
        return EXIT_FAILED if counts["error"] else EXIT_OK
    except (ExtractRefused, OSError, ValueError) as error:
        print(f"refused: {error}")
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
