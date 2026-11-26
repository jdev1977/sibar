"""The stability check (docs/metrics.md, "The stability rule"; task T1.8).

Doubling the runs per cell must not change the reported top choices of the
L0 fingerprint. ``check`` compares the tables of run indexes 1..small and
1..big for one model, or, when runs are missing, says which cells to run.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from analysis import stats
from analysis.runs import Refused
from analysis.spec import WORDINGS
from analysis.tables import Grid, _summarise

PAIRS = {(5, 10): "first", (10, 20): "repeat"}
SCORE_LIMIT = Fraction(9, 10)
GROWTH_LIMIT = Fraction(1, 10)
REVERSALS_ALLOWED = 1
CELL_SHARE = Fraction(4, 5)      # 4 of 5, 8 of 10, 16 of 20 usable runs

CONSEQUENCES = {
    "first": {
        "stable": "5 runs per cell stand for this model.",
        "unstable: defaults still appearing":
            "10 runs per cell for this model. With the Human's approval of the "
            "spend, the check is repeated once, 10 against 20.",
        "unstable: contested choices":
            "5 runs per cell stand for this model. The variables that changed are "
            "marked contested in the pilot report and are not called defaults.",
        "drift suspected":
            "No recommendation on the run count from this model. Compare run "
            "indexes 1 to 5 with 6 to 10 (shift per dimension, dates, "
            "model_id_returned); if the provider changed the model, run its L0 "
            "again as a new batch.",
        "no defaults": "Recorded as such; the fingerprint has no top choices to be stable.",
        "not run": "Complete the named cells first.",
    },
    "repeat": {
        "stable": "10 runs per cell stand: twenty runs report what ten did.",
        "unstable: contested choices":
            "10 runs per cell stand. The variables that changed are marked "
            "contested and are not called defaults.",
        "unstable: defaults still appearing":
            "10 runs per cell stand all the same, and there is no further repeat. "
            "The variables that gained an established default between 10 and 20 "
            "runs are listed as open at 10 runs, with the growth, for the Human "
            "to decide.",
        "drift suspected":
            "As in the first check, with run indexes 1 to 10 compared with 11 to 20.",
        "no defaults": "Recorded as such; the fingerprint has no top choices to be stable.",
        "not run": "Complete the named cells first.",
    },
}


@dataclass(frozen=True)
class VariableReport:
    """What one table claims about one variable."""

    name: str
    single: bool
    label: str
    reported: Optional[str] = None
    nominal_top: tuple = ()
    majority: bool = False          # the reported choice has an established majority
    default_set: tuple = ()
    shares: dict = field(default_factory=dict)


def variable_report(var, p):
    if var.single:
        e = stats.evidence_single(p, var.order_key)
        return VariableReport(var.name, True, e.label, e.reported, e.nominal_top,
                              bool(e.reported is not None and e.majority),
                              shares=dict(p.shares))
    _, defaults = stats.default_items(p, var.order_key)
    label = "insufficient data" if stats.insufficient(p) else "default set"
    return VariableReport(var.name, False, label, default_set=defaults,
                          shares=dict(p.shares))


@dataclass
class Comparison:
    counted: list
    credits: dict
    score: Optional[Fraction]
    reversals: int
    kinds: dict
    changes: list
    e_small: int
    e_big: int
    growth: object
    gained: list


def growth(e_small, e_big):
    """E10 / E5 - 1; 0 when both are 0; infinite when only E5 is 0."""
    if e_small == 0:
        return Fraction(0) if e_big == 0 else float("inf")
    return Fraction(e_big, e_small) - 1


def _established(report):
    if report is None:
        return 0
    return int(report.majority) if report.single else len(report.default_set)


def compare(small, big):
    """Compare two tables ({variable: VariableReport}) of primary variables."""
    names = list(small) + [n for n in big if n not in small]
    counted, credits, changes, gained = [], {}, [], []
    kinds = {"kept": 0, "new": 0, "lost": 0, "reversed": 0, "changed": 0}
    reversals = 0
    for name in names:
        a, b = small.get(name), big.get(name)
        single = (a or b).single
        if single:
            ra = a.reported if a else None
            rb = b.reported if b else None
            if rb is not None and b.majority and not (a and ra == rb and a.majority):
                gained.append({"variable": name, "choice": rb})
            if ra is None and rb is None:
                continue
            counted.append(name)
            credits[name] = 1 if ra == rb else 0
            if ra == rb:
                kind = "kept"
            elif ra is None:
                kind = "new"
            elif ra not in (b.nominal_top if b else ()):
                kind = "reversed"
                reversals += 1
            else:
                kind = "lost"
            kinds[kind] += 1
            if kind != "kept":
                changes.append({
                    "variable": name, "kind": kind,
                    "small": {"reported": ra, "established_majority": bool(a and a.majority)},
                    "big": {"reported": rb, "nominal_top": list(b.nominal_top) if b else [],
                            "established_majority": bool(b and b.majority)}})
            continue
        da = set(a.default_set) if a else set()
        db = set(b.default_set) if b else set()
        gained += [{"variable": name, "item": item} for item in sorted(db - da)]
        if not da and not db:
            continue
        counted.append(name)
        credits[name] = Fraction(len(da & db), len(da | db))
        reversed_items = [item for item in sorted(da)
                          if (b.shares.get(item, Fraction(0)) if b else Fraction(0))
                          < Fraction(1, 2)]
        reversals += len(reversed_items)
        if da == db:
            kind = "kept"
        elif not da:
            kind = "new"
        elif reversed_items:
            kind = "reversed"
        elif not db:
            kind = "lost"
        else:
            kind = "changed"
        kinds[kind] += 1
        if kind != "kept":
            changes.append({"variable": name, "kind": kind,
                            "small": {"default_set": sorted(da)},
                            "big": {"default_set": sorted(db)},
                            "gained": sorted(db - da), "dropped": sorted(da - db),
                            "reversed_items": reversed_items})
    score = (sum(credits.values(), Fraction(0)) / len(counted)) if counted else None
    e_small = sum(_established(small.get(n)) for n in names)
    e_big = sum(_established(big.get(n)) for n in names)
    return Comparison(counted, credits, score, reversals, kinds, changes,
                      e_small, e_big, growth(e_small, e_big), gained)


def verdict(result):
    if not result.counted:
        return "no defaults"
    if result.reversals > REVERSALS_ALLOWED:
        return "drift suspected"
    if result.score >= SCORE_LIMIT:
        return "stable"
    if result.growth >= GROWTH_LIMIT:
        return "unstable: defaults still appearing"
    return "unstable: contested choices"


def consequence(verdict_text, repeat):
    return CONSEQUENCES["repeat" if repeat else "first"][verdict_text]


# --- the check on records ---------------------------------------------------------


def _reports(runs, spec, model):
    grid = Grid(runs, spec)
    out = {}
    for name, var in spec.variables.items():
        if var.role != "primary":
            continue
        tasks = grid.open_tasks("L0", name)
        out[name] = variable_report(
            var, stats.pool(grid.groups(model, "L0", name, tasks), is_set=not var.single))
    return out


def _halves(runs, spec, model, small, big):
    """Run indexes 1..small against small+1..big: the shift per dimension
    (near 0 without drift), dates and model_id_returned of each group."""
    first = [r for r in runs if r.run_index <= small]
    second = [r for r in runs if small < r.run_index <= big]
    g1, g2 = Grid(first, spec), Grid(second, spec)
    per = {}
    for name, var in spec.variables.items():
        if var.role != "primary":
            continue
        for task in spec.tasks:
            per[(task, name)] = stats.mean_defined([
                stats.shift(g1.values(model, "L0", task, w, name),
                            g2.values(model, "L0", task, w, name)) for w in WORDINGS])

    def about(group):
        days = sorted(r.timestamp[:10] for r in group)
        return {"runs": len(group), "dates": [days[0], days[-1]] if days else None,
                "model_id_returned": sorted({r.model_id_returned for r in group
                                             if r.model_id_returned})}
    shift = _summarise(spec, per)
    return {"groups": [f"1-{small}", f"{small + 1}-{big}"],
            "first": about(first), "second": about(second),
            "shift_by_dimension": shift["dimensions"], "shift_overall": shift["overall"]}


def runner_command(spec, batch, model, big):
    return (f"python -m runner.run --prompts prompts/{spec.project_type} "
            f"--batch-id {batch} --models {model} --levels L0 --runs {big} --dry-run")


def check(selection, spec, model, small=5, big=10):
    """The stability check for one model; see the module docstring."""
    if (small, big) not in PAIRS:
        raise Refused(f"the check compares 5 with 10 runs, or 10 with 20 (the repeat), "
                      f"not {small} with {big}")
    if len(selection.batches) != 1:
        raise Refused("the stability check reads one batch: name exactly one --batch")
    batch = selection.batches[0]
    repeat = PAIRS[(small, big)] == "repeat"
    runs = [r for r in selection.runs if r.model == model and r.level == "L0"
            and r.run_index <= big]
    if not any(r.model == model for r in selection.runs):
        raise Refused(f"no runs of model {model} in batch {batch}")
    cells, to_run, short = [], [], []
    need_small, need_big = CELL_SHARE * small, CELL_SHARE * big
    for task in spec.tasks:
        for wording in WORDINGS:
            mine = {r.run_index: r for r in runs if r.task == task and r.wording == wording}
            missing = [i for i in range(1, big + 1) if i not in mine]
            usable_small = sum(r.usable for i, r in mine.items() if i <= small)
            usable_big = sum(r.usable for r in mine.values())
            cell = {"task": task, "level": "L0", "wording": wording,
                    "usable_first": usable_small, "usable_all": usable_big,
                    "missing_run_indexes": missing}
            cells.append(cell)
            if missing:
                to_run.append({"task": task, "level": "L0", "wording": wording,
                               "run_indexes": missing})
            elif usable_small < need_small or usable_big < need_big:
                short.append(cell)
    result = {"model": model, "batch": batch, "runs_compared": [small, big],
              "check": "repeat (10 against 20)" if repeat else "first (5 against 10)",
              "metrics_version": spec.metrics_version,
              "extractor_versions": dict(spec.extractor_versions),
              "record_files": list(selection.files), "notes": list(selection.notes),
              "cells": cells,
              "selection": {"cells": to_run,
                            "runner_command": runner_command(spec, batch, model, big)
                            if to_run else None},
              "cells_short": [f"{c['task']} L0 {c['wording']}" for c in short]}
    if to_run or short:
        result["verdict"] = "not run"
        result["consequence"] = consequence("not run", repeat)
        return result
    small_runs = [r for r in runs if r.run_index <= small]
    comparison = compare(_reports(small_runs, spec, model), _reports(runs, spec, model))
    text = verdict(comparison)
    result.update({
        "verdict": text, "consequence": consequence(text, repeat),
        "score": comparison.score, "counted": comparison.counted,
        "credits": comparison.credits, "kinds": comparison.kinds,
        "reversals": comparison.reversals,
        "established_defaults": [comparison.e_small, comparison.e_big],
        "growth": comparison.growth, "changes": comparison.changes,
        "gained_established_defaults": comparison.gained,
        "open_at_10_runs": comparison.gained
        if repeat and text == "unstable: defaults still appearing" else [],
        "halves": _halves(runs, spec, model, small, big)})
    return result
