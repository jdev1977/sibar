"""The calibration sample of docs/rubrics.md, "Calibration (T2.5)":
``python -m tagger sample``.

    python -m tagger sample --type pipeline --records FILE... --size 100 --human 5 --seed 1 --models pilot --out FOLDER

**The 100**: every task gets an equal share (16 or 17 of 100 for six tasks),
and within a task the records are spread as evenly as the pool allows over
the levels, both wordings and the models. **The 30 for the Human**: ``--human``
per task from the 100, covering every level and every model in each task's
share where the 100 hold them. The choice depends only on the seed and on
which records are in the pool, not on the order of the input files.

Writes ``records.jsonl`` (the 100, for ``python -m tagger tag --records``),
``ids.txt``, ``human-records.jsonl`` (for ``python -m tagger template
--records``), ``human-ids.txt`` and ``sample.yaml`` (the counts). Nothing is
overwritten.
"""

import random
from collections import Counter
from pathlib import Path

import yaml

from runner.models import load_models
from runner.record import LEVELS, RecordError, write_records
from tagger.rubric import RubricError, load_checked

DIMENSIONS = (("level",), ("wording",), ("model_id",))
PAIRS = (("level", "model_id"), ("level", "wording"), ("model_id", "wording"))


class SampleError(ValueError):
    """The sample cannot be drawn; the message says why."""


def _value(record, fields):
    return tuple(record[f] for f in fields)


def _pick(candidates, count):
    """``count`` of ``candidates`` (already in a seeded random order), each
    pick the one that keeps levels, wordings and models most even: first no
    value above the least-used one of its dimension, then the fewest uses,
    then the fewest uses of each pair of dimensions; ties go to the earlier."""
    chosen, left = [], list(candidates)
    used = {dims: Counter() for dims in DIMENSIONS + PAIRS}
    values = {dims: {_value(r, dims) for r in candidates} for dims in DIMENSIONS}
    for _ in range(count):
        def score(record):
            excess = 0
            for dims in DIMENSIONS:
                least = min(used[dims][v] for v in values[dims])
                excess += used[dims][_value(record, dims)] - least
            single = sum(used[d][_value(record, d)] for d in DIMENSIONS)
            pairs = sum(used[d][_value(record, d)] for d in PAIRS)
            return excess, single, pairs
        best = min(range(len(left)), key=lambda i: score(left[i]))
        record = left.pop(best)
        chosen.append(record)
        for dims in used:
            used[dims][_value(record, dims)] += 1
    return chosen


def _order(records):
    return sorted(records, key=lambda r: (r["task_id"], r["level"], r["wording"],
                                          r["model_id"], r["run_index"], r["record_id"]))


def _shuffled(records, rng):
    records = sorted(records, key=lambda r: r["record_id"])
    rng.shuffle(records)
    return records


def stratified(records, rubric, size, *, seed, models=None):
    """The sample of ``size`` records of the rubric's type with status ok."""
    if size < 1:
        raise SampleError("--size must be 1 or more")
    allowed = set(models) if models else None
    pool = [r for r in records if r["project_type"] == rubric.project_type
            and r["status"] == "ok" and r["task_id"] in rubric.tasks
            and r["level"] in LEVELS and r["wording"] is not None
            and (allowed is None or r["model_id"] in allowed)]
    tasks = sorted(rubric.tasks)
    rng = random.Random(seed)
    base, extra = divmod(size, len(tasks))
    larger = set(rng.sample(tasks, extra))
    chosen = []
    for task in tasks:
        quota = base + (task in larger)
        candidates = _shuffled([r for r in pool if r["task_id"] == task], rng)
        if len(candidates) < quota:
            raise SampleError(f"task {task}: {len(candidates)} usable records "
                              f"(status ok), {quota} needed")
        chosen += _pick(candidates, quota)
    return _order(chosen)


def human_subset(chosen, rubric, per_task, *, seed):
    """``per_task`` records of each task from ``chosen``, spread over levels,
    models and wordings as :func:`stratified` spreads them."""
    rng = random.Random(f"human:{seed}")
    picked = []
    for task in sorted(rubric.tasks):
        candidates = _shuffled([r for r in chosen if r["task_id"] == task], rng)
        if len(candidates) < per_task:
            raise SampleError(f"task {task}: {len(candidates)} records in the sample, "
                              f"{per_task} needed for the Human")
        picked += _pick(candidates, per_task)
    return _order(picked)


def coverage_gaps(subset, rubric, models):
    """What each task's records lack: a level, or a model of ``models``."""
    gaps = []
    for task in sorted(rubric.tasks):
        mine = [r for r in subset if r["task_id"] == task]
        missing = sorted(set(LEVELS) - {r["level"] for r in mine}) + \
            sorted(set(models) - {r["model_id"] for r in mine})
        if missing:
            gaps.append(f"{task}: no {', '.join(missing)}")
    return gaps


def counts(records):
    return {"records": len(records),
            "per_task": dict(sorted(Counter(r["task_id"] for r in records).items())),
            "per_level": dict(sorted(Counter(r["level"] for r in records).items())),
            "per_wording": dict(sorted(Counter(r["wording"] for r in records).items())),
            "per_model": dict(sorted(Counter(r["model_id"] for r in records).items()))}


# --- command line ------------------------------------------------------------------------


def add_sample_arguments(parser):
    parser.add_argument("--type", required=True, dest="project_type")
    parser.add_argument("--rubric-version", default="1")
    parser.add_argument("--records", nargs="+", required=True, metavar="FILE",
                        help="run record files (the T2.9 or pilot records)")
    parser.add_argument("--size", type=int, default=100, help="records to tag (default 100)")
    parser.add_argument("--human", type=int, default=5, metavar="N",
                        help="records per task for the Human, from the sample "
                             "(default 5; 0 for none)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--models", default="all",
                        help="all (default: every model in the records), pilot "
                             "(models.yaml), or ids separated by commas")
    parser.add_argument("--models-file", default="models.yaml")
    parser.add_argument("--out", required=True, metavar="FOLDER")


def _models(text, path):
    if text == "all":
        return None
    if text == "pilot":
        return list(load_models(path).pilot)
    return [part.strip() for part in text.split(",") if part.strip()]


def _write_ids(path, records):
    path.write_text("".join(r["record_id"] + "\n" for r in records), encoding="utf-8")


def run_sample(args, out=print):
    from tagger.agreement import AgreementError, _records
    try:
        rubric = load_checked(args.project_type, args.rubric_version)
        models = _models(args.models, args.models_file)
        records = _records(args.records)
        chosen = stratified(records, rubric, args.size, seed=args.seed, models=models)
        human = (human_subset(chosen, rubric, args.human, seed=args.seed)
                 if args.human else [])
        folder = Path(args.out)
        names = ["records.jsonl", "ids.txt", "human-records.jsonl", "human-ids.txt",
                 "sample.yaml"]
        existing = [n for n in names if (folder / n).exists()]
        if existing:
            raise SampleError(f"{folder / existing[0]} exists; a sample is never overwritten")
        folder.mkdir(parents=True, exist_ok=True)
        write_records(folder / "records.jsonl", chosen)
        _write_ids(folder / "ids.txt", chosen)
        if human:
            write_records(folder / "human-records.jsonl", human)
            _write_ids(folder / "human-ids.txt", human)
        every_model = models or sorted({r["model_id"] for r in chosen})
        gaps = coverage_gaps(human, rubric, every_model) if human else []
        summary = {"rubric": rubric.name, "seed": args.seed, "size": args.size,
                   "models": models or "all", "inputs": [str(p) for p in args.records],
                   "sample": counts(chosen),
                   "human": counts(human) if human else None,
                   "human_gaps": gaps}
        (folder / "sample.yaml").write_text(
            "# The calibration sample (T2.5), from python -m tagger sample.\n"
            + yaml.safe_dump(summary, sort_keys=False), encoding="utf-8")
        out(f"{len(chosen)} records: {folder / 'records.jsonl'} (tag these)")
        if human:
            out(f"{len(human)} for the Human: {folder / 'human-records.jsonl'} "
                "(python -m tagger template --records it)")
        for gap in gaps:
            out(f"note: the Human's records of {gap}")
        return 0
    except (SampleError, AgreementError, RubricError, RecordError, OSError,
            ValueError) as error:
        out(f"refused: {error}")
        return 2
