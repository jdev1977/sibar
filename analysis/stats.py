"""The arithmetic of docs/metrics.md, on plain values.

A run's value for a variable is a choice (text), a ``frozenset`` of items
(set, ordered-list and count-map variables), or ``None`` when the run has no
value (undetermined or not applicable). Shares, agreements and shifts are
exact ``Fraction``s; the conditions that involve z are decided on floats.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations
from typing import Optional

Z = 1.96
Z2 = Z * Z
# 0.975 point of Student's t by degrees of freedom (docs/metrics.md, Uncertainty)
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201}
MIN_TASKS = 3                 # below: insufficient data
MIN_N_EFF = 16
STRONG = 0.8
FLAG_SHARE = Fraction(1, 10)  # incomplete outcomes, partly read
TASK_DEPENDENT = Fraction(7, 10)
HOLDS_MIN_TASKS = 5


# --- intervals -------------------------------------------------------------------


def wilson(p, n):
    """95% Wilson score interval for share ``p`` at ``n`` effective runs."""
    if n is None or n <= 0:
        return None
    p, n = float(p), float(n)
    denominator = 1 + Z2 / n
    centre = (p + Z2 / (2 * n)) / denominator
    half = Z * math.sqrt(p * (1 - p) / n + Z2 / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def _t_density(x, df):
    log_c = (math.lgamma((df + 1) / 2) - math.lgamma(df / 2)
             - 0.5 * math.log(df * math.pi))
    return math.exp(log_c - (df + 1) / 2 * math.log1p(x * x / df))


def _t_cdf_upper_half(x, df, steps=2000):
    """P(0 < T < x) by Simpson's rule."""
    h = x / steps
    total = _t_density(0, df) + _t_density(x, df)
    for i in range(1, steps):
        total += (4 if i % 2 else 2) * _t_density(i * h, df)
    return total * h / 3


def t975(df):
    """The 0.975 point of Student's t: the document's table for 1 to 11
    degrees of freedom, computed beyond it."""
    if df < 1:
        raise ValueError("Student's t needs at least 1 degree of freedom")
    if df in T975:
        return T975[df]
    low, high = 1.9, 2.3
    for _ in range(60):
        middle = (low + high) / 2
        if _t_cdf_upper_half(middle, df) < 0.475:
            low = middle
        else:
            high = middle
    return round((low + high) / 2, 3)


@dataclass(frozen=True)
class TaskInterval:
    mean: Fraction
    sd: float
    low: float
    high: float
    tasks: int


def mean(values):
    values = list(values)
    return sum(values, Fraction(0)) / len(values) if values else None


def task_interval(values):
    """Student t interval over per-task values (tasks as clusters); needs
    two tasks. Returns None with fewer."""
    values = list(values)
    if len(values) < 2:
        return None
    m = mean(values)
    variance = sum((Fraction(v) - m) ** 2 for v in values) / (len(values) - 1)
    sd = math.sqrt(variance)
    half = t975(len(values) - 1) * sd / math.sqrt(len(values))
    return TaskInterval(m, sd, float(m) - half, float(m) + half, len(values))


def share_task_interval(values, run_interval):
    """The task interval of a share: cut to 0..1, then widened to contain the
    run interval."""
    base = task_interval(values)
    if base is None:
        return None
    low, high = max(0.0, base.low), min(1.0, base.high)
    if run_interval is not None:
        low, high = min(low, run_interval[0]), max(high, run_interval[1])
    return TaskInterval(base.mean, base.sd, low, high, base.tasks)


# --- pooling -----------------------------------------------------------------------


@dataclass
class Pool:
    """Shares pooled with the design's weights: runs equal in a cell,
    wordings equal in a task, tasks equal."""

    shares: dict = field(default_factory=dict)       # item -> Fraction
    task_shares: dict = field(default_factory=dict)  # task -> {item: Fraction}
    task_n_eff: dict = field(default_factory=dict)   # task -> Fraction
    tasks: tuple = ()
    n: int = 0
    n_eff: Optional[Fraction] = None
    cells: dict = field(default_factory=dict)        # (task, wording) -> runs with a value

    @property
    def t(self):
        return len(self.tasks)


def pool(groups, is_set=False):
    """Pool ``{(task, wording): [value or None, ...]}``.

    For a set, a run counts toward every item it holds. A cell without a run
    that has a value is dropped, and a task without such a cell.
    """
    by_task = {}
    cells = {}
    for (task, wording) in sorted(groups):
        values = [v for v in groups[(task, wording)] if v is not None]
        if not values:
            continue
        counts = Counter()
        for value in values:
            counts.update(value if is_set else (value,))
        by_task.setdefault(task, []).append((counts, len(values)))
        cells[(task, wording)] = len(values)
    if not by_task:
        return Pool()
    items = set()
    for cell_list in by_task.values():
        for counts, _ in cell_list:
            items.update(counts)
    task_shares, task_n_eff = {}, {}
    sum_squares = Fraction(0)
    tasks = tuple(sorted(by_task))
    for task in tasks:
        cell_list = by_task[task]
        task_shares[task] = {
            item: sum((Fraction(c[item], n) for c, n in cell_list), Fraction(0))
            / len(cell_list) for item in items}
        within = sum((n * Fraction(1, len(cell_list) * n) ** 2 for _, n in cell_list),
                     Fraction(0))
        task_n_eff[task] = 1 / within
        sum_squares += sum((n * Fraction(1, len(tasks) * len(cell_list) * n) ** 2
                            for _, n in cell_list), Fraction(0))
    shares = {item: sum((task_shares[t][item] for t in tasks), Fraction(0)) / len(tasks)
              for item in items}
    return Pool(shares=shares, task_shares=task_shares, task_n_eff=task_n_eff,
                tasks=tasks, n=sum(cells.values()), n_eff=1 / sum_squares, cells=cells)


def task_pool(groups, task, is_set=False):
    """The per-task table: cells, then the task (weights within the task)."""
    return pool({key: values for key, values in groups.items() if key[0] == task},
                is_set)


# --- labels ------------------------------------------------------------------------


def clear_lead(x1, x2):
    return (x1 - x2) ** 2 > Z2 * (x1 + x2)


def majority(x, n):
    return x > n / 2 and (2 * x - n) ** 2 > Z2 * n


def strong(p, n):
    interval = wilson(p, n)
    return interval is not None and interval[0] > STRONG


def ordered(shares, key=str):
    """Items by share, largest first; ties by ``key`` (bins in bin order,
    else alphabetical)."""
    return sorted(shares.items(), key=lambda kv: (-kv[1], key(kv[0])))


def insufficient(p):
    return p.t < MIN_TASKS or p.n_eff is None or p.n_eff < MIN_N_EFF


@dataclass(frozen=True)
class Evidence:
    nominal_top: tuple
    p1: Fraction
    p2: Fraction
    x1: float
    x2: float
    clear_lead: bool
    majority: bool
    strong: bool
    label: str
    reported: Optional[str]


def evidence_single(p, key=str, labelled=True):
    """Top choice of a variable with one value per run. ``labelled`` False
    for a per-task table, which carries no `insufficient data` label."""
    if not p.shares:
        return Evidence((), Fraction(0), Fraction(0), 0.0, 0.0, False, False,
                        False, "insufficient data", None)
    items = ordered(p.shares, key)
    p1 = items[0][1]
    p2 = items[1][1] if len(items) > 1 else Fraction(0)
    tops = tuple(k for k, share in items if share == p1)
    n = float(p.n_eff)
    x1, x2 = float(p1) * n, float(p2) * n
    lead = len(tops) == 1 and clear_lead(x1, x2)
    major = len(tops) == 1 and majority(x1, n)
    is_strong = len(tops) == 1 and strong(p1, n)
    if labelled and insufficient(p):
        label = "insufficient data"
    elif not lead:
        label = "contested"
    elif is_strong:
        label = "strong default"
    elif major:
        label = "default"
    else:
        label = "leading"
    reported = tops[0] if label in ("strong default", "default", "leading") else None
    return Evidence(tops, p1, p2, x1, x2, lead, major, is_strong, label, reported)


def task_support(p, item):
    """In how many tasks ``item`` is the top choice of the task's own table
    (ties included)."""
    count = 0
    for task in p.tasks:
        shares = p.task_shares[task]
        if shares.get(item, 0) == max(shares.values()):
            count += 1
    return count


def task_spread(p, item):
    """Largest minus smallest per-task share of ``item``."""
    values = [p.task_shares[task].get(item, Fraction(0)) for task in p.tasks]
    return max(values) - min(values) if values else None


def default_items(p, key=str, labelled=True):
    """``[(item, share, established majority, strong)]`` by share, and the
    default set (empty when the row has insufficient data)."""
    rows = []
    n = float(p.n_eff) if p.n_eff else 0.0
    for item, share in ordered(p.shares, key):
        rows.append((item, share, majority(float(share) * n, n) if n else False,
                     strong(share, n) if n else False))
    if labelled and insufficient(p):
        return rows, ()
    return rows, tuple(sorted(item for item, _, major, _ in rows if major))


# --- agreement ---------------------------------------------------------------------


def agreement(a, b):
    """1 or 0 for two choices; Jaccard for two sets (1 if both are empty)."""
    if isinstance(a, frozenset):
        union = a | b
        return Fraction(1) if not union else Fraction(len(a & b), len(union))
    return Fraction(1 if a == b else 0)


def _valued(values):
    return [v for v in values if v is not None]


def within(values):
    """Mean agreement over pairs of different runs; None with fewer than two."""
    values = _valued(values)
    if len(values) < 2:
        return None
    if not isinstance(values[0], frozenset):
        counts = Counter(values)
        n = len(values)
        return Fraction(sum(c * (c - 1) for c in counts.values()), n * (n - 1))
    pairs = list(combinations(values, 2))
    return sum((agreement(a, b) for a, b in pairs), Fraction(0)) / len(pairs)


def cross(g, h):
    """Mean agreement over every run of ``g`` with every run of ``h``."""
    g, h = _valued(g), _valued(h)
    if not g or not h:
        return None
    if not isinstance(g[0], frozenset):
        cg, ch = Counter(g), Counter(h)
        return Fraction(sum(cg[k] * ch[k] for k in cg), len(g) * len(h))
    return sum((agreement(a, b) for a in g for b in h), Fraction(0)) / (len(g) * len(h))


def shift(g, h):
    """(within(g) + within(h)) / 2 - cross(g, h); None unless both have two
    runs with a value."""
    wg, wh, c = within(g), within(h), cross(g, h)
    if wg is None or wh is None or c is None:
        return None
    return (wg + wh) / 2 - c


# --- averaging ---------------------------------------------------------------------


@dataclass
class Summary:
    """A measure averaged per variable, per dimension and overall."""

    variables: dict = field(default_factory=dict)   # var -> {"tasks": {t: Q}, "mean", "interval"}
    dimensions: dict = field(default_factory=dict)  # dim -> same
    overall: dict = field(default_factory=dict)


def _block(per_task):
    values = [per_task[t] for t in sorted(per_task)]
    return {"tasks": dict(sorted(per_task.items())), "mean": mean(values),
            "interval": task_interval(values)}


def summarise(per_task_var, dimension_of, summarised):
    """Average ``{(task, var): Q(t, v)}`` in the document's order.

    ``dimension_of`` maps a variable to its dimension; ``summarised`` is the
    set of variables that enter dimension and overall values (primary ones).
    Entries must already be restricted to open variables.
    """
    out = Summary()
    by_var = {}
    for (task, var), value in per_task_var.items():
        if value is not None:
            by_var.setdefault(var, {})[task] = value
    for var in by_var:
        out.variables[var] = _block(by_var[var])
    by_task_dim = {}
    for (task, var), value in per_task_var.items():
        if value is not None and var in summarised:
            by_task_dim.setdefault((task, dimension_of[var]), []).append(value)
    per_dim = {}
    for (task, dim), values in by_task_dim.items():
        per_dim.setdefault(dim, {})[task] = mean(values)
    for dim in sorted(per_dim):
        out.dimensions[dim] = _block(per_dim[dim])
    per_task = {}
    for dim, tasks in per_dim.items():
        for task, value in tasks.items():
            per_task.setdefault(task, []).append(value)
    if per_task:
        out.overall = _block({task: mean(values) for task, values in per_task.items()})
    return out


def mean_defined(values):
    values = [v for v in values if v is not None]
    return mean(values) if values else None
