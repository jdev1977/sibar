"""From record files to runs (docs/metrics.md, "Which runs count" and "From
features to variables").

One record per planned run: per cell key, the first record by timestamp
whose status is not ``failed``. Each selected record gets an outcome; only
``artifact`` runs carry variable values. Everything that would make a table
mean something other than it says is refused with a message.
"""

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from runner.record import cell_key, read_records

from analysis.spec import LEVELS, WORDINGS

OUTCOMES = ("artifact", "no-artifact", "unread", "truncated", "refused")
EXTRACTOR_STATUSES = ("ok", "partial", "no-input", "error")
# The runner stores what a response said about its own serving (service tier
# and the like) in the record's settings under this prefix. Those values vary
# per response and are not settings that were sent, so they are not compared.
REPORTED_PREFIX = "reported_"


class Refused(Exception):
    """The metrics refuse to compute; the message says why."""


class _State:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


UND = _State("undetermined")
NA = _State("not applicable")


def has_value(value):
    return value is not UND and value is not NA


# --- conversion -------------------------------------------------------------------


def bin_label(value, var):
    """The bin of a whole number; refuses one below the first edge."""
    if type(value) is not int:
        raise Refused(f"{var.name}: {value!r} is not a whole number")
    edges = var.bins
    if value < edges[0]:
        raise Refused(f"{var.name}: {value} is below its first bin edge {edges[0]}")
    labels = var.labels
    for index in range(len(edges) - 1, -1, -1):
        if value >= edges[index]:
            return labels[index]


def item_text(element):
    """A list element as an item: text as it is, anything else as JSON."""
    if isinstance(element, str):
        return element
    return json.dumps(element, sort_keys=True, separators=(",", ":"))


def coverage(part, whole):
    """``none`` / ``some`` / ``all``; not applicable when ``whole`` is 0."""
    if whole == 0:
        return NA
    if part == 0:
        return "none"
    return "all" if part == whole else "some"


def ordered_pairs(elements):
    """``[a, b]`` -> ``{^>a, a>b, b>$}``; the empty list is ``{^>$}``."""
    chain = ["^"] + [item_text(e) for e in elements] + ["$"]
    return frozenset(f"{a}>{b}" for a, b in zip(chain, chain[1:]))


def convert(var, raw):
    """A stored feature value as the variable's value (choice text, item set,
    or NA). ``raw`` must not be None."""
    kind = var.type
    if kind == "categorical":
        if not isinstance(raw, str):
            raise Refused(f"{var.name}: {raw!r} is not text")
        return NA if raw in var.not_applicable else raw
    if kind == "boolean":
        if not isinstance(raw, bool):
            raise Refused(f"{var.name}: {raw!r} is not true or false")
        return "true" if raw else "false"
    if kind == "number":
        return bin_label(raw, var)
    if kind in ("set", "ordered-list"):
        if not isinstance(raw, list):
            raise Refused(f"{var.name}: {raw!r} is not a list")
        if not raw and var.empty == "not-applicable":
            return NA
        if kind == "set":
            return frozenset(item_text(e) for e in raw)
        return ordered_pairs(raw)
    if kind == "count-map":
        if not isinstance(raw, dict) or not all(
                type(n) is int for n in raw.values()):
            raise Refused(f"{var.name}: {raw!r} is not a map of names to counts")
        if not raw and var.empty == "not-applicable":
            return NA
        return frozenset(k for k, n in raw.items() if n >= var.minimum(k))
    raise Refused(f"{var.name}: cannot convert type {kind}")


@dataclass
class RunValues:
    values: dict                 # variable -> value | UND | NA (masks applied)
    masked: bool
    statuses: dict               # extractor -> status
    health: dict                 # health rate name -> True / False / None


def _features_by_extractor(record):
    out = {}
    for entry in record["features"]:
        out.setdefault(entry["extractor"], {})[entry["name"]] = entry["value"]
    return out


def read_values(record, spec):
    """Every variable's value for one usable run, masks applied."""
    stored = _features_by_extractor(record)
    statuses = {}
    for extractor in spec.extractor_versions:
        status = stored.get(extractor, {}).get("status")
        if status not in EXTRACTOR_STATUSES:
            raise Refused(f"record {record['record_id']}: {extractor} has status "
                          f"{status!r}, not one of {', '.join(EXTRACTOR_STATUSES)}")
        statuses[extractor] = status
    values = {}
    for name, var in spec.variables.items():
        if var.tasks and record["task_id"] not in var.tasks:
            values[name] = NA      # not asked of this task
            continue
        status = statuses[var.extractor]
        if status in ("no-input", "error"):
            values[name] = UND
            continue
        features = stored.get(var.extractor, {})
        if var.type == "coverage":
            part, whole = features.get(var.part), features.get(var.whole)
            if part is None or whole is None:
                values[name] = UND
                continue
            for label, number in ((var.part, part), (var.whole, whole)):
                if type(number) is not int or number < 0:
                    raise Refused(f"{var.name}: {label} is {number!r}, not a count")
            values[name] = coverage(part, whole)
            continue
        raw = features.get(var.feature)
        values[name] = UND if raw is None else convert(var, raw)
    masked = False
    for mask in spec.masks:
        tested = values[mask.variable]
        if mask.applies(tested, has_value(tested)):
            masked = True
            for target in mask.targets:
                values[target] = UND
    health = {f"partial:{extractor}": status == "partial"
              for extractor, status in statuses.items()}
    for name, var in spec.variables.items():
        if var.role != "diagnostic" or var.common:
            continue
        if statuses[var.extractor] not in ("ok", "partial") or not has_value(values[name]):
            health[f"present:{name}"] = None
            continue
        value = values[name]
        if isinstance(value, frozenset):
            health[f"present:{name}"] = bool(value)
        elif var.type == "number":
            health[f"present:{name}"] = value != var.labels[0]
        else:
            health[f"present:{name}"] = True
    health["masked"] = masked
    return RunValues(values, masked, statuses, health)


# --- selection -------------------------------------------------------------------


@dataclass
class Run:
    """One selected record: the run of its cell key."""

    record_id: str
    model: str
    task: str
    level: str
    wording: str
    run_index: int
    timestamp: str
    batch_id: str
    model_id_returned: Optional[str]
    settings: str  # what was sent (reported_* values left out), as JSON text
    outcome: str
    values: dict = field(default_factory=dict)
    masked: bool = False
    statuses: dict = field(default_factory=dict)
    health: dict = field(default_factory=dict)
    served: str = "{}"  # the reported_* values of the record, as JSON text

    @property
    def usable(self):
        return self.outcome == "artifact"

    def value(self, name):
        """The value for stats: a choice or set, or None without a value."""
        value = self.values.get(name, UND)
        return value if has_value(value) else None


@dataclass
class Selection:
    runs: list
    notes: list
    batches: tuple
    files: tuple


def parse_time(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_records(paths):
    """Records of the files, in file order; refuses a file with bad lines."""
    records, notes, seen = [], [], {}
    for path in paths:
        try:
            found = read_records(path)
        except OSError as error:
            raise Refused(f"{path}: {error}") from None
        if found.problems:
            problem = found.problems[0]
            raise Refused(f"{path}: line {problem.line} is not a valid record: "
                          f"{'; '.join(problem.errors)}")
        if found.truncated_tail is not None:
            notes.append(f"{path}: an unfinished last line (interrupted write) "
                         "was ignored")
        for record in found.records:
            first = seen.setdefault(record["record_id"], path)
            if first != path:
                raise Refused(f"record {record['record_id']} is in both {first} and {path}")
        records.extend(found.records)
    return records, notes


def _version_fits(version, want):
    """``want`` is a version, or ``<rubric version>@*``: any one tagger."""
    if want.endswith("@*"):
        return version.startswith(want[:-1]) and len(version) >= len(want)
    return version == want


def _check_one_tagger(records, spec):
    """Refuse a table whose tags come from two tagger models."""
    for name, want in spec.extractor_versions.items():
        if not want.endswith("@*"):
            continue
        found = sorted({e["extractor_version"] for record in records
                        for e in record["extractors"] if e["extractor"] == name})
        if len(found) > 1:
            raise Refused(f"{name}: records tagged at {' and '.join(found)}; "
                          "tags of two taggers are never mixed")


def _check_extractors(record, spec, required):
    listed = {e["extractor"]: e["extractor_version"] for e in record["extractors"]}
    rid = record["record_id"]
    prefix = spec.project_type + "."
    for name in listed:
        if name.startswith(prefix) and name not in spec.extractor_versions:
            raise Refused(f"record {rid}: extractor {name} is not declared in "
                          f"{spec.source.get('features', 'features.yaml')}")
    for name in required:
        want = spec.extractor_versions[name]
        if name not in listed:
            raise Refused(f"record {rid}: extractor {name} has not run on it; "
                          "re-run python -m extractors first")
        if not _version_fits(listed[name], want):
            raise Refused(f"record {rid}: extractor {name} is at version "
                          f"{listed[name]}, the metrics read version {want}; "
                          "re-run python -m extractors first (versions are never mixed)")
    for entry in record["features"]:
        if entry["extractor"] in required and \
                entry["name"] not in spec.declared_features(entry["extractor"]):
            raise Refused(f"record {rid}: feature {entry['name']} of "
                          f"{entry['extractor']} is not declared in features.yaml")


def _outcome(record, spec):
    status = record["status"]
    if status in ("truncated", "refused"):
        return status
    if spec.outcome is not None:
        return _gated_outcome(record, spec)
    structure_extractor = _structure_extractor(spec)
    _check_extractors(record, spec, [structure_extractor])
    features = _features_by_extractor(record).get(structure_extractor, {})
    fs_status = features.get("status")
    if fs_status == "error":
        return "unread"
    if fs_status == "no-input":
        return "no-artifact"
    if fs_status not in ("ok", "partial"):
        raise Refused(f"record {record['record_id']}: {structure_extractor} has "
                      f"status {fs_status!r}")
    structure = features.get("structure")
    if structure is None:
        return "unread"
    return "no-artifact" if structure == "no-html" else "artifact"


def _gated_outcome(record, spec):
    """The outcome of a type with a rubric: the gate item says whether the
    reply gives a solution, and ``needs`` whether it delivered anything."""
    gate = spec.variables[spec.outcome.gate]
    needs = spec.variables.get(spec.outcome.needs)
    required = [gate.extractor] + ([needs.extractor] if needs else [])
    _check_extractors(record, spec, required)
    stored = _features_by_extractor(record)

    def read(var):
        features = stored.get(var.extractor, {})
        status = features.get("status")
        if status not in EXTRACTOR_STATUSES:
            raise Refused(f"record {record['record_id']}: {var.extractor} has "
                          f"status {status!r}")
        return status, features.get(var.feature)

    status, answer = read(gate)
    if status in ("error", "no-input") or answer is None:
        return "unread"
    if answer in spec.outcome.no_solution:
        return "no-artifact"
    if needs:
        status, value = read(needs)
        if status == "error":
            return "unread"
        if status == "no-input" or value in spec.outcome.needs_no_artifact:
            return "no-artifact"
    return "artifact"


def _structure_extractor(spec):
    """The extractor whose ``structure`` feature says whether there is a page."""
    for var in spec.variables.values():
        if var.feature == "structure" and not var.common:
            return var.extractor
    raise Refused("features.yaml declares no `structure` feature to decide outcomes")


def select(records, spec, batches):
    """The runs of the batch group: one per cell key, with outcomes and
    values. ``batches`` are the batch ids named for the group."""
    batches = tuple(batches)
    notes = []
    scoped, skipped = [], 0
    for order, record in enumerate(records):
        if record["project_type"] != spec.project_type or record["batch_id"] not in batches:
            continue
        if record["source"] != "controlled" or record["surface"] != "api":
            skipped += 1
            continue
        task = record["task_id"]
        if task not in spec.tasks:
            raise Refused(f"record {record['record_id']}: task {task!r} is not in "
                          "dictated.yaml")
        if record["prompt_set_version"] != spec.prompt_set_version(task):
            raise Refused(
                f"record {record['record_id']}: prompt_set_version "
                f"{record['prompt_set_version']!r} of {task}, but dictated.yaml was "
                f"read from version {spec.prompt_set_version(task)!r}")
        if record["level"] not in LEVELS or record["wording"] not in WORDINGS:
            raise Refused(f"record {record['record_id']}: level or wording outside the grid")
        scoped.append((parse_time(record["timestamp"]), order, record))
    if skipped:
        notes.append(f"{skipped} records that are not controlled API runs were left out")
    chosen = {}
    for moment, order, record in sorted(scoped, key=lambda x: (x[0], x[1])):
        if record["status"] == "failed":
            continue
        chosen.setdefault(cell_key(record), record)
    _check_one_tagger([r for r in chosen.values() if r["status"] == "ok"], spec)
    settings, serving = {}, {}
    runs = []
    for key in sorted(chosen, key=lambda k: tuple("" if v is None else str(v) for v in k)):
        record = chosen[key]
        sent, served = split_settings(record["settings"])
        text = _dump(sent)
        settings.setdefault(record["model_id"], set()).add(text)
        serving.setdefault(record["model_id"], set()).add(_dump(served))
        outcome = _outcome(record, spec)
        run = Run(record_id=record["record_id"], model=record["model_id"],
                  task=record["task_id"], level=record["level"],
                  wording=record["wording"], run_index=record["run_index"],
                  timestamp=record["timestamp"], batch_id=record["batch_id"],
                  model_id_returned=record["model_id_returned"], settings=text,
                  outcome=outcome, served=_dump(served))
        if outcome == "artifact":
            _check_extractors(record, spec, list(spec.extractor_versions))
            read = read_values(record, spec)
            run.values, run.masked = read.values, read.masked
            run.statuses, run.health = read.statuses, read.health
        runs.append(run)
    for model, texts in sorted(settings.items()):
        if len(texts) > 1:
            raise Refused(f"model {model}: records with {len(texts)} different "
                          f"`settings` values ({'; '.join(sorted(texts))}); one table "
                          "takes one setting")
    for model, texts in sorted(serving.items()):
        if len(texts) > 1:
            notes.append(f"model {model}: responses reported different serving "
                         f"({'; '.join(sorted(texts))}); these are not settings "
                         "that were sent, so the records are compared")
    runs.sort(key=lambda r: (r.model, r.task, r.level, r.wording, r.run_index))
    return Selection(runs=runs, notes=notes, batches=batches, files=())


def split_settings(settings):
    """(sent, reported): a record's settings without and with only the
    ``reported_*`` values the runner stored from the response."""
    sent = {k: v for k, v in settings.items() if not k.startswith(REPORTED_PREFIX)}
    reported = {k: v for k, v in settings.items() if k.startswith(REPORTED_PREFIX)}
    return sent, reported


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def select_files(paths, spec, batches):
    records, notes = load_records(paths)
    selection = select(records, spec, batches)
    selection.notes = notes + selection.notes
    selection.files = tuple(str(Path(p)) for p in paths)
    return selection
