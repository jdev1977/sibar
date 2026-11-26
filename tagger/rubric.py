"""Rubrics: ``rubrics/<type>.v<N>.yaml`` and its companion, read and checked (T2.4).

A rubric is the fixed list of multiple-choice items a tagging model answers
about one output (plan.md, "Rubric tagging by a model"). The format, the
reasons for it and the calibration plan are in ``docs/rubrics.md``.

    rubric = load_checked("pipeline")          # rubric + prompts + companion
    for item in rubric.items_for("csv-to-database", "L0"):
        order = presentation_order(rubric, item, record_id)
        ...
    rubric.check_value("opening", "content")   # a stored tag

Nothing here calls a model. The tagger itself is T2.6.
"""

import hashlib
import re
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUBRICS_DIR = ROOT / "rubrics"
PROMPTS_DIR = ROOT / "prompts"

SCHEMA_VERSION = 1
LEVELS = ("L0", "L1", "L2")
SELECTS = ("single", "multi")
ORDERS = ("shuffle", "scale")
REASONS = ("direction", "content", "constraint")

# Answers every item shares. An item's own options never use these ids.
CANNOT_TELL = "cannot-tell"        # stored as null: undetermined
NOT_APPLICABLE = "not-applicable"  # stored as this text, or [] for multi-select
NONE = "none"                      # multi-select only: no option applies
OTHER = "other"                    # the catch-all option of an open set
# An option with one of these ids needs a tie rule: when does it apply?
COMBINED = ("several", "both")
RESERVED = (CANNOT_TELL, NOT_APPLICABLE)
ALWAYS_PRESENT = "always-present"  # `absent` of an item whose subject always exists
NEVER = "never"                    # `not_applicable` of an item that always applies

MIN_OPTIONS, MAX_OPTIONS = 2, 9
MAX_EXAMPLE_CHARS = 200

_FILE_NAME = re.compile(r"(?P<type>[a-z0-9][a-z0-9_-]*)\.v(?P<version>[1-9][0-9]*)\.yaml")
_ITEM_ID = re.compile(r"[a-z][a-z0-9_]*")
_OPTION_ID = re.compile(r"[a-z0-9][a-z0-9-]*")

# Words that judge instead of describe. They are refused in questions,
# definitions and the other texts that tell a tagger how to choose, so that
# no option reads as the better one (examples and `instructions` are exempt:
# an example quotes an invented output, and the instructions say what not to
# judge).
EVALUATIVE = (
    "good", "bad", "better", "best", "worse", "worst", "proper", "properly",
    "correct", "correctly", "incorrect", "incorrectly", "wrong", "wrongly",
    "appropriate", "appropriately", "adequate", "adequately", "sufficient",
    "sufficiently", "thorough", "thoroughly", "professional", "robust",
    "elegant", "sloppy", "lazy", "careful", "carefully", "rigorous",
    "comprehensive", "helpful", "excessive", "verbose", "concise", "poor",
    "poorly", "nice", "clear", "clearly", "high-quality",
)
# No text of a rubric names a model, a model family or a provider.
MODEL_NAMES = (
    "claude", "anthropic", "fable", "opus", "sonnet", "haiku", "gpt",
    "chatgpt", "openai", "gemini", "google", "llama", "mistral", "grok",
    "deepseek", "copilot", "qwen",
)
_EVALUATIVE = re.compile(r"(?<![\w-])(" + "|".join(EVALUATIVE) + r")(?![\w-])", re.I)
_MODEL_NAMES = re.compile(r"(?<![\w-])(" + "|".join(MODEL_NAMES) + r")(?![\w-])", re.I)

_TOP_KEYS = {"schema_version", "project_type", "rubric_version",
             "prompt_set_versions", "instructions", "gate", "dimensions", "items"}
_ITEM_KEYS = {"id", "dimension", "question", "select", "applies_to", "options",
              "cannot_tell", "not_applicable"}
_ITEM_OPTIONAL = {"order", "absent", "none_example", "tie_rule", "guidance",
                  "task_notes", "complete"}
_OPTION_KEYS = {"id", "definition", "example"}
_ENTRY_KEYS = {"closed", "reason", "quote", "expect", "note"}


class RubricError(ValueError):
    """A rubric file, its companion or a stored tag breaks the format."""


@dataclass(frozen=True)
class Option:
    id: str
    definition: str
    example: str


@dataclass(frozen=True)
class Special:
    """When a reserved answer is given for an item, with an example."""

    when: str
    example: str


@dataclass(frozen=True)
class Item:
    id: str
    dimension: str
    question: str
    select: str                      # single | multi
    order: str                       # shuffle | scale
    tasks: Tuple[str, ...]           # the tasks it is asked for
    levels: Tuple[str, ...]          # the levels it is asked at
    options: Tuple[Option, ...]
    absent: Optional[str]            # single: the "not present" option, or always-present
    none_example: Optional[str]      # multi: an output where no option applies
    cannot_tell: Special
    not_applicable: Optional[Special]  # None: the item always applies
    tie_rule: Optional[str] = None
    guidance: Optional[str] = None
    task_notes: Mapping[str, str] = MappingProxyType({})
    complete: bool = False           # multi: the options cover every case

    @property
    def multi(self):
        return self.select == "multi"

    @property
    def option_ids(self):
        return tuple(option.id for option in self.options)

    def applies(self, task, level):
        return task in self.tasks and level in self.levels

    def answers(self):
        """Every answer a tagger may give, options first, reserved ones last."""
        out = list(self.option_ids)
        if self.multi:
            out.append(NONE)
        out.append(CANNOT_TELL)
        if self.not_applicable is not None:
            out.append(NOT_APPLICABLE)
        return tuple(out)


@dataclass(frozen=True)
class Rubric:
    project_type: str
    version: str
    prompt_set_versions: Mapping[str, str]   # task -> version of its prompt texts
    instructions: Tuple[str, ...]
    gate_item: str
    gate_no_solution: Tuple[str, ...]
    dimensions: Mapping[str, str]
    items: Tuple[Item, ...]
    path: Path

    @property
    def name(self):
        """``<type>.v<N>``, as in the file name."""
        return f"{self.project_type}.v{self.version}"

    @property
    def extractor(self):
        """The extractor name tags are stored under (docs/record-format.md)."""
        return f"rubric.{self.project_type}"

    @property
    def tasks(self):
        return tuple(self.prompt_set_versions)

    def item(self, item_id):
        for item in self.items:
            if item.id == item_id:
                return item
        raise RubricError(f"{self.name}: no item {item_id!r}")

    def variable(self, item_id):
        """The variable name of an item in the metrics: ``rubric.<type>.<id>``."""
        return f"{self.extractor}.{self.item(item_id).id}"

    def stops_at_gate(self, value):
        """Whether a stored gate tag ends the tagging of an output.

        It does for a ``no_solution`` answer, and for None (cannot tell):
        without knowing that there is a solution, nothing else can be read.
        """
        self.check_value(self.gate_item, value)
        return value is None or value in self.gate_no_solution

    def items_for(self, task, level):
        """The items asked about an output of a task and level, gate first."""
        if task not in self.prompt_set_versions:
            raise RubricError(f"{self.name}: no task {task!r}")
        if level not in LEVELS:
            raise RubricError(f"{self.name}: no level {level!r}")
        chosen = [item for item in self.items if item.applies(task, level)]
        return tuple(sorted(chosen, key=lambda item: item.id != self.gate_item))

    def check_value(self, item_id, value):
        """Raise unless ``value`` is a storable tag for the item.

        Single-select: an option id, ``"not-applicable"`` where the item allows
        it, or None (cannot tell). Multi-select: a sorted list of distinct
        option ids, ``["none"]``, ``[]`` (not applicable, where allowed), or
        None (cannot tell).
        """
        item = self.item(item_id)
        at = f"{self.name}.{item.id}"
        if value is None:
            return
        if not item.multi:
            allowed = set(item.option_ids)
            if item.not_applicable is not None:
                allowed.add(NOT_APPLICABLE)
            if not isinstance(value, str) or value not in allowed:
                raise RubricError(f"{at}: {value!r} is not one of {sorted(allowed)}")
            return
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise RubricError(f"{at}: a multi-select tag is a list of option ids")
        if value == []:
            if item.not_applicable is None:
                raise RubricError(f"{at}: [] means not applicable, which this "
                                  f"item never is; no option is [{NONE!r}]")
            return
        if value == [NONE]:
            return
        unknown = [x for x in value if x not in item.option_ids]
        if unknown:
            raise RubricError(f"{at}: {unknown} are not options (and {NONE!r} "
                              "stands alone)")
        if value != sorted(set(value)):
            raise RubricError(f"{at}: list the options once each, sorted")


# --- Reading -----------------------------------------------------------------

class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a repeated key instead of keeping the last."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            line = key_node.start_mark.line + 1
            if not isinstance(key, Hashable):
                raise RubricError(f"unusable key on line {line}")
            if key in seen:
                raise RubricError(f"repeated key {key!r} on line {line}")
            seen.add(key)
        return super().construct_mapping(node, deep)


def _read(path):
    try:
        return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise RubricError(str(error)) from error


def _text(value, at):
    if not isinstance(value, str) or not value.strip():
        raise RubricError(f"{at} must be non-empty text")
    return " ".join(value.split())


def _keys(raw, required, optional, at):
    if not isinstance(raw, dict):
        raise RubricError(f"{at} must be a mapping")
    for key in required:
        if key not in raw:
            raise RubricError(f"{at}: missing {key}")
    for key in raw:
        if key not in required and key not in optional:
            raise RubricError(f"{at}: unknown key {key!r}")


def _no_model_names(text, at):
    found = _MODEL_NAMES.search(text)
    if found:
        raise RubricError(f"{at}: names a model or provider ({found.group(0)!r})")


def _descriptive(text, at):
    """Text that tells a tagger how to choose: no judging word, no model name."""
    found = _EVALUATIVE.search(text)
    if found:
        raise RubricError(f"{at}: {found.group(0)!r} judges; describe what the "
                          "response does instead")
    _no_model_names(text, at)
    return text


def _example(value, at):
    text = _text(value, at)
    if len(text) > MAX_EXAMPLE_CHARS:
        raise RubricError(f"{at}: an example is at most {MAX_EXAMPLE_CHARS} characters")
    _no_model_names(text, at)
    return text


def _special(raw, at):
    _keys(raw, {"when", "example"}, set(), at)
    return Special(when=_descriptive(_text(raw["when"], f"{at}.when"), f"{at}.when"),
                   example=_example(raw["example"], f"{at}.example"))


def _applies_to(raw, tasks, at):
    _keys(raw, {"tasks", "levels"}, set(), at)
    out = []
    for key, universe in (("tasks", tuple(tasks)), ("levels", LEVELS)):
        value = raw[key]
        if value == "all":
            out.append(universe)
            continue
        if not isinstance(value, list) or not value:
            raise RubricError(f"{at}.{key} must be 'all' or a non-empty list")
        for entry in value:
            if entry not in universe:
                raise RubricError(f"{at}.{key}: {entry!r} is not one of "
                                  f"{', '.join(universe)}")
        if len(set(value)) != len(value):
            raise RubricError(f"{at}.{key}: an entry is listed twice")
        if len(value) == len(universe):
            raise RubricError(f"{at}.{key}: write 'all'")
        out.append(tuple(entry for entry in universe if entry in value))
    return out


def _item(raw, tasks, dimensions, at):
    _keys(raw, _ITEM_KEYS, _ITEM_OPTIONAL, at)
    item_id = raw["id"]
    if not isinstance(item_id, str) or not _ITEM_ID.fullmatch(item_id):
        raise RubricError(f"{at}.id must be lower-case letters, digits and '_', "
                          "starting with a letter")
    at = f"item {item_id}"
    if raw["dimension"] not in dimensions:
        raise RubricError(f"{at}: dimension {raw['dimension']!r} is not declared")
    question = _descriptive(_text(raw["question"], f"{at}.question"), f"{at}.question")
    if not question.endswith("?") or question.count("?") != 1:
        raise RubricError(f"{at}.question must be one question, ending in '?'")
    select = raw["select"]
    if select not in SELECTS:
        raise RubricError(f"{at}.select must be one of {', '.join(SELECTS)}")
    order = raw.get("order", "shuffle")
    if order not in ORDERS:
        raise RubricError(f"{at}.order must be one of {', '.join(ORDERS)}")
    item_tasks, item_levels = _applies_to(raw["applies_to"], tasks, f"{at}.applies_to")

    if not isinstance(raw["options"], list):
        raise RubricError(f"{at}.options must be a list")
    if not MIN_OPTIONS <= len(raw["options"]) <= MAX_OPTIONS:
        raise RubricError(f"{at}: {MIN_OPTIONS} to {MAX_OPTIONS} options, "
                          f"not {len(raw['options'])}")
    options = []
    for index, entry in enumerate(raw["options"]):
        _keys(entry, _OPTION_KEYS, set(), f"{at}.options[{index}]")
        option_id = entry["id"]
        if not isinstance(option_id, str) or not _OPTION_ID.fullmatch(option_id):
            raise RubricError(f"{at}.options[{index}].id must be lower-case "
                              "letters, digits and '-'")
        where = f"{at}.{option_id}"
        if option_id in RESERVED or (select == "multi" and option_id == NONE):
            raise RubricError(f"{where}: a reserved answer cannot be an option")
        if option_id in (ALWAYS_PRESENT, NEVER):
            raise RubricError(f"{where}: {option_id!r} is a keyword of the format")
        if option_id in [option.id for option in options]:
            raise RubricError(f"{where}: option listed twice")
        options.append(Option(
            id=option_id,
            definition=_descriptive(_text(entry["definition"], f"{where}.definition"),
                                    f"{where}.definition"),
            example=_example(entry["example"], f"{where}.example")))
    ids = [option.id for option in options]
    if order == "shuffle" and ids != sorted(ids):
        raise RubricError(f"{at}: list the options in alphabetical order of id "
                          f"({', '.join(sorted(ids))}), or declare order: scale")

    absent = none_example = None
    if select == "single":
        if "none_example" in raw:
            raise RubricError(f"{at}: none_example belongs to a multi-select item")
        absent = raw.get("absent")
        if absent != ALWAYS_PRESENT and absent not in ids:
            raise RubricError(f"{at}.absent must name the option that means "
                              f"'not present', or be {ALWAYS_PRESENT!r}")
    else:
        if "absent" in raw:
            raise RubricError(f"{at}: a multi-select item answers {NONE!r} when "
                              "no option applies; it has no absent key")
        if "none_example" not in raw:
            raise RubricError(f"{at}: missing none_example")
        none_example = _example(raw["none_example"], f"{at}.none_example")
    complete = raw.get("complete", False)
    if complete is not False and (complete is not True or select != "multi"):
        raise RubricError(f"{at}.complete may only be true, on a multi-select item")
    if select == "multi" and not complete and OTHER not in ids:
        raise RubricError(f"{at}: a multi-select item has an {OTHER!r} option, "
                          "or declares complete: true when its options cover "
                          "every case")
    if any(option_id in COMBINED for option_id in ids) and "tie_rule" not in raw:
        raise RubricError(f"{at}: an item with a 'several' or 'both' option "
                          "needs a tie_rule that says when it applies")

    cannot_tell = _special(raw["cannot_tell"], f"{at}.cannot_tell")
    not_applicable = None
    if raw["not_applicable"] != NEVER:
        not_applicable = _special(raw["not_applicable"], f"{at}.not_applicable")

    examples = [option.example for option in options] + [cannot_tell.example]
    examples += [none_example] if none_example else []
    examples += [not_applicable.example] if not_applicable else []
    if len(set(examples)) != len(examples):
        raise RubricError(f"{at}: two answers share one example")

    optional = {}
    for key in ("tie_rule", "guidance"):
        if key in raw:
            optional[key] = _descriptive(_text(raw[key], f"{at}.{key}"), f"{at}.{key}")
    task_notes = {}
    if "task_notes" in raw:
        if not isinstance(raw["task_notes"], dict) or not raw["task_notes"]:
            raise RubricError(f"{at}.task_notes must be a mapping of task to text")
        for task, note in raw["task_notes"].items():
            if task not in item_tasks:
                raise RubricError(f"{at}.task_notes: the item is not asked for {task!r}")
            task_notes[task] = _descriptive(_text(note, f"{at}.task_notes.{task}"),
                                            f"{at}.task_notes.{task}")
    return Item(
        id=item_id, dimension=raw["dimension"], question=question, select=select,
        order=order, tasks=item_tasks, levels=item_levels, options=tuple(options),
        absent=absent, none_example=none_example, cannot_tell=cannot_tell,
        not_applicable=not_applicable, task_notes=MappingProxyType(task_notes),
        complete=complete, **optional)


def _rubric(raw, path):
    _keys(raw, _TOP_KEYS, set(), "the file")
    named = _FILE_NAME.fullmatch(path.name)
    if not named:
        raise RubricError("a rubric file is named <type>.v<N>.yaml")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != SCHEMA_VERSION:
        raise RubricError(f"schema_version must be {SCHEMA_VERSION}")
    if raw["project_type"] != named["type"]:
        raise RubricError(f"project_type {raw['project_type']!r} must equal the "
                          f"type in the file name, {named['type']!r}")
    if not isinstance(raw["rubric_version"], str):
        raise RubricError('rubric_version must be text: quote it, such as "1"')
    if raw["rubric_version"] != named["version"]:
        raise RubricError(f"rubric_version {raw['rubric_version']!r} must equal "
                          f"the version in the file name, {named['version']!r}")

    versions = raw["prompt_set_versions"]
    if not isinstance(versions, dict) or not versions:
        raise RubricError("prompt_set_versions must map each task to the "
                          "version of its prompt texts")
    for task, version in versions.items():
        if not isinstance(task, str) or not isinstance(version, str) or not version:
            raise RubricError(f"prompt_set_versions.{task}: the version must be "
                              'text: quote it, such as "1"')

    if not isinstance(raw["instructions"], list) or not raw["instructions"]:
        raise RubricError("instructions must be a non-empty list of texts")
    instructions = []
    for index, line in enumerate(raw["instructions"]):
        text = _text(line, f"instructions[{index}]")
        _no_model_names(text, f"instructions[{index}]")
        instructions.append(text)

    dimensions = raw["dimensions"]
    if not isinstance(dimensions, dict) or not dimensions:
        raise RubricError("dimensions must map each dimension to a description")
    for name, description in dimensions.items():
        if not isinstance(name, str) or not _OPTION_ID.fullmatch(name):
            raise RubricError(f"dimension {name!r} must be lower-case letters, "
                              "digits and '-'")
        _text(description, f"dimensions.{name}")

    if not isinstance(raw["items"], list) or not raw["items"]:
        raise RubricError("items must be a non-empty list")
    items = []
    for index, entry in enumerate(raw["items"]):
        item = _item(entry, versions, dimensions, f"items[{index}]")
        if item.id in [other.id for other in items]:
            raise RubricError(f"item {item.id}: id used twice")
        items.append(item)
    unused = set(dimensions) - {item.dimension for item in items}
    if unused:
        raise RubricError(f"dimensions without an item: {', '.join(sorted(unused))}")

    _keys(raw["gate"], {"item", "no_solution"}, set(), "gate")
    by_id = {item.id: item for item in items}
    gate = by_id.get(raw["gate"]["item"])
    if gate is None:
        raise RubricError(f"gate.item {raw['gate']['item']!r} is not an item")
    if gate.multi or gate.not_applicable is not None or gate.absent != ALWAYS_PRESENT \
            or gate.tasks != tuple(versions) or gate.levels != LEVELS:
        raise RubricError("the gate item is single-select, always present, never "
                          "not applicable, and asked for every task and level")
    no_solution = raw["gate"]["no_solution"]
    if not isinstance(no_solution, list) or not no_solution or \
            any(answer not in gate.option_ids for answer in no_solution) or \
            len(set(no_solution)) == len(gate.options):
        raise RubricError("gate.no_solution must list some, not all, of the gate "
                          "item's options")
    for task in versions:
        if not any(item.id != gate.id and task in item.tasks for item in items):
            raise RubricError(f"task {task}: no item beyond the gate")

    return Rubric(
        project_type=raw["project_type"], version=raw["rubric_version"],
        prompt_set_versions=MappingProxyType(dict(versions)),
        instructions=tuple(instructions), gate_item=gate.id,
        gate_no_solution=tuple(no_solution),
        dimensions=MappingProxyType(dict(dimensions)), items=tuple(items), path=path)


def check_against_prompts(rubric, prompts):
    """The rubric covers exactly the tasks of its type, at their versions.

    ``prompts`` maps task id to a loaded prompt task (``runner.prompts``).
    """
    missing = sorted(set(prompts) - set(rubric.tasks))
    extra = sorted(set(rubric.tasks) - set(prompts))
    if missing or extra:
        raise RubricError(f"{rubric.name}: prompt_set_versions must list the "
                          f"tasks under prompts/{rubric.project_type}/ "
                          f"(missing: {missing}; not a task: {extra})")
    for task, version in rubric.prompt_set_versions.items():
        if prompts[task].project_type != rubric.project_type:
            raise RubricError(f"{rubric.name}: {task} is not a "
                              f"{rubric.project_type} task")
        if prompts[task].prompt_set_version != version:
            raise RubricError(
                f"{rubric.name}: task {task} was read at prompt set version "
                f"{version!r}; the prompts are at "
                f"{prompts[task].prompt_set_version!r}. Read the new texts, then "
                "update the version here")


def load_rubric(path, prompts=None):
    """Read and check one rubric file; raise :class:`RubricError` naming it.

    With ``prompts`` (task id -> prompt task) the tasks are checked as well.
    """
    path = Path(path)
    try:
        rubric = _rubric(_read(path), path)
        if prompts is not None:
            check_against_prompts(rubric, prompts)
        return rubric
    except RubricError as error:
        raise RubricError(f"{path.name}: {error}") from None


# --- The companion: what each prompt dictates ---------------------------------

@dataclass(frozen=True)
class Dictated:
    """``rubrics/<type>.v<N>.dictated.yaml``: the items each prompt closes."""

    rubric: str                    # <type>.v<N>
    tasks: Mapping[str, dict]      # task -> body, as in analysis/<type>/dictated.yaml
    path: Path

    def closed(self, task, level):
        """Item ids an entry closes for a task and level."""
        out = []
        for entry in self.tasks.get(task, {}).get(level) or []:
            out.extend(name.rsplit(".", 1)[1] for name in entry["closed"])
        return tuple(out)


def _quotes(entry):
    quote = entry["quote"]
    return [quote] if isinstance(quote, str) else list(quote)


def _item_of(name, rubric, at):
    prefix = rubric.extractor + "."
    if not isinstance(name, str) or not name.startswith(prefix):
        raise RubricError(f"{at}: {name!r} must be {prefix}<item id>")
    return rubric.item(name[len(prefix):])


def _expect(raw, item, at):
    if not isinstance(raw, dict) or not raw:
        raise RubricError(f"{at} must be a mapping")
    kinds = {"present", "absent"} if item.multi else {"in"}
    for kind, values in raw.items():
        if kind not in kinds:
            raise RubricError(f"{at}: {sorted(kinds)} only for a "
                              f"{item.select}-select item, not {kind!r}")
        if not isinstance(values, list) or not values:
            raise RubricError(f"{at}.{kind} must be a non-empty list")
        allowed = item.option_ids + ((NONE,) if item.multi else ())
        for value in values:
            if value not in allowed:
                raise RubricError(f"{at}.{kind}: {value!r} is not an answer of "
                                  f"{item.id}")
    if item.multi and set(raw.get("present", ())) & set(raw.get("absent", ())):
        raise RubricError(f"{at}: an option is both present and absent")


def load_dictated(path, rubric, prompts=None):
    """Read and check the companion of ``rubric``.

    With ``prompts`` every quote is looked up in wording A at its level.
    """
    path = Path(path)
    try:
        raw = _read(path)
        _keys(raw, {"schema_version", "project_type", "rubric", "tasks"}, set(),
              "the file")
        if raw["schema_version"] != SCHEMA_VERSION or \
                raw["project_type"] != rubric.project_type or \
                raw["rubric"] != rubric.name or path.name != f"{rubric.name}.dictated.yaml":
            raise RubricError(f"the companion of {rubric.name} is "
                              f"{rubric.name}.dictated.yaml, with rubric: {rubric.name}")
        if not isinstance(raw["tasks"], dict):
            raise RubricError("tasks must be a mapping")
        if set(raw["tasks"]) != set(rubric.tasks):
            raise RubricError("tasks must list every task of the rubric, and "
                              "no other")
        for task, body in raw["tasks"].items():
            _keys(body, {"prompt_set_version"}, set(LEVELS) | {"associations"},
                  f"task {task}")
            if body["prompt_set_version"] != rubric.prompt_set_versions[task]:
                raise RubricError(f"task {task}: prompt_set_version differs from "
                                  "the rubric's")
            for level in LEVELS:
                seen = set()
                if level != "L2" and body.get(level):
                    # docs/leak-check.md: L0 and L1 name none of the open
                    # choices. Wording that may pull one is an association.
                    raise RubricError(f"task {task}: {level} closes nothing; "
                                      "list wording that may pull a choice "
                                      "under associations")
                for index, entry in enumerate(body.get(level) or []):
                    at = f"{task}.{level}[{index}]"
                    _keys(entry, {"closed", "reason", "quote"},
                          _ENTRY_KEYS, at)
                    if entry["reason"] not in REASONS:
                        raise RubricError(f"{at}.reason must be one of "
                                          f"{', '.join(REASONS)}")
                    if not isinstance(entry["closed"], list) or not entry["closed"]:
                        raise RubricError(f"{at}.closed must be a non-empty list")
                    for name in entry["closed"]:
                        item = _item_of(name, rubric, f"{at}.closed")
                        if not item.applies(task, level):
                            raise RubricError(f"{at}: {item.id} is not asked for "
                                              f"{task} at {level}")
                        if item.id == rubric.gate_item:
                            raise RubricError(f"{at}: the gate item is never closed")
                        if item.id in seen:
                            raise RubricError(f"{at}: {item.id} is closed twice")
                        seen.add(item.id)
                    for name, expect in (entry.get("expect") or {}).items():
                        if name not in entry["closed"]:
                            raise RubricError(f"{at}.expect: {name} is not in "
                                              "this entry's closed list")
                        _expect(expect, _item_of(name, rubric, at),
                                f"{at}.expect.{name}")
                    _check_quotes(entry, prompts, task, level, at)
            for level, notes in (body.get("associations") or {}).items():
                if level not in LEVELS or not isinstance(notes, list):
                    raise RubricError(f"task {task}: associations is a mapping of "
                                      "level to a list")
                for index, note in enumerate(notes):
                    at = f"{task}.associations.{level}[{index}]"
                    _keys(note, {"variables", "quote", "note"}, set(), at)
                    for name in note["variables"]:
                        if not _item_of(name, rubric, at).applies(task, level):
                            raise RubricError(f"{at}: {name} is not asked there")
                    _check_quotes(note, prompts, task, level, at)
        return Dictated(rubric=rubric.name, tasks=MappingProxyType(dict(raw["tasks"])),
                        path=path)
    except RubricError as error:
        raise RubricError(f"{path.name}: {error}") from None


def _check_quotes(entry, prompts, task, level, at):
    for quote in _quotes(entry):
        _text(quote, f"{at}.quote")
        if prompts is not None and quote not in prompts[task].text(level, "A"):
            raise RubricError(f"{at}: the quote {quote!r} is not in wording A")


# --- Finding the files ----------------------------------------------------------

def load_type_prompts(project_type, prompts_dir=PROMPTS_DIR):
    """``{task id: prompt task}`` for one project type."""
    from runner.prompts import PromptError, load_prompts
    try:
        tasks = load_prompts([Path(prompts_dir) / project_type])
    except PromptError as error:
        raise RubricError(str(error)) from error
    return {task.task_id: task for task in tasks}


def rubric_path(project_type, version="1", directory=RUBRICS_DIR):
    return Path(directory) / f"{project_type}.v{version}.yaml"


def load_checked(project_type, version="1", directory=RUBRICS_DIR,
                 prompts_dir=PROMPTS_DIR):
    """A rubric checked against its prompts, with its companion checked too.

    Returns the rubric; :func:`load_dictated` gives the companion.
    """
    prompts = load_type_prompts(project_type, prompts_dir)
    rubric = load_rubric(rubric_path(project_type, version, directory), prompts)
    load_dictated(dictated_path(rubric), rubric, prompts)
    return rubric


def dictated_path(rubric):
    return rubric.path.with_name(f"{rubric.name}.dictated.yaml")


# --- For the tagger (T2.6) and the metrics (T1.6) --------------------------------

def presentation_order(rubric, item, key):
    """Option ids in the order to show them for one output.

    ``key`` identifies the output (its record id). The order depends only on
    the rubric name, the item and the key, so tagging the same output twice
    shows the same order. A ``shuffle`` item gets a permutation; a ``scale``
    item keeps its order or is reversed. Reserved answers are not in the
    list: show them after the options, always in the same place.
    """
    seed = hashlib.sha256(f"{rubric.name}:{item.id}:{key}".encode("utf-8")).digest()
    ids = list(item.option_ids)
    if item.order == "scale":
        return tuple(reversed(ids)) if seed[0] & 1 else tuple(ids)
    return tuple(sorted(ids, key=lambda option_id: hashlib.sha256(
        seed + option_id.encode("utf-8")).digest()))


def variable_declarations(rubric):
    """The rubric's items as ``features.yaml`` declarations (docs/metrics.md).

    Single-select -> categorical; multi-select -> set whose empty list is
    "not applicable" (no option is the item ``none``). Every item starts
    ``provisional``: a model read it, and calibration (T2.5) has not yet
    checked it. ``dimension`` is per item, which ``features.yaml`` does not
    yet take (it has one dimension per extractor); see docs/rubrics.md.
    """
    out = {}
    for item in rubric.items:
        if item.multi:
            entry = {"type": "set", "empty": NOT_APPLICABLE}
        else:
            entry = {"type": "categorical"}
            if item.not_applicable is not None:
                entry["not_applicable"] = [NOT_APPLICABLE]
        entry.update(role="provisional", why="heuristic", dimension=item.dimension)
        out[item.id] = entry
    return {rubric.extractor: out}
