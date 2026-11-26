"""The two data files of a project type, read once (docs/metrics.md).

``features.yaml`` says how every feature becomes a variable; ``dictated.yaml``
says which variables each prompt closes. Nothing here knows a feature name:
everything comes from the files.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "analysis"

SINGLE_TYPES = ("categorical", "boolean", "number", "coverage")
SET_TYPES = ("set", "ordered-list", "count-map")
ROLES = ("primary", "provisional", "secondary", "diagnostic")
LEVELS = ("L0", "L1", "L2")
WORDINGS = ("A", "B")


class SpecError(ValueError):
    """A data file is missing, unreadable or inconsistent."""


def bin_labels(edges):
    """``[0, 1, 3, 6]`` -> ``["0", "1-2", "3-5", "6+"]``."""
    labels = []
    for index, low in enumerate(edges):
        if index + 1 == len(edges):
            labels.append(f"{low}+")
        else:
            high = edges[index + 1] - 1
            labels.append(str(low) if low == high else f"{low}-{high}")
    return labels


@dataclass(frozen=True)
class Variable:
    """One feature or derived variable, as ``features.yaml`` declares it."""

    name: str            # <extractor>.<feature>
    extractor: str
    feature: str
    type: str
    role: str
    dimension: str
    bins: Optional[tuple] = None
    empty: str = "value"
    not_applicable: frozenset = frozenset()
    min_count: tuple = ()          # ((key, minimum), ...), "default" included
    no_verdict: frozenset = frozenset()
    depends_on: tuple = ()
    task_driven: bool = False
    part: Optional[str] = None     # coverage only
    whole: Optional[str] = None
    common: bool = False           # status, error, skipped_files
    tasks: tuple = ()              # asked only in these tasks; () is every task

    @property
    def single(self):
        """True for a variable with one value per run."""
        return self.type in SINGLE_TYPES

    @property
    def labels(self):
        return tuple(bin_labels(self.bins)) if self.bins else ()

    def order_key(self, choice):
        """Sort key for listing choices: bins in bin order, else alphabetical."""
        if self.type == "number" and choice in self.labels:
            return (0, self.labels.index(choice), "")
        return (1, 0, str(choice))

    def minimum(self, key):
        table = dict(self.min_count)
        return table.get(key, table.get("default", 1))


@dataclass(frozen=True)
class Mask:
    name: str
    variable: str
    in_: Optional[frozenset]
    not_in: Optional[frozenset]
    targets: frozenset

    def applies(self, value, has_value):
        """Whether a run whose tested variable is ``value`` is masked. A run
        without a value for it is masked: the condition cannot be ruled out."""
        if not has_value:
            return True
        if self.in_ is not None:
            return value in self.in_
        return value not in self.not_in


@dataclass(frozen=True)
class Expect:
    in_: Optional[tuple] = None
    absent: Optional[tuple] = None
    present: Optional[tuple] = None
    no_verdict: frozenset = frozenset()


@dataclass(frozen=True)
class Outcome:
    """How a type without pages decides that a run has an artifact: the
    rubric's gate item, and optionally a feature that shows nothing was
    delivered (docs/metrics.md, "Types with a rubric")."""

    gate: str
    no_solution: frozenset
    needs: Optional[str] = None
    needs_no_artifact: frozenset = frozenset()


@dataclass
class Spec:
    project_type: str
    metrics_version: str
    extractor_versions: dict
    dimensions: dict              # extractor -> dimension
    variables: dict               # name -> Variable (features, derived, common)
    masks: tuple
    tasks: dict                   # task -> dictated body
    source: dict = field(default_factory=dict)  # file paths, for messages
    outcome: Optional[Outcome] = None    # None: read from `structure` (website)

    # --- names ---------------------------------------------------------------

    def declared_features(self, extractor):
        """Feature names an extractor may store (common ones included)."""
        cache = self.__dict__.setdefault("_declared_cache", {})
        if extractor not in cache:   # derived variables are not stored features
            cache[extractor] = frozenset(
                v.feature for v in self.variables.values()
                if v.extractor == extractor and v.type != "coverage")
        return cache[extractor]

    def table_variables(self):
        """Every variable that has a frequency table: all but diagnostic."""
        return [v for v in self.variables.values() if v.role != "diagnostic"]

    def resolve(self, pattern):
        """Variable names a name or ``<extractor>.*`` stands for; ``*`` leaves
        out diagnostic variables."""
        if pattern.endswith(".*"):
            extractor = pattern[:-2]
            return [n for n, v in self.variables.items()
                    if v.extractor == extractor and v.role != "diagnostic"]
        if pattern not in self.variables:
            raise SpecError(f"{pattern}: not a declared variable")
        return [pattern]

    # --- prompts -------------------------------------------------------------

    def prompt_set_version(self, task):
        return str(self.tasks[task]["prompt_set_version"])

    def _entries(self, task, level):
        return self.tasks[task].get(level) or []

    def closed(self, task, level):
        """``{variable: closer}`` for every variable closed in a task and level.
        ``closer`` is None for a variable an entry lists, else the variable it
        depends on that closed it (followed step by step)."""
        listed = set()
        for entry in self._entries(task, level):
            for pattern in entry["closed"]:
                listed.update(self.resolve(pattern))
        closed = set(listed)
        grew = True
        while grew:
            grew = False
            for name, var in self.variables.items():
                if name not in closed and closed.intersection(var.depends_on):
                    closed.add(name)
                    grew = True
        out = {}
        for name in self.variables:
            if name in listed:
                out[name] = None
            elif name in closed:
                out[name] = next(dep for dep in self.variables[name].depends_on
                                 if dep in closed)
        return out

    def closed_cached(self, task, level):
        cache = self.__dict__.setdefault("_closed_cache", {})
        if (task, level) not in cache:
            cache[(task, level)] = self.closed(task, level)
        return cache[(task, level)]

    def is_open(self, task, level, name):
        return name not in self.closed_cached(task, level)

    def expectations(self, task, level):
        """``{variable: Expect}`` for a task and level."""
        out = {}
        for entry in self._entries(task, level):
            for name, raw in (entry.get("expect") or {}).items():
                out[name] = Expect(
                    in_=tuple(str(x) for x in raw["in"]) if "in" in raw else None,
                    absent=tuple(str(x) for x in raw["absent"]) if "absent" in raw else None,
                    present=tuple(str(x) for x in raw["present"]) if "present" in raw else None,
                    no_verdict=frozenset(str(x) for x in raw.get("no_verdict", ())))
        return out

    def associations(self, task, level):
        """The association notes for content at a level (they close nothing)."""
        out = []
        for note in (self.tasks[task].get("associations") or {}).get(level, []):
            names = []
            for pattern in note["variables"]:
                names.extend(self.resolve(pattern))
            quote = note["quote"]
            out.append({"variables": names,
                        "quote": quote if isinstance(quote, str) else list(quote),
                        "note": note.get("note")})
        return out


def _variable(name, extractor, feature, raw, dimension, common=False):
    kind = raw["type"]
    if kind not in SINGLE_TYPES + SET_TYPES:
        raise SpecError(f"{name}: unknown type {kind!r}")
    if raw.get("role") not in ROLES:
        raise SpecError(f"{name}: unknown role {raw.get('role')!r}")
    # A variable may name its own dimension, overriding its extractor's: all
    # tags of a rubric come from one extractor, each item with its dimension.
    if "dimension" in raw:
        dimension = raw["dimension"]
        if not isinstance(dimension, str) or not dimension.strip():
            raise SpecError(f"{name}: dimension must be a name")
    bins = None
    if kind == "number":
        bins = tuple(raw.get("bins") or ())
        if (len(bins) < 2 or list(bins) != sorted(set(bins))
                or not all(type(edge) is int for edge in bins)):
            raise SpecError(f"{name}: bins must be two or more ascending whole numbers")
    return Variable(
        name=name, extractor=extractor, feature=feature, type=kind,
        role=raw["role"], dimension=dimension, bins=bins,
        empty=raw.get("empty", "value"),
        not_applicable=frozenset(str(x) for x in raw.get("not_applicable", ())),
        min_count=tuple(sorted((raw.get("min_count") or {}).items())),
        no_verdict=frozenset(str(x) for x in raw.get("no_verdict", ())),
        depends_on=tuple(raw.get("depends_on", ())),
        task_driven=bool(raw.get("task_driven", False)),
        part=raw.get("part"), whole=raw.get("whole"), common=common,
        tasks=tuple(raw.get("tasks", ())))


def _outcome(raw, variables):
    if raw is None:
        return None
    needs = raw.get("needs") or {}
    for name in [raw["gate"], *([needs["variable"]] if needs else [])]:
        if name not in variables:
            raise SpecError(f"outcome: {name} is not declared")
    return Outcome(
        gate=raw["gate"], no_solution=frozenset(raw["no_solution"]),
        needs=needs.get("variable"),
        needs_no_artifact=frozenset(needs.get("no_artifact", ())))


def _read_yaml(path):
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SpecError(f"{path}: {error}") from None


def load_spec(project_type="website", directory=None):
    """Read ``analysis/<type>/features.yaml`` and ``dictated.yaml``."""
    folder = Path(directory) if directory else ANALYSIS_DIR / project_type
    features_path, dictated_path = folder / "features.yaml", folder / "dictated.yaml"
    features, dictated = _read_yaml(features_path), _read_yaml(dictated_path)
    if features.get("project_type") != project_type or \
            dictated.get("project_type") != project_type:
        raise SpecError(f"{folder}: the data files are not for {project_type!r}")
    dimensions = dict(features["dimensions"])
    variables = {}
    for extractor, entries in features["features"].items():
        if extractor not in dimensions:
            raise SpecError(f"{extractor}: no dimension")
        for feature, raw in entries.items():
            name = f"{extractor}.{feature}"
            variables[name] = _variable(name, extractor, feature, raw, dimensions[extractor])
        for feature, raw in features.get("common", {}).items():
            name = f"{extractor}.{feature}"
            if name in variables:
                raise SpecError(f"{name}: declared twice")
            variables[name] = _variable(name, extractor, feature, raw,
                                        dimensions[extractor], common=True)
    for extractor, entries in (features.get("derived") or {}).items():
        for feature, raw in entries.items():
            name = f"{extractor}.{feature}"
            if name in variables:
                raise SpecError(f"{name}: declared twice")
            var = _variable(name, extractor, feature, raw, dimensions[extractor])
            for part in (var.part, var.whole):
                source = variables.get(f"{extractor}.{part}")
                if source is None or source.type != "number":
                    raise SpecError(f"{name}: {part} is not a number feature of {extractor}")
            variables[name] = var
    for name, var in variables.items():
        for dep in var.depends_on:
            if dep not in variables:
                raise SpecError(f"{name}: depends on undeclared {dep}")
    spec = Spec(
        project_type=project_type,
        metrics_version=str(features["metrics_version"]),
        extractor_versions={k: str(v) for k, v in features["extractor_versions"].items()},
        dimensions=dimensions, variables=variables, masks=(),
        tasks=dict(dictated["tasks"]),
        source={"features": str(features_path), "dictated": str(dictated_path)},
        outcome=_outcome(features.get("outcome"), variables))
    for name, var in variables.items():
        unknown = set(var.tasks) - set(spec.tasks)
        if unknown:
            raise SpecError(f"{name}: unknown tasks {', '.join(sorted(unknown))}")
    built = []
    for raw in features.get("masks") or ():
        when = raw["when"]
        if when["variable"] not in variables:
            raise SpecError(f"mask {raw['name']}: {when['variable']} is not declared")
        targets = set()
        for pattern in raw["undetermined"]:
            targets.update(spec.resolve(pattern))
        targets.discard(when["variable"])   # a mask never hides what it tests
        built.append(Mask(
            name=raw["name"], variable=when["variable"],
            in_=frozenset(str(x) for x in when["in"]) if "in" in when else None,
            not_in=frozenset(str(x) for x in when["not_in"]) if "not_in" in when else None,
            targets=frozenset(targets)))
    spec.masks = tuple(built)
    for task in spec.tasks:
        for level in LEVELS:
            for entry in spec._entries(task, level):
                for pattern in entry["closed"]:
                    spec.resolve(pattern)
                for name in entry.get("expect") or {}:
                    spec.resolve(name)
    return spec
