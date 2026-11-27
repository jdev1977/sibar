"""Command line of the answer checker (T2.10): ``python -m checker``.

    python -m checker --records FILE [--record-id ID] [--answers FILE]
    python -m checker --task TYPE/TASK --level L2 [--response FILE] [--answers FILE]

``--records`` adds a ``checker`` entry to the math and engineering records of
a record file and rewrites it; ``--task`` grades one response and prints the
result as JSON. See checker/README.md.
"""

import argparse
import json
import sys

from checker.answers import AnswersError, read_answers_file
from checker.formulas import LEVELS
from checker.grade import SUSPECTED
from checker.records import CheckRefused, evaluate_response, references, run_file
from extractors.common.response import MAX_TEXT

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m checker",
        description="Grade the final answers of math and engineering outputs "
                    "against the reference answers, without running any of them.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", metavar="FILE",
                        help="a record file: add checker entries and rewrite it")
    source.add_argument("--task", metavar="TYPE/TASK",
                        help="grade one response for this task and print the result")
    parser.add_argument("--record-id", action="append", default=[], metavar="ID",
                        help="with --records: this record only (repeatable)")
    parser.add_argument("--level", choices=LEVELS, help="with --task: the level")
    parser.add_argument("--response", metavar="FILE",
                        help="with --task: the response text")
    parser.add_argument("--answers", metavar="FILE",
                        help="an answers file (YAML or JSON), put over the found values")
    parser.add_argument("--no-extract", action="store_true",
                        help="with --records: grade the answers file alone")
    return parser


def _one(args):
    reference = references().get(args.task)
    if reference is None:
        raise CheckRefused(f"no reference file for {args.task!r}")
    if args.level is None or not (args.response or args.answers):
        raise CheckRefused("--task needs --level, and --response or --answers")
    text = supplied = None
    if args.response and not args.no_extract:
        with open(args.response, "rb") as handle:
            text = handle.read(4 * MAX_TEXT).decode("utf-8-sig", "replace")
    if args.answers:
        entries = read_answers_file(args.answers)
        if len(entries) != 1:
            raise CheckRefused("with --task the answers file holds one entry")
        supplied = next(iter(entries.values()))
    detail = evaluate_response(reference, args.level, text, supplied)
    print(json.dumps(detail, indent=2, ensure_ascii=True))


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.task:
            _one(args)
            return EXIT_OK
        counts = run_file(args.records, args.record_id, args.answers,
                          extract=not args.no_extract, say=print)
        print(", ".join(f"{name} {count}" for name, count in sorted(counts.items()))
              or "no records to check")
        if counts[SUSPECTED]:
            print(f"{SUSPECTED} is neither right nor wrong: it needs review (supply "
                  "the value, or confirm or reject it under review: in an answers file)")
        return EXIT_FAILED if counts["error"] else EXIT_OK
    except (CheckRefused, AnswersError, OSError, ValueError) as error:
        print(f"refused: {error}")
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
