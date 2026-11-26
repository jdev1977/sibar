"""Rubrics (T2.4): the files under rubrics/ and the loader in tagger/rubric.py.

The first half checks the real rubrics against the prompts and each other.
The second half feeds the loader small broken rubrics, one fault each.
"""

import copy
from collections import Counter
from pathlib import Path

import pytest
import yaml

from tagger.rubric import (
    CANNOT_TELL, LEVELS, MAX_OPTIONS, NONE, NOT_APPLICABLE, RUBRICS_DIR,
    RubricError, check_against_prompts, dictated_path, load_checked,
    load_dictated, load_rubric, load_type_prompts, presentation_order,
    variable_declarations)

ROOT = Path(__file__).resolve().parents[1]
TYPES = ("pipeline", "math", "engineering", "website")
# The most items one output is tagged with (docs/rubrics.md, "Size").
MAX_ITEMS_PER_OUTPUT = 15
# Items that mean the same in every rubric that has them.
SHARED = ("response_mode", "result_form", "opening", "closing",
          "assumptions_stated", "answer_position")


@pytest.fixture(scope="module")
def rubrics():
    return {name: load_checked(name) for name in TYPES}


@pytest.fixture(scope="module")
def companions(rubrics):
    return {name: load_dictated(dictated_path(rubric), rubric,
                                load_type_prompts(name))
            for name, rubric in rubrics.items()}


# --- The real files ------------------------------------------------------------

def test_every_rubric_file_is_loaded_here_and_has_a_companion():
    files = sorted(p.name for p in RUBRICS_DIR.glob("*.yaml")
                   if not p.name.endswith(".dictated.yaml"))
    assert files == sorted(f"{name}.v1.yaml" for name in TYPES)
    for name in TYPES:
        assert (RUBRICS_DIR / f"{name}.v1.dictated.yaml").is_file()


@pytest.mark.parametrize("name", TYPES)
def test_version_in_the_name_matches_the_content(rubrics, name):
    rubric = rubrics[name]
    assert rubric.path.name == f"{name}.v{rubric.version}.yaml"
    assert rubric.name == f"{name}.v1"
    assert rubric.extractor == f"rubric.{name}"


@pytest.mark.parametrize("name", TYPES)
def test_the_rubric_covers_the_tasks_of_its_type(rubrics, name):
    prompts = load_type_prompts(name)
    rubric = rubrics[name]
    assert set(rubric.tasks) == set(prompts)
    for task, version in rubric.prompt_set_versions.items():
        assert prompts[task].prompt_set_version == version
    for item in rubric.items:
        assert set(item.tasks) <= set(prompts) and item.tasks
        assert set(item.levels) <= set(LEVELS) and item.levels


@pytest.mark.parametrize("name", TYPES)
def test_item_ids_are_unique_and_every_dimension_is_used(rubrics, name):
    rubric = rubrics[name]
    ids = [item.id for item in rubric.items]
    assert len(ids) == len(set(ids))
    assert {item.dimension for item in rubric.items} == set(rubric.dimensions)


@pytest.mark.parametrize("name", TYPES)
def test_every_item_has_an_example_of_each_answer(rubrics, name):
    for item in rubrics[name].items:
        examples = {option.id: option.example for option in item.options}
        examples[CANNOT_TELL] = item.cannot_tell.example
        if item.multi:
            examples[NONE] = item.none_example
        if item.not_applicable is not None:
            examples[NOT_APPLICABLE] = item.not_applicable.example
        assert set(examples) == set(item.answers()), item.id
        for answer, example in examples.items():
            assert example and example.strip(), (item.id, answer)
        assert len(set(examples.values())) == len(examples), item.id
        for option in item.options:
            assert option.definition.strip(), (item.id, option.id)


@pytest.mark.parametrize("name", TYPES)
def test_every_single_select_item_says_how_absence_is_answered(rubrics, name):
    for item in rubrics[name].items:
        if item.multi:
            assert item.absent is None and NONE not in item.option_ids
        else:
            assert item.absent == "always-present" or item.absent in item.option_ids


@pytest.mark.parametrize("name", TYPES)
def test_a_rubric_is_small_enough_to_tag(rubrics, name):
    rubric = rubrics[name]
    for task in rubric.tasks:
        counts = {len(rubric.items_for(task, level)) for level in LEVELS}
        assert max(counts) <= MAX_ITEMS_PER_OUTPUT, task
        assert min(counts) >= 2, task
    for item in rubric.items:
        assert len(item.options) <= MAX_OPTIONS


@pytest.mark.parametrize("name", TYPES)
def test_the_gate_is_asked_first_for_every_output(rubrics, name):
    rubric = rubrics[name]
    assert rubric.gate_item == "response_mode"
    assert set(rubric.gate_no_solution) == {"asks-first", "declines"}
    for task in rubric.tasks:
        for level in LEVELS:
            assert rubric.items_for(task, level)[0].id == rubric.gate_item


def test_shared_items_read_the_same_in_every_rubric(rubrics):
    def facing(item):
        """Everything a tagger is told about an item, examples aside."""
        return (item.question, item.select, item.order, item.absent,
                item.tie_rule, item.guidance,
                tuple((o.id, o.definition) for o in item.options),
                item.cannot_tell.when,
                item.not_applicable and item.not_applicable.when)

    seen = Counter()
    for item_id in SHARED:
        versions = {facing(rubric.item(item_id)) for rubric in rubrics.values()
                    if item_id in [item.id for item in rubric.items]}
        assert len(versions) == 1, item_id
    for rubric in rubrics.values():
        seen.update(item.id for item in rubric.items)
    # An id used in two rubrics is a shared item, and is listed above.
    assert {item_id for item_id, count in seen.items() if count > 1} == set(SHARED)
    assert len({rubric.instructions for rubric in rubrics.values()}) == 1


def test_items_per_task_as_documented(rubrics):
    """The counts in docs/rubrics.md, "Size"."""
    counted = {name: {task: len(rubric.items_for(task, "L0")) for task in rubric.tasks}
               for name, rubric in rubrics.items()}
    assert counted == {
        "pipeline": {"ci-workflow": 7, "csv-to-database": 12, "daily-api-fetch": 12,
                     "data-validation": 11, "image-resize": 10, "log-aggregation": 10},
        "math": {"entropy-explanation": 5, "hypothesis-test": 11,
                 "least-squares-fit": 10, "loan-amortization": 10,
                 "projectile-drag": 10, "titration-curve": 10},
        "engineering": {"cantilever-beam": 15, "compression-spring": 14,
                        "conveyor-gear-ratio": 12, "heat-sink": 14,
                        "pipe-and-pump": 14, "shelf-bracket": 15},
        "website": {task: 6 for task in rubrics["website"].tasks},
    }
    assert {name: len(rubric.items) for name, rubric in rubrics.items()} == {
        "pipeline": 19, "math": 19, "engineering": 24, "website": 6}


# --- The companions --------------------------------------------------------------

@pytest.mark.parametrize("name", TYPES)
def test_l0_and_l1_close_nothing(companions, rubrics, name):
    for task in rubrics[name].tasks:
        assert companions[name].closed(task, "L0") == ()
        assert companions[name].closed(task, "L1") == ()
        assert companions[name].closed(task, "L2"), task


def test_closed_items_of_some_cells(companions):
    assert set(companions["pipeline"].closed("csv-to-database", "L2")) == {
        "sample_data", "input_assumption", "cleaning_steps",
        "bad_input_handling", "rerun_behavior", "storage_kind"}
    assert set(companions["math"].closed("entropy-explanation", "L2")) == {
        "entropy_framings", "entropy_examples", "closing"}
    assert set(companions["engineering"].closed("heat-sink", "L2")) == {
        "assumptions_stated", "result_form", "material_assumed", "cooling_mode",
        "interface_resistance", "part_selection"}
    # Rule 15 of docs/leak-check.md: at L2 the brief gives the assumptions.
    for task in ("hypothesis-test", "least-squares-fit", "loan-amortization",
                 "projectile-drag", "titration-curve"):
        assert "assumptions_stated" in companions["math"].closed(task, "L2")
    for task in companions["engineering"].tasks:
        assert "assumptions_stated" in companions["engineering"].closed(task, "L2")


@pytest.mark.parametrize("name", TYPES)
def test_tone_items_stay_open_unless_a_brief_names_them(companions, rubrics, name):
    closed = {(task, item) for task in rubrics[name].tasks
              for item in companions[name].closed(task, "L2")}
    assert {pair for pair in closed if pair[1] in ("opening", "closing")} <= {
        ("entropy-explanation", "closing")}


# --- Stored tags ------------------------------------------------------------------

def test_check_value_single_select(rubrics):
    rubric = rubrics["pipeline"]
    rubric.check_value("opening", "content")
    rubric.check_value("opening", None)                    # cannot tell
    rubric.check_value("rerun_behavior", NOT_APPLICABLE)
    for bad in ("not-an-option", NOT_APPLICABLE, CANNOT_TELL, ["content"], 3):
        with pytest.raises(RubricError):
            rubric.check_value("opening", bad)             # never not applicable
    with pytest.raises(RubricError):
        rubric.check_value("no_such_item", "content")


def test_check_value_multi_select(rubrics):
    rubric = rubrics["pipeline"]
    rubric.check_value("bad_input_handling", ["repairs", "sets-aside"])
    rubric.check_value("bad_input_handling", [NONE])
    rubric.check_value("bad_input_handling", [])           # not applicable
    rubric.check_value("bad_input_handling", None)
    for bad in ("repairs", ["sets-aside", "repairs"], ["repairs", "repairs"],
                [NONE, "repairs"], ["nope"], [NOT_APPLICABLE]):
        with pytest.raises(RubricError):
            rubric.check_value("bad_input_handling", bad)
    with pytest.raises(RubricError):
        rubric.check_value("scheduling", [])               # never not applicable


def test_variable_declarations(rubrics):
    declared = variable_declarations(rubrics["pipeline"])["rubric.pipeline"]
    assert set(declared) == {item.id for item in rubrics["pipeline"].items}
    assert declared["opening"] == {
        "type": "categorical", "role": "provisional", "why": "heuristic",
        "dimension": "tone"}
    assert declared["rerun_behavior"]["not_applicable"] == [NOT_APPLICABLE]
    assert declared["scheduling"] == {
        "type": "set", "empty": NOT_APPLICABLE, "role": "provisional",
        "why": "heuristic", "dimension": "operation"}


# --- Option order -----------------------------------------------------------------

def test_presentation_order_is_a_repeatable_permutation(rubrics):
    rubric = rubrics["pipeline"]
    item = rubric.item("closing")
    first = presentation_order(rubric, item, "record-1")
    assert first == presentation_order(rubric, item, "record-1")
    assert sorted(first) == sorted(item.option_ids)
    orders = {presentation_order(rubric, item, f"record-{n}") for n in range(40)}
    assert len(orders) > 10
    # Another item, or another rubric version, shuffles differently.
    assert any(presentation_order(rubric, rubric.item("opening"), f"r{n}")[0]
               != presentation_order(rubric, rubric.item("opening"), f"s{n}")[0]
               for n in range(20))


def test_presentation_order_puts_every_option_first_about_equally(rubrics):
    rubric = rubrics["pipeline"]
    item = rubric.item("response_mode")                    # four options
    firsts = Counter(presentation_order(rubric, item, f"record-{n}")[0]
                     for n in range(800))
    assert set(firsts) == set(item.option_ids)
    assert all(140 <= count <= 260 for count in firsts.values()), firsts


def test_a_scale_keeps_its_order_or_is_reversed(rubrics):
    rubric = rubrics["pipeline"]
    item = rubric.item("assumptions_stated")
    assert item.order == "scale"
    orders = {presentation_order(rubric, item, f"record-{n}") for n in range(40)}
    assert orders == {item.option_ids, tuple(reversed(item.option_ids))}


# --- A small rubric to break -------------------------------------------------------

class FakePrompt:
    def __init__(self, version="1", project_type="demo", texts=None):
        self.prompt_set_version = version
        self.project_type = project_type
        self._texts = texts or {}

    def text(self, level, wording):
        return self._texts.get((level, wording), "Make a thing.")


def minimal():
    return {
        "schema_version": 1,
        "project_type": "demo",
        "rubric_version": "1",
        "prompt_set_versions": {"task-a": "1", "task-b": "1"},
        "instructions": ["Answer from the response alone."],
        "gate": {"item": "mode", "no_solution": ["asks"]},
        "dimensions": {"response": "How the request is taken up",
                       "method": "What is done"},
        "items": [
            {"id": "mode", "dimension": "response",
             "question": "What does the response do?",
             "select": "single", "applies_to": {"tasks": "all", "levels": "all"},
             "absent": "always-present",
             "options": [
                 {"id": "answers", "definition": "Delivers a solution.",
                  "example": "A script."},
                 {"id": "asks", "definition": "Asks and delivers nothing.",
                  "example": "'Which file?'"}],
             "cannot_tell": {"when": "The response is empty.", "example": "''"},
             "not_applicable": "never"},
            {"id": "steps", "dimension": "method",
             "question": "Which steps does the code take?",
             "select": "multi",
             "applies_to": {"tasks": ["task-a"], "levels": "all"},
             "none_example": "The file is copied unchanged.",
             "options": [
                 {"id": "sorts", "definition": "Sorts the rows.",
                  "example": "rows.sort()"},
                 {"id": "trims", "definition": "Strips spaces.",
                  "example": "value.strip()"}],
             "cannot_tell": {"when": "The steps are in a file that is not shown.",
                             "example": "'import steps'"},
             "not_applicable": {"when": "The response has no code.",
                                "example": "A prose outline."}},
            {"id": "store", "dimension": "method",
             "question": "Where is the result kept?",
             "select": "single", "order": "scale",
             "applies_to": {"tasks": "all", "levels": ["L0", "L1"]},
             "absent": "nowhere",
             "options": [
                 {"id": "nowhere", "definition": "The result is not kept.",
                  "example": "It is printed."},
                 {"id": "file", "definition": "In a file.",
                  "example": "out.csv is written."}],
             "cannot_tell": {"when": "The storing call is not shown.",
                             "example": "'save(rows)'"},
             "not_applicable": "never"},
        ],
    }


def write(tmp_path, raw, name="demo.v1.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
    return path


def prompts(**changes):
    out = {"task-a": FakePrompt(), "task-b": FakePrompt()}
    out.update(changes)
    return out


def test_the_minimal_rubric_loads(tmp_path):
    rubric = load_rubric(write(tmp_path, minimal()), prompts())
    assert [item.id for item in rubric.items_for("task-a", "L0")] == ["mode", "steps", "store"]
    assert [item.id for item in rubric.items_for("task-b", "L2")] == ["mode"]
    assert rubric.item("steps").answers() == (
        "sorts", "trims", NONE, CANNOT_TELL, NOT_APPLICABLE)
    assert rubric.item("store").answers() == ("nowhere", "file", CANNOT_TELL)
    with pytest.raises(RubricError):
        rubric.items_for("task-c", "L0")
    with pytest.raises(RubricError):
        rubric.items_for("task-a", "L3")


def item(raw, item_id):
    return next(entry for entry in raw["items"] if entry["id"] == item_id)


def _version_differs(raw): raw["rubric_version"] = "2"
def _version_is_a_number(raw): raw["rubric_version"] = 1
def _type_differs(raw): raw["project_type"] = "other"
def _unknown_top_key(raw): raw["extra"] = 1
def _unknown_item_key(raw): item(raw, "mode")["weight"] = 2
def _item_id_twice(raw): raw["items"].append(copy.deepcopy(item(raw, "store")))
def _item_id_not_a_slug(raw): item(raw, "store")["id"] = "Store-Kind"
def _option_twice(raw): item(raw, "steps")["options"][1]["id"] = "sorts"
def _one_option(raw): item(raw, "steps")["options"].pop()
def _too_many_options(raw):
    item(raw, "steps")["options"] = [
        {"id": f"o{n:02d}", "definition": f"Does thing {n}.", "example": f"Thing {n}."}
        for n in range(MAX_OPTIONS + 1)]
def _no_example(raw): del item(raw, "steps")["options"][0]["example"]
def _empty_example(raw): item(raw, "steps")["options"][0]["example"] = "  "
def _long_example(raw): item(raw, "steps")["options"][0]["example"] = "x" * 201
def _shared_example(raw): item(raw, "steps")["options"][1]["example"] = "rows.sort()"
def _no_definition(raw): item(raw, "mode")["options"][0]["definition"] = ""
def _reserved_option(raw): item(raw, "mode")["options"][1]["id"] = "cannot-tell"
def _none_as_multi_option(raw): item(raw, "steps")["options"][0]["id"] = "none"
def _not_alphabetical(raw): item(raw, "steps")["options"].reverse()
def _judging_definition(raw):
    item(raw, "steps")["options"][0]["definition"] = "Sorts the rows correctly."
def _judging_question(raw):
    item(raw, "store")["question"] = "Is the result kept in a proper place?"
def _model_named(raw):
    item(raw, "steps")["options"][0]["example"] = "The kind of sort Claude writes."
def _question_without_mark(raw): item(raw, "store")["question"] = "Where it is kept."
def _two_questions(raw):
    item(raw, "store")["question"] = "Is it kept? Where is the result kept?"
def _bad_select(raw): item(raw, "store")["select"] = "one"
def _bad_order(raw): item(raw, "store")["order"] = "random"
def _single_without_absent(raw): del item(raw, "store")["absent"]
def _absent_not_an_option(raw): item(raw, "store")["absent"] = "missing"
def _multi_with_absent(raw): item(raw, "steps")["absent"] = "sorts"
def _multi_without_none_example(raw): del item(raw, "steps")["none_example"]
def _no_cannot_tell(raw): del item(raw, "store")["cannot_tell"]
def _not_applicable_without_example(raw):
    item(raw, "steps")["not_applicable"] = {"when": "The response has no code."}
def _unknown_task(raw): item(raw, "steps")["applies_to"]["tasks"] = ["task-z"]
def _unknown_level(raw): item(raw, "store")["applies_to"]["levels"] = ["L0", "L9"]
def _all_written_out(raw): item(raw, "steps")["applies_to"]["tasks"] = ["task-a", "task-b"]
def _unknown_dimension(raw): item(raw, "store")["dimension"] = "storage"
def _unused_dimension(raw): raw["dimensions"]["tone"] = "How it sounds"
def _gate_unknown(raw): raw["gate"]["item"] = "nothing"
def _gate_not_everywhere(raw):
    item(raw, "mode")["applies_to"]["tasks"] = ["task-a"]
def _gate_all_options(raw): raw["gate"]["no_solution"] = ["answers", "asks"]
def _gate_unknown_answer(raw): raw["gate"]["no_solution"] = ["refuses"]
def _task_without_items(raw):
    item(raw, "store")["applies_to"]["tasks"] = ["task-a"]
def _note_for_other_task(raw):
    item(raw, "steps")["task_notes"] = {"task-b": "Judge the first step."}
def _no_instructions(raw): raw["instructions"] = []


@pytest.mark.parametrize("fault", [
    _version_differs, _version_is_a_number, _type_differs, _unknown_top_key,
    _unknown_item_key, _item_id_twice, _item_id_not_a_slug, _option_twice,
    _one_option, _too_many_options, _no_example, _empty_example, _long_example,
    _shared_example, _no_definition, _reserved_option, _none_as_multi_option,
    _not_alphabetical, _judging_definition, _judging_question, _model_named,
    _question_without_mark, _two_questions, _bad_select, _bad_order,
    _single_without_absent, _absent_not_an_option, _multi_with_absent,
    _multi_without_none_example, _no_cannot_tell,
    _not_applicable_without_example, _unknown_task, _unknown_level,
    _all_written_out, _unknown_dimension, _unused_dimension, _gate_unknown,
    _gate_not_everywhere, _gate_all_options, _gate_unknown_answer,
    _task_without_items, _note_for_other_task, _no_instructions,
], ids=lambda fault: fault.__name__.lstrip("_"))
def test_a_broken_rubric_is_refused(tmp_path, fault):
    raw = minimal()
    fault(raw)
    with pytest.raises(RubricError) as error:
        load_rubric(write(tmp_path, raw), prompts())
    assert "demo.v1.yaml" in str(error.value)


def test_the_file_name_carries_type_and_version(tmp_path):
    for name in ("demo.yaml", "demo.v0.yaml", "demo.v1.yml", "demo-v1.yaml",
                 "demo.v2.yaml", "other.v1.yaml"):
        with pytest.raises(RubricError):
            load_rubric(write(tmp_path, minimal(), name))
    raw = minimal()
    raw["rubric_version"] = "2"
    assert load_rubric(write(tmp_path, raw, "demo.v2.yaml")).name == "demo.v2"


def test_a_repeated_key_is_refused(tmp_path):
    path = write(tmp_path, minimal())
    path.write_text(path.read_text(encoding="utf-8") + "rubric_version: '1'\n",
                    encoding="utf-8")
    with pytest.raises(RubricError, match="repeated key"):
        load_rubric(path)


def test_examples_may_quote_judging_words(tmp_path):
    raw = minimal()
    item(raw, "steps")["options"][0]["example"] = "'This is the best way to sort.'"
    load_rubric(write(tmp_path, raw))


def test_applicability_refers_to_real_tasks(tmp_path):
    rubric = load_rubric(write(tmp_path, minimal()))
    check_against_prompts(rubric, prompts())
    for wrong in (
            {"task-a": FakePrompt()},                                  # a listed task has no prompts
            prompts(**{"task-c": FakePrompt()}),                       # a task of the type is not covered
            prompts(**{"task-a": FakePrompt(version="2")}),            # the prompt texts changed
            prompts(**{"task-a": FakePrompt(project_type="website")}),
    ):
        with pytest.raises(RubricError):
            check_against_prompts(rubric, wrong)


# --- A small companion to break ----------------------------------------------------

def minimal_dictated():
    return {
        "schema_version": 1, "project_type": "demo", "rubric": "demo.v1",
        "tasks": {
            "task-a": {
                "prompt_set_version": "1",
                "L2": [{"closed": ["rubric.demo.steps"], "reason": "direction",
                        "quote": "Sort the rows",
                        "expect": {"rubric.demo.steps": {"present": ["sorts"]}},
                        "note": "The brief asks for sorting."}],
                "associations": {"L1": [{"variables": ["rubric.demo.store"],
                                         "quote": "keep", "note": "Suggests a file."}]},
            },
            "task-b": {"prompt_set_version": "1"},
        },
    }


def dictated_prompts():
    return prompts(**{"task-a": FakePrompt(texts={
        ("L1", "A"): "Make a thing and keep it.",
        ("L2", "A"): "Make a thing. Sort the rows."})})


def entry(raw):
    return raw["tasks"]["task-a"]["L2"][0]


def test_the_minimal_companion_loads(tmp_path):
    rubric = load_rubric(write(tmp_path, minimal()))
    path = write(tmp_path, minimal_dictated(), "demo.v1.dictated.yaml")
    companion = load_dictated(path, rubric, dictated_prompts())
    assert companion.closed("task-a", "L2") == ("steps",)
    assert companion.closed("task-a", "L0") == ()
    assert companion.closed("task-b", "L2") == ()


def _quote_not_in_prompt(raw): entry(raw)["quote"] = "Order the rows"
def _unknown_item(raw): entry(raw)["closed"] = ["rubric.demo.nothing"]
def _bare_item_id(raw): entry(raw)["closed"] = ["steps"]
def _closes_the_gate(raw): entry(raw)["closed"].append("rubric.demo.mode")
def _item_not_asked_there(raw): entry(raw)["closed"].append("rubric.demo.store")
def _closed_twice(raw):
    raw["tasks"]["task-a"]["L2"].append(copy.deepcopy(entry(raw)))
def _bad_reason(raw): entry(raw)["reason"] = "style"
def _no_quote(raw): del entry(raw)["quote"]
def _expect_unknown_option(raw):
    entry(raw)["expect"]["rubric.demo.steps"] = {"present": ["shuffles"]}
def _expect_in_on_multi(raw):
    entry(raw)["expect"]["rubric.demo.steps"] = {"in": ["sorts"]}
def _expect_both_ways(raw):
    entry(raw)["expect"]["rubric.demo.steps"] = {"present": ["sorts"], "absent": ["sorts"]}
def _expect_not_closed(raw):
    entry(raw)["expect"]["rubric.demo.mode"] = {"in": ["answers"]}
def _task_missing(raw): del raw["tasks"]["task-b"]
def _other_prompt_version(raw): raw["tasks"]["task-a"]["prompt_set_version"] = "2"
def _other_rubric(raw): raw["rubric"] = "demo.v2"
def _unknown_entry_key(raw): entry(raw)["because"] = "x"
def _association_quote_missing(raw):
    raw["tasks"]["task-a"]["associations"]["L1"][0]["quote"] = "store forever"


@pytest.mark.parametrize("fault", [
    _quote_not_in_prompt, _unknown_item, _bare_item_id, _closes_the_gate,
    _item_not_asked_there, _closed_twice, _bad_reason, _no_quote,
    _expect_unknown_option, _expect_in_on_multi, _expect_both_ways,
    _expect_not_closed, _task_missing, _other_prompt_version, _other_rubric,
    _unknown_entry_key, _association_quote_missing,
], ids=lambda fault: fault.__name__.lstrip("_"))
def test_a_broken_companion_is_refused(tmp_path, fault):
    rubric = load_rubric(write(tmp_path, minimal()))
    raw = minimal_dictated()
    fault(raw)
    path = write(tmp_path, raw, "demo.v1.dictated.yaml")
    with pytest.raises(RubricError) as error:
        load_dictated(path, rubric, dictated_prompts())
    assert "demo.v1.dictated.yaml" in str(error.value)


def test_a_single_select_expectation_uses_in(tmp_path):
    rubric = load_rubric(write(tmp_path, minimal()))
    raw = minimal_dictated()
    raw["tasks"]["task-b"]["L0"] = [{
        "closed": ["rubric.demo.store"], "reason": "content", "quote": "Make",
        "expect": {"rubric.demo.store": {"in": ["file"]}}}]
    path = write(tmp_path, raw, "demo.v1.dictated.yaml")
    assert load_dictated(path, rubric, dictated_prompts()).closed("task-b", "L0") == ("store",)
    raw["tasks"]["task-b"]["L0"][0]["expect"] = {"rubric.demo.store": {"present": ["file"]}}
    with pytest.raises(RubricError):
        load_dictated(write(tmp_path, raw, "demo.v1.dictated.yaml"), rubric,
                      dictated_prompts())


def test_the_document_names_every_item(rubrics):
    text = (ROOT / "docs" / "rubrics.md").read_text(encoding="utf-8")
    for rubric in rubrics.values():
        for entry in rubric.items:
            assert f"`{entry.id}`" in text, entry.id
