"""``python -m tagger``: tag outputs, compare taggings, make a human tag file.

    python -m tagger tag ...         tag run records with a tagging model
    python -m tagger agreement ...   agreement of two taggings (docs/rubrics.md)
    python -m tagger template ...    a blank human tag file and reading sheets

See ``tagger/README.md``.
"""

import argparse
import sys

from tagger import agreement, run


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m tagger",
                                     description="Rubric tagging (T2.6).")
    commands = parser.add_subparsers(dest="command", required=True)
    run.add_arguments(commands.add_parser(
        "tag", help="tag run records with a tagging model (batch API)"))
    agreement.add_agreement_arguments(commands.add_parser(
        "agreement", help="agreement between two taggings"))
    agreement.add_template_arguments(commands.add_parser(
        "template", help="a blank human tag file for a sample of records"))
    return parser


def main(argv=None, **kwargs):
    args = build_parser().parse_args(argv)
    if args.command == "tag":
        return run.run_tag(args, **kwargs)
    if args.command == "agreement":
        return agreement.run_agreement(args, out=kwargs.get("out", print))
    return agreement.run_template(args, out=kwargs.get("out", print))


if __name__ == "__main__":
    sys.exit(main())
