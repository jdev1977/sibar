"""The answers of one response, as the grader reads them.

:class:`Answers` is the seam between finding answers and grading them. The
deterministic extractor (checker/extract.py) builds one from a response; an
answers file written by a person, a tagger or a model builds one through
:func:`answers_from_dict`; a model-based extractor would return one too.
The file format is described in checker/README.md.
"""

import datetime
import math
from dataclasses import dataclass, field, replace

import yaml

NOT_STATED = "not_stated"
SUPPLIED, EXTRACTED = "supplied", "extracted"
TESTS = ("t", "z", "wilcoxon", "wilcoxon_exact", "wilcoxon_normal",
         "wilcoxon_normal_corrected", "sign_flip_permutation", "sign_test", "other")
JUDGEMENTS = ("pass", "fail")
TOP_KEYS = frozenset({"record_id", "complete", "quantities", "inputs", "conditions",
                      "facts", "criteria"})
MAX_FILE_BYTES = 1_000_000
MAX_ENTRIES = 500
MAX_TEXT = 200


class AnswersError(ValueError):
    """An answers file is not in the format, or does not fit the task."""


@dataclass(frozen=True)
class Stated:
    """One statement of a quantity.

    ``value`` is a number, a word (a choice or a date) or, for a list, a
    mapping of key to number. ``hedged`` marks a statement the extractor
    found in a comparison, a condition or a check; ``doubt`` gives a reason
    a mismatch must not be called wrong; ``unsettled`` marks a response with a
    correction or summary holding a number that was not read.
    """

    value: object
    unit: object = None
    inputs: dict = field(default_factory=dict)
    source: str = SUPPLIED
    hedged: bool = False
    doubt: object = None
    unsettled: bool = False


@dataclass(frozen=True)
class Answers:
    """``quantities`` maps an id to a tuple of :class:`Stated`, or to
    :data:`NOT_STATED`. ``complete`` says everything the response states is
    here, so what is missing was not stated. ``conditions`` maps an
    alternative's id to true (the response states it), false (it does not) or
    null (unknown). ``tests`` and ``levels`` are the facts of a hypothesis
    test: the tests the response uses and the significance levels it states.
    ``seen`` holds every number of the response (extraction only)."""

    quantities: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    conditions: dict = field(default_factory=dict)
    criteria: dict = field(default_factory=dict)
    tests: tuple = ()
    levels: tuple = ()
    complete: bool = False
    seen: tuple = ()
    extracted_inputs: frozenset = frozenset()

    def condition(self, identifier):
        if identifier in self.conditions:
            return self.conditions[identifier]
        return False if self.complete else None

    def merged(self, supplied):
        """These answers with ``supplied`` ones put over them, key by key."""
        quantities = dict(self.quantities, **supplied.quantities)
        complete = self.complete or supplied.complete
        if supplied.complete:
            quantities = dict(supplied.quantities)
        return replace(
            self, quantities=quantities,
            inputs=dict(self.inputs, **supplied.inputs),
            conditions=dict(self.conditions, **supplied.conditions),
            criteria=dict(self.criteria, **supplied.criteria),
            tests=supplied.tests or self.tests,
            levels=supplied.levels or self.levels,
            complete=complete,
            extracted_inputs=self.extracted_inputs - set(supplied.inputs))


def _need(condition, message):
    if not condition:
        raise AnswersError(message)


def _mapping(value, where):
    value = {} if value is None else value
    _need(isinstance(value, dict) and len(value) <= MAX_ENTRIES,
          f"{where} must be a mapping")
    return value


def _number(value, where):
    _need(type(value) in (int, float) and abs(value) <= 1e300 and math.isfinite(value),
          f"{where} must be a finite number")
    return value


def _inputs(value, where):
    found = _mapping(value, where)
    _need(all(isinstance(name, str) for name in found), f"{where}: names are text")
    return {name: _number(number, f"{where}.{name}") for name, number in found.items()}


def _value(value, where):
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, str):
        _need(0 < len(value) <= MAX_TEXT, f"{where}: text of a sensible length")
        return value
    if isinstance(value, dict):
        _need(0 < len(value) <= MAX_ENTRIES, f"{where}: a list maps each key to a number")
        return {_number(key, f"{where} key"): _number(item, f"{where}[{key}]")
                for key, item in value.items()}
    return _number(value, where)


def _statement(entry, where):
    _need(isinstance(entry, dict) and "value" in entry
          and set(entry) <= {"value", "unit", "inputs"},
          f"{where} holds value, and maybe unit and inputs")
    unit = entry.get("unit")
    _need(unit is None or isinstance(unit, str) and len(unit) <= MAX_TEXT,
          f"{where}.unit must be text")
    return Stated(_value(entry["value"], where), unit,
                  _inputs(entry.get("inputs"), f"{where}.inputs"))


def answers_from_dict(data):
    """:class:`Answers` from the content of an answers file."""
    _need(isinstance(data, dict) and set(data) <= TOP_KEYS,
          f"an answers file holds {', '.join(sorted(TOP_KEYS))}")
    complete = data.get("complete", False)
    _need(type(complete) is bool, "complete must be true or false")
    quantities = {}
    for name, entry in _mapping(data.get("quantities"), "quantities").items():
        where = f"quantities.{name}"
        if entry == NOT_STATED:
            quantities[name] = NOT_STATED
            continue
        entries = entry if isinstance(entry, list) else [entry]
        _need(0 < len(entries) <= MAX_ENTRIES, f"{where} is empty or too long")
        quantities[name] = tuple(_statement(item, where) for item in entries)
    conditions = _mapping(data.get("conditions"), "conditions")
    _need(all(value is None or type(value) is bool for value in conditions.values()),
          "conditions are true, false or null")
    criteria = _mapping(data.get("criteria"), "criteria")
    for name, items in criteria.items():
        items = _mapping(items, f"criteria.{name}")
        _need(all(value in JUDGEMENTS for value in items.values()),
              f"criteria.{name}: each item is pass or fail")
    facts = _mapping(data.get("facts"), "facts")
    _need(set(facts) <= {"test", "level_percent"}, "facts holds test and level_percent")
    tests, levels = (), ()
    if "test" in facts:
        _need(facts["test"] in TESTS, f"facts.test is one of {', '.join(TESTS)}")
        tests = (facts["test"],)
    if "level_percent" in facts:
        level = _number(facts["level_percent"], "facts.level_percent")
        _need(0 < level < 100, "facts.level_percent is between 0 and 100")
        levels = (float(level),)
    return Answers(quantities=quantities, inputs=_inputs(data.get("inputs"), "inputs"),
                   conditions=dict(conditions), criteria=dict(criteria),
                   tests=tests, levels=levels, complete=complete)


class _NoAliases(yaml.SafeLoader):
    """The safe loader, without aliases (which can expand without bound)."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise AnswersError("an answers file may not use YAML aliases")
        return super().compose_node(parent, index)


def read_answers_file(path):
    """The content of an answers file (YAML or JSON): ``{record_id: Answers}``,
    with the key None for a file that names no record."""
    with open(path, "rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    _need(len(data) <= MAX_FILE_BYTES, "the answers file is too large")
    try:
        loaded = yaml.load(data.decode("utf-8-sig"), Loader=_NoAliases)
    except (yaml.YAMLError, UnicodeDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, AnswersError):
            raise
        raise AnswersError(f"the answers file is not YAML: {type(error).__name__}") \
            from None
    entries = loaded if isinstance(loaded, list) else [loaded]
    found = {}
    for entry in entries:
        answers = answers_from_dict(entry)
        identifier = entry.get("record_id")
        _need(identifier is None or isinstance(identifier, str), "record_id is text")
        _need(identifier not in found, "two entries for one record")
        found[identifier] = answers
    return found
