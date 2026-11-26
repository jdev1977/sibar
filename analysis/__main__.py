"""Command line for the metrics (T1.6): ``python -m analysis``.

    python -m analysis tables --records FILE... --batch ID [--batch ID...]
    python -m analysis stability --records FILE... --batch ID --model ID \\
        [--compare 5,10]

Both write JSON and Markdown under data/analysis/ (gitignored) unless --out
names another folder. See analysis/README.md.
"""

import argparse
import sys
from pathlib import Path

from analysis import report, stability, tables
from analysis.runs import Refused, select_files
from analysis.spec import ROOT, SpecError, load_spec

OUT_DIR = ROOT / "data" / "analysis"
EXIT_OK, EXIT_REFUSED = 0, 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m analysis",
        description="Fingerprint tables, metrics and the stability check (docs/metrics.md).")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("tables", "fingerprint tables and every metric"),
                       ("stability", "the stability check for one model (T1.8)")):
        p = sub.add_parser(name, help=text, description=text)
        p.add_argument("--records", nargs="+", required=True, metavar="FILE",
                       help="record files (data/runs/<batch-id>/records.jsonl)")
        p.add_argument("--batch", action="append", required=True, metavar="ID",
                       help="a batch id of the batch group (repeat for several)")
        p.add_argument("--type", default="website",
                       help="project type, as in analysis/<type>/ (default website)")
        p.add_argument("--out", metavar="DIR",
                       help=f"output folder (default {OUT_DIR.relative_to(ROOT)}/<batch group>)")
        if name == "stability":
            p.add_argument("--model", required=True, help="the model id to check")
            p.add_argument("--compare", default="5,10", metavar="SMALL,BIG",
                           help="run counts to compare: 5,10 (default) or 10,20 (the repeat)")
    return parser


def _out_dir(args):
    if args.out:
        return Path(args.out)
    return OUT_DIR / "+".join(report.safe_name(b) for b in args.batch)


def _compare(text):
    try:
        small, big = (int(part) for part in text.split(","))
    except ValueError:
        raise Refused("--compare must be two whole numbers, such as 5,10") from None
    return small, big


def main(argv=None, out=print):
    args = build_parser().parse_args(argv)
    try:
        spec = load_spec(args.type)
        batches = list(dict.fromkeys(args.batch))
        selection = select_files(args.records, spec, batches)
        folder = _out_dir(args)
        if args.command == "tables":
            if not selection.runs:
                raise Refused(f"no records of type {args.type} in batch group "
                              f"{', '.join(batches)}")
            result = tables.compute(selection, spec)
            stem = folder / f"{spec.project_type}-tables"
            json_path = report.write(stem.with_suffix(".json"), report.dumps(result))
            md_path = report.write(stem.with_suffix(".md"), report.tables_markdown(result))
            for model, body in result["models"].items():
                for level, data in body["levels"].items():
                    fp = data["fingerprint"]
                    out(f"{model} {level}: {fp['outcomes']['N']} runs, "
                        f"flags: {', '.join(fp['flags']) or 'none'}")
        else:
            small, big = _compare(args.compare)
            result = stability.check(selection, spec, args.model, small, big)
            stem = folder / (f"{spec.project_type}-stability-"
                             f"{report.safe_name(args.model)}-{small}v{big}")
            json_path = report.write(stem.with_suffix(".json"), report.dumps(result))
            md_path = report.write(stem.with_suffix(".md"), report.stability_markdown(result))
            out(f"verdict: {result['verdict']}. {result['consequence']}")
            if result["verdict"] != "not run":
                kinds = result["kinds"]
                out(f"score {report.frac(result['score'])}; counted "
                    f"{len(result['counted'])}: kept {kinds['kept']}, new {kinds['new']}, "
                    f"lost {kinds['lost']}, reversed {kinds['reversed']}, changed sets "
                    f"{kinds['changed']}; reversals {result['reversals']}; established "
                    f"defaults {result['established_defaults'][0]} -> "
                    f"{result['established_defaults'][1]}, growth "
                    f"{report.frac(result['growth'])}")
                for change in result["changes"]:
                    out(f"  {change['variable']}: {change['kind']}")
            if result["cells_short"]:
                out("cells short of usable runs: " + ", ".join(result["cells_short"]))
            if result["selection"]["runner_command"]:
                out(f"cells to run: {len(result['selection']['cells'])}; "
                    f"{result['selection']['runner_command']}")
        for note in selection.notes:
            out(f"note: {note}")
        out(f"wrote {json_path}")
        out(f"wrote {md_path}")
        return EXIT_OK
    except (Refused, SpecError, OSError) as error:
        out(f"refused: {error}")
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
