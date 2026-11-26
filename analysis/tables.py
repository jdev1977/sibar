"""Fingerprint tables, convergence, sensitivity, the directed table, model
comparisons and representative outputs (docs/metrics.md).

Results are plain dicts of exact fractions; ``analysis.report`` writes them
out. Everything is built in a fixed order, so the output is deterministic.
"""

from collections import defaultdict
from fractions import Fraction
from itertools import combinations

from analysis import stats
from analysis.spec import LEVELS, WORDINGS, Expect  # noqa: F401  (Expect re-exported)
from analysis.runs import NA, OUTCOMES, UND

LEVEL_PAIRS = (("L0", "L1"), ("L1", "L2"), ("L0", "L2"))
MEASURED_ROLES = ("primary", "provisional")   # per-variable convergence and shift
VALUE, UNDETERMINED, NOT_APPLICABLE = "value", "undetermined", "not applicable"


# --- small pieces, tested against the worked examples -----------------------------


def level_shift(pairs):
    """S(t, v; L -> L'): the mean over wordings of shift(cell at L, cell at
    L'), skipping a wording where it is undefined. ``pairs`` holds one
    (values at L, values at L') per wording."""
    return stats.mean_defined([stats.shift(a, b) for a, b in pairs])


def excess(s, wording_shift_from, wording_shift_to):
    """E = S - (S_w at L + S_w at L') / 2; None unless all three exist."""
    if s is None or wording_shift_from is None or wording_shift_to is None:
        return None
    return s - (wording_shift_from + wording_shift_to) / 2


def complies(var, expect, value):
    """True or False for a run's value; None when it gives no verdict (no
    value, or a value listed under ``no_verdict``)."""
    if value is None:
        return None
    if var.single:
        if value in var.no_verdict or value in expect.no_verdict:
            return None
        if expect.in_ is None:
            return None
        return value in expect.in_
    ok = True
    if expect.absent is not None:
        ok = ok and not value.intersection(expect.absent)
    if expect.present is not None:
        ok = ok and set(expect.present) <= value
    if expect.absent is None and expect.present is None:
        return None
    return ok


def _yes_no(flag):
    return None if flag is None else ("yes" if flag else "no")


def _pooled_yes(groups):
    """Pool yes/no values; share of yes with its run interval."""
    p = stats.pool(groups)
    if not p.tasks:
        return None
    share = p.shares.get("yes", Fraction(0))
    return {"share": share, "run_interval": stats.wilson(share, p.n_eff),
            "n": p.n, "tasks": list(p.tasks), "n_eff": p.n_eff}


def compliance(var, expects, groups):
    """Compliance over the tasks in ``expects`` (task -> Expect), from
    ``groups`` ({(task, wording): [values]} at the level). Runs without a
    verdict are left out and counted."""
    verdicts, no_verdict = {}, 0
    for (task, wording), values in groups.items():
        if task not in expects:
            continue
        cell = []
        for value in values:
            flag = complies(var, expects[task], value)
            if flag is None and value is not None:
                no_verdict += 1
            cell.append(_yes_no(flag))
        verdicts[(task, wording)] = cell
    result = _pooled_yes(verdicts)
    if result is None:
        return None
    result["no_verdict"] = no_verdict
    return result


def l0_default(var, expect, l0_task_pool):
    """The task's L0 default d when persistence can be read: a single nominal
    top with a clear lead at the task's n_eff, not expected and not a value
    without verdict. None otherwise."""
    if not var.single or expect.in_ is None or not l0_task_pool.shares:
        return None
    evidence = stats.evidence_single(l0_task_pool, var.order_key, labelled=False)
    if len(evidence.nominal_top) != 1 or not evidence.clear_lead:
        return None
    d = evidence.nominal_top[0]
    if d in expect.in_ or d in var.no_verdict or d in expect.no_verdict:
        return None
    return d


def reading(interval):
    """persists / gave way / undecided, against one run in ten."""
    if interval is None:
        return "undecided"
    if interval[0] > 0.10:
        return "persists"
    if interval[1] < 0.10:
        return "gave way"
    return "undecided"


def persistence(var, expects, l0_pools, groups):
    """Share of runs at the level that still show the task's L0 default,
    over the tasks where it can be read. None when it can be read nowhere."""
    defaults = {}
    for task, expect in expects.items():
        if task in l0_pools:
            d = l0_default(var, expect, l0_pools[task])
            if d is not None:
                defaults[task] = d
    if not defaults:
        return None
    cells, no_verdict = {}, 0
    for (task, wording), values in groups.items():
        if task not in defaults:
            continue
        cell = []
        for value in values:
            if value is not None and (value in var.no_verdict
                                      or value in expects[task].no_verdict):
                no_verdict += 1
                cell.append(None)
            else:
                cell.append(None if value is None else
                            ("yes" if value == defaults[task] else "no"))
        cells[(task, wording)] = cell
    result = _pooled_yes(cells)
    if result is None:
        return None
    result["defaults"] = dict(sorted(defaults.items()))
    result["no_verdict"] = no_verdict
    result["reading"] = reading(result["run_interval"])
    return result


def typicality(runs, variables, dimension_of):
    """Typicality of each usable run against the other runs of the list
    (one model, task and level), most typical first. ``variables`` are the
    ones that may count (primary, open)."""
    usable = [run for run in runs if run.usable]
    ranking = []
    for run in usable:
        others = [s for s in usable if s is not run]
        per_var = {}
        for var in variables:
            mine = run.value(var)
            if mine is None:
                continue
            theirs = [s.value(var) for s in others if s.value(var) is not None]
            if theirs:
                per_var[var] = stats.mean([stats.agreement(mine, t) for t in theirs])
        per_dim = defaultdict(list)
        for var, value in per_var.items():
            per_dim[dimension_of[var]].append(value)
        dims = {d: stats.mean(v) for d, v in sorted(per_dim.items())}
        if dims:
            ranking.append({"run": run, "variables": per_var, "dimensions": dims,
                            "typicality": stats.mean(dims.values())})
    ranking.sort(key=lambda e: (-e["typicality"], e["run"].wording,
                                e["run"].run_index, e["run"].record_id))
    return ranking


def _brief(entry, variables):
    run = entry["run"]
    return {"record_id": run.record_id, "wording": run.wording,
            "run_index": run.run_index, "typicality": entry["typicality"],
            "dimensions": entry["dimensions"],
            "values": {v: run.value(v) for v in variables if run.value(v) is not None}}


def representative(runs, variables, dimension_of):
    """The representative output, the three most typical runs and the least
    typical; None with fewer than 3 usable runs."""
    if sum(run.usable for run in runs) < 3:
        return None
    ranking = typicality(runs, variables, dimension_of)
    if not ranking:
        return None
    return {"representative": ranking[0]["run"].record_id,
            "most_typical": [_brief(e, variables) for e in ranking[:3]],
            "least_typical": _brief(ranking[-1], variables)}


# --- the grid ---------------------------------------------------------------------


class Grid:
    """The selected runs, indexed by model, level, task and wording."""

    def __init__(self, runs, spec):
        self.spec = spec
        self.runs = list(runs)
        self.cells = defaultdict(list)
        for run in self.runs:
            self.cells[(run.model, run.level, run.task, run.wording)].append(run)
        self.models = sorted({run.model for run in self.runs})
        self.tasks = [t for t in spec.tasks if any(r.task == t for r in self.runs)]
        self.levels = [lv for lv in LEVELS if any(r.level == lv for r in self.runs)]
        self._shift_cache = {}

    def cell(self, model, level, task, wording, usable=True):
        runs = self.cells.get((model, level, task, wording), [])
        return [r for r in runs if r.usable] if usable else list(runs)

    def values(self, model, level, task, wording, var):
        return [r.value(var) for r in self.cell(model, level, task, wording)]

    def groups(self, model, level, var, tasks):
        out = {}
        for task in tasks:
            for wording in WORDINGS:
                cell = self.cell(model, level, task, wording)
                if cell:
                    out[(task, wording)] = [r.value(var) for r in cell]
        return out

    def open_tasks(self, level, var):
        return [t for t in self.tasks if self.spec.is_open(t, level, var)]

    def wording_shift(self, model, level, task, var):
        key = (model, level, task, var)
        if key not in self._shift_cache:
            self._shift_cache[key] = stats.shift(
                self.values(model, level, task, "A", var),
                self.values(model, level, task, "B", var))
        return self._shift_cache[key]


def _interval(iv):
    return None if iv is None else [iv.low, iv.high]


def _block(block):
    return {"mean": block["mean"], "interval": _interval(block["interval"]),
            "T": len(block["tasks"]), "tasks": block["tasks"]}


def summary_dict(summary, flag=None):
    """A ``stats.Summary`` as nested dicts; ``flag(block)`` adds a flag to a
    dimension (its name and condition)."""
    out = {"variables": {v: _block(b) for v, b in summary.variables.items()},
           "dimensions": {}, "overall": _block(summary.overall) if summary.overall else None}
    for dim, block in summary.dimensions.items():
        entry = _block(block)
        if flag is not None:
            entry["flag"] = flag(block)
        out["dimensions"][dim] = entry
    return out


def _lower_above_zero(block):
    return block["interval"] is not None and block["interval"].low > 0


# --- fingerprint ------------------------------------------------------------------


def _state(run, var):
    value = run.values.get(var)
    if value is UND or value is None:
        return UNDETERMINED
    if value is NA:
        return NOT_APPLICABLE
    return VALUE


def variable_row(grid, model, level, var):
    """The fingerprint row of one variable at one level."""
    spec = grid.spec
    decl = spec.variables[var]
    tasks = grid.open_tasks(level, var)
    row = {"variable": var, "type": decl.type, "role": decl.role,
           "dimension": decl.dimension, "task_driven": decl.task_driven,
           "open_tasks": tasks, "flags": []}
    if not tasks:
        row.update(label="closed in every task", N=0, T=0, n_eff=None, items=[])
        return row
    groups = grid.groups(model, level, var, tasks)
    states = {}
    for task in tasks:
        for wording in WORDINGS:
            cell = grid.cell(model, level, task, wording)
            if cell:
                states[(task, wording)] = [_state(r, var) for r in cell]
    state_pool = stats.pool(states)
    counts = defaultdict(int)
    for cell in states.values():
        for s in cell:
            counts[s] += 1
    row["undetermined"] = {"count": counts[UNDETERMINED],
                           "share": state_pool.shares.get(UNDETERMINED, Fraction(0))}
    row["not_applicable"] = {"count": counts[NOT_APPLICABLE],
                             "share": state_pool.shares.get(NOT_APPLICABLE, Fraction(0))}
    if row["undetermined"]["share"] > stats.FLAG_SHARE:
        row["flags"].append("partly read")
    p = stats.pool(groups, is_set=not decl.single)
    row.update(N=p.n, T=p.t, n_eff=p.n_eff)
    items = []
    for item, share in stats.ordered(p.shares, decl.order_key):
        run_iv = stats.wilson(share, p.n_eff)
        task_iv = stats.share_task_interval([p.task_shares[t][item] for t in p.tasks], run_iv)
        items.append({"choice": item, "share": share, "run_interval": run_iv,
                      "task_interval": _interval(task_iv)})
    row["items"] = items
    row["per_task"] = {
        task: {"n_eff": p.task_n_eff[task],
               "n": sum(n for (t, _), n in p.cells.items() if t == task),
               "shares": {k: v for k, v in stats.ordered(p.task_shares[task], decl.order_key)
                          if v}}
        for task in p.tasks}
    if decl.single:
        e = stats.evidence_single(p, decl.order_key)
        row.update(label=e.label, nominal_top=list(e.nominal_top), reported=e.reported,
                   evidence={"x1": e.x1, "x2": e.x2, "clear_lead": e.clear_lead,
                             "established_majority": e.majority, "strong": e.strong})
        if len(e.nominal_top) == 1 and p.tasks:
            top = e.nominal_top[0]
            support, spread = stats.task_support(p, top), stats.task_spread(p, top)
            row["task_support"] = [support, p.t]
            row["task_spread"] = spread
            if spread >= stats.TASK_DEPENDENT:
                row["flags"].append("task-dependent")
            row["holds_across_tasks"] = bool(
                e.reported is not None and support == p.t and p.t >= stats.HOLDS_MIN_TASKS)
    else:
        rows, defaults = stats.default_items(p, decl.order_key)
        for entry, (_, _, major, strong) in zip(items, rows):
            entry["established_majority"] = major
            entry["strong"] = strong
        row["label"] = "insufficient data" if stats.insufficient(p) else "default set"
        row["default_set"] = list(defaults)
    if decl.task_driven:
        row["flags"].append("task-driven")
    return row


def outcome_table(grid, model, level):
    groups = {}
    for task in grid.tasks:
        for wording in WORDINGS:
            cell = grid.cell(model, level, task, wording, usable=False)
            if cell:
                groups[(task, wording)] = [r.outcome for r in cell]
    p = stats.pool(groups)
    shares = {o: p.shares.get(o, Fraction(0)) for o in OUTCOMES}
    counts = {o: sum(c.count(o) for c in groups.values()) for o in OUTCOMES}
    not_artifact = 1 - shares["artifact"] if p.tasks else Fraction(0)
    return {"shares": shares, "counts": counts, "N": p.n, "T": p.t, "n_eff": p.n_eff,
            "not_artifact": not_artifact,
            "incomplete_outcomes": bool(not_artifact > stats.FLAG_SHARE)}


def health_rates(grid, model, level):
    """Health rates over usable runs, pooled like any share."""
    names = []
    for run in grid.runs:
        if run.model == model and run.level == level and run.usable:
            names = list(run.health)
            break
    out = {}
    for name in names:
        groups = {}
        for task in grid.tasks:
            for wording in WORDINGS:
                cell = grid.cell(model, level, task, wording)
                if cell:
                    groups[(task, wording)] = [
                        None if r.health.get(name) is None else
                        ("yes" if r.health[name] else "no") for r in cell]
        p = stats.pool(groups)
        out[name] = {"share": p.shares.get("yes", Fraction(0)) if p.tasks else None,
                     "N": p.n, "n_eff": p.n_eff}
    return out


def _partly_read_dimensions(spec, health):
    """Dimensions flagged by a diagnostic count feature of 1 or more in more
    than 10% of runs."""
    flagged = {}
    for name, rate in health.items():
        if not name.startswith("present:") or rate["share"] is None:
            continue
        var = spec.variables[name.split(":", 1)[1]]
        if var.type == "number" and rate["share"] > stats.FLAG_SHARE:
            flagged.setdefault(var.dimension, []).append(var.name)
    return flagged


def _dates(runs):
    days = sorted(r.timestamp[:10] for r in runs)
    return [days[0], days[-1]] if days else None


def fingerprint(grid, model, level):
    spec = grid.spec
    runs = [r for r in grid.runs if r.model == model and r.level == level]
    snapshots = sorted({r.model_id_returned for r in runs if r.model_id_returned})
    health = health_rates(grid, model, level)
    rows = [variable_row(grid, model, level, v.name) for v in spec.table_variables()]
    flags = []
    outcomes = outcome_table(grid, model, level)
    if outcomes["incomplete_outcomes"]:
        flags.append("incomplete outcomes")
    if len(snapshots) > 1:
        flags.append("mixed snapshots")
    reps = {}
    dimension_of = {n: v.dimension for n, v in spec.variables.items()}
    for task in grid.tasks:
        variables = [n for n, v in spec.variables.items()
                     if v.role == "primary" and spec.is_open(task, level, n)]
        runs_t = grid.cell(model, level, task, "A", usable=False) + \
            grid.cell(model, level, task, "B", usable=False)
        reps[task] = representative(runs_t, variables, dimension_of)
    return {"model": model, "level": level, "dates": _dates(runs),
            "model_id_returned": snapshots, "settings": sorted({r.settings for r in runs}),
            "flags": flags, "outcomes": outcomes, "health": health,
            "partly_read_dimensions": _partly_read_dimensions(spec, health),
            "variables": rows, "representative_outputs": reps}


# --- convergence and sensitivity --------------------------------------------------


def _measured(spec):
    return [n for n, v in spec.variables.items() if v.role in MEASURED_ROLES]


def _summarise(spec, per_task_var, flag=None):
    dimension_of = {n: v.dimension for n, v in spec.variables.items()}
    primary = {n for n, v in spec.variables.items() if v.role == "primary"}
    return summary_dict(stats.summarise(per_task_var, dimension_of, primary), flag)


def convergence(grid, model, level):
    spec = grid.spec
    per = {}
    for var in _measured(spec):
        for task in grid.open_tasks(level, var):
            per[(task, var)] = stats.mean_defined(
                [stats.within(grid.values(model, level, task, w, var)) for w in WORDINGS])
    return _summarise(spec, per)


def wording_sensitivity(grid, model, level):
    spec = grid.spec
    per = {(task, var): grid.wording_shift(model, level, task, var)
           for var in _measured(spec) for task in grid.open_tasks(level, var)}
    out = _summarise(spec, per, lambda b: "read the wording pair again"
                     if _lower_above_zero(b) else None)
    return out


def level_sensitivity(grid, model, low, high):
    """S, the yardstick and E between two levels, for variables open at both."""
    spec = grid.spec
    s_per, y_per, e_per = {}, {}, {}
    for var in _measured(spec):
        for task in grid.tasks:
            if not (spec.is_open(task, low, var) and spec.is_open(task, high, var)):
                continue
            s = level_shift([(grid.values(model, low, task, w, var),
                              grid.values(model, high, task, w, var)) for w in WORDINGS])
            sw_low = grid.wording_shift(model, low, task, var)
            sw_high = grid.wording_shift(model, high, task, var)
            s_per[(task, var)] = s
            y_per[(task, var)] = (None if sw_low is None or sw_high is None
                                  else (sw_low + sw_high) / 2)
            e_per[(task, var)] = excess(s, sw_low, sw_high)
    associations = {task: spec.associations(task, high) for task in grid.tasks
                    if spec.associations(task, high)}
    return {"from": low, "to": high,
            "shift": _summarise(spec, s_per),
            "yardstick": _summarise(spec, y_per),
            "excess": _summarise(spec, e_per, lambda b: "direction moved it"
                                 if _lower_above_zero(b) else None),
            "associations": associations}


# --- directed table ---------------------------------------------------------------


def directed(grid, model, level):
    """Closed variables, task by task, with shift from L0, compliance and
    persistence; pooled compliance and persistence per variable."""
    spec = grid.spec
    entries = []
    per_var_tasks = defaultdict(list)
    for task in grid.tasks:
        expects = spec.expectations(task, level)
        for var, closer in spec.closed_cached(task, level).items():
            decl = spec.variables[var]
            if decl.role == "diagnostic":
                continue
            per_var_tasks[var].append(task)
            groups = grid.groups(model, level, var, [task])
            p = stats.task_pool(groups, task, is_set=not decl.single)
            entry = {"task": task, "variable": var, "role": decl.role,
                     "closed_by": "listed" if closer is None else "dependent",
                     "closer": closer, "N": p.n, "n_eff": p.n_eff,
                     "shares": dict(stats.ordered(p.shares, decl.order_key))}
            if var in expects:
                entry["expect"] = _expect_dict(expects[var])
                entry["compliance"] = compliance(decl, {task: expects[var]}, groups)
            if decl.role in MEASURED_ROLES:
                entry["convergence"] = stats.mean_defined(
                    [stats.within(grid.values(model, level, task, w, var)) for w in WORDINGS])
                entry["wording_shift"] = grid.wording_shift(model, level, task, var)
                if level != "L0":
                    s = level_shift([(grid.values(model, "L0", task, w, var),
                                      grid.values(model, level, task, w, var))
                                     for w in WORDINGS])
                    entry["shift_from_L0"] = s
                    entry["excess_from_L0"] = excess(
                        s, grid.wording_shift(model, "L0", task, var),
                        grid.wording_shift(model, level, task, var))
            entries.append(entry)
    pooled = {}
    for var, tasks in per_var_tasks.items():
        decl = spec.variables[var]
        expects = {t: spec.expectations(t, level)[var] for t in tasks
                   if var in spec.expectations(t, level)}
        if not expects:
            continue
        groups = grid.groups(model, level, var, list(expects))
        l0_pools = {t: stats.task_pool(grid.groups(model, "L0", var, [t]), t,
                                       is_set=not decl.single) for t in expects}
        pooled[var] = {"compliance": compliance(decl, expects, groups),
                       "persistence": persistence(decl, expects, l0_pools, groups)
                       if decl.single else None}
    return {"entries": entries, "pooled": pooled}


def _expect_dict(expect):
    out = {}
    for key, value in (("in", expect.in_), ("absent", expect.absent),
                       ("present", expect.present)):
        if value is not None:
            out[key] = list(value)
    if expect.no_verdict:
        out["no_verdict"] = sorted(expect.no_verdict)
    return out


# --- across models ----------------------------------------------------------------


def model_comparison(grid, level, fingerprints):
    """Cross-model agreement X and model shift D per pair and for all models;
    shared defaults. ``fingerprints`` maps model -> fingerprint at ``level``."""
    spec = grid.spec
    models = [m for m in grid.models if any(r.model == m and r.level == level
                                            for r in grid.runs)]
    if len(models) < 2:
        return None
    pairs = list(combinations(models, 2))
    cell_x, cell_d = defaultdict(list), defaultdict(list)
    out_pairs = []
    for m1, m2 in pairs:
        x_per, d_per = {}, {}
        for var in _measured(spec):
            for task in grid.open_tasks(level, var):
                xs, ds = [], []
                for w in WORDINGS:
                    a = grid.values(m1, level, task, w, var)
                    b = grid.values(m2, level, task, w, var)
                    x, d = stats.cross(a, b), stats.shift(a, b)
                    xs.append(x)
                    ds.append(d)
                    if x is not None:
                        cell_x[(task, w, var)].append(x)
                    if d is not None:
                        cell_d[(task, w, var)].append(d)
                x_per[(task, var)] = stats.mean_defined(xs)
                d_per[(task, var)] = stats.mean_defined(ds)
        out_pairs.append({"models": [m1, m2],
                          "agreement": _summarise(spec, x_per),
                          "model_shift": _summarise(spec, d_per, lambda b: "the models differ"
                                                    if _lower_above_zero(b) else None)})

    def over_pairs(cells):
        per = {}
        for var in _measured(spec):
            for task in grid.open_tasks(level, var):
                per[(task, var)] = stats.mean_defined(
                    [stats.mean_defined(cells.get((task, w, var), [])) for w in WORDINGS])
        return per

    shared = {}
    for row_set in zip(*[fingerprints[m]["variables"] for m in models]):
        var = row_set[0]["variable"]
        if spec.variables[var].role != "primary":
            continue
        if spec.variables[var].single:
            reported = {row.get("reported") for row in row_set}
            if len(reported) == 1 and None not in reported:
                shared[var] = sorted(reported)
        else:
            common = set(row_set[0].get("default_set") or [])
            for row in row_set[1:]:
                common &= set(row.get("default_set") or [])
            if common:
                shared[var] = sorted(common)
    return {"level": level, "models": models, "pairs": out_pairs,
            "all_models": {"agreement": _summarise(spec, over_pairs(cell_x)),
                           "model_shift": _summarise(spec, over_pairs(cell_d),
                                                     lambda b: "the models differ"
                                                     if _lower_above_zero(b) else None)},
            "shared_defaults": shared}


# --- everything -------------------------------------------------------------------


def compute(selection, spec):
    """Every table for the runs of a selection."""
    grid = Grid(selection.runs, spec)
    models = {}
    fingerprints_by_level = defaultdict(dict)
    for model in grid.models:
        levels = [lv for lv in grid.levels if any(r.model == model and r.level == lv
                                                  for r in grid.runs)]
        per_level = {}
        for level in levels:
            fp = fingerprint(grid, model, level)
            fingerprints_by_level[level][model] = fp
            per_level[level] = {"fingerprint": fp,
                                "convergence": convergence(grid, model, level),
                                "wording_sensitivity": wording_sensitivity(grid, model, level),
                                "directed": directed(grid, model, level)}
        sensitivity = [level_sensitivity(grid, model, low, high)
                       for low, high in LEVEL_PAIRS if low in levels and high in levels]
        models[model] = {"levels": per_level, "sensitivity": sensitivity}
    comparisons = [c for c in (model_comparison(grid, level, fingerprints_by_level[level])
                               for level in grid.levels) if c is not None]
    return {"metrics_version": spec.metrics_version,
            "project_type": spec.project_type,
            "extractor_versions": dict(spec.extractor_versions),
            "batch_group": list(selection.batches),
            "record_files": list(selection.files),
            "notes": list(selection.notes),
            "tasks": grid.tasks, "models": models, "model_comparisons": comparisons}
