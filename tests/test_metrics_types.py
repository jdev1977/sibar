"""The data files the metrics read for the pipeline, math and engineering
types (T2.8): analysis/<type>/features.yaml and dictated.yaml agree with the
extractors, the rubrics and the prompts; and the metrics read records of
these types."""

import uuid
from pathlib import Path

import pytest
import yaml

from analysis import tables
from analysis.runs import NA, UND, Refused, select
from analysis.spec import LEVELS, load_spec
from extractors.base import InputFile, Inputs, run_extractors
from extractors.registry import extractors_for
from runner.files import extract_files
from runner.prompts import load_prompts
from runner.record import build_record, with_features
from tagger.rubric import load_checked, variable_declarations

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
TYPES = ("pipeline", "math", "engineering")
SINGLE = {"categorical", "boolean", "number"}
JSON_TYPES = {"categorical": str, "boolean": bool, "number": int, "set": list}


def read(project_type, name):
    path = ROOT / "analysis" / project_type / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=TYPES)
def kind(request):
    return request.param


@pytest.fixture(scope="module")
def spec(kind):
    return load_spec(kind)


@pytest.fixture(scope="module")
def extracted(kind):
    out = []
    for folder in sorted((FIXTURES / kind).iterdir()):
        out.append({name: values for name, (_, values) in run_extractors(
            extractors_for(kind), Inputs.from_directory(folder)).items()})
    return out


# --- features.yaml -------------------------------------------------------------


def test_versions_match_the_registry_and_the_rubric(kind, spec):
    wanted = {e.name: e.version for e in extractors_for(kind)}
    wanted[f"rubric.{kind}"] = f"{load_checked(kind).version}@*"
    assert spec.extractor_versions == wanted
    assert set(spec.dimensions) == set(wanted)


def test_every_extracted_feature_is_declared_and_nothing_else(kind, extracted):
    features = read(kind, "features.yaml")
    common = set(features["common"])
    for extractor in extractors_for(kind):
        declared = features["features"][extractor.name]
        seen = set()
        for page in extracted:
            seen |= set(page[extractor.name])
        assert seen - common == set(declared), extractor.name
        for name, entry in declared.items():
            for page in extracted:
                value = page[extractor.name].get(name)
                if value is None:
                    continue
                assert isinstance(value, JSON_TYPES[entry["type"]]), (name, value)
                assert (entry["type"] == "boolean") == isinstance(value, bool), name
        for name, entry in declared.items():
            assert (entry["role"] == "primary") == ("why" not in entry) or \
                entry["role"] == "provisional", name


def test_rubric_variables_are_the_rubric_s_declarations(kind):
    features = read(kind, "features.yaml")
    rubric = load_checked(kind)
    declared = features["features"][rubric.extractor]
    expected = variable_declarations(rubric)[rubric.extractor]
    assert set(declared) == set(expected)
    for item in rubric.items:
        entry = dict(declared[item.id])
        tasks = entry.pop("tasks", None)
        assert entry == expected[item.id], item.id
        asked = None if set(item.tasks) == set(rubric.prompt_set_versions) \
            else sorted(item.tasks)
        assert (None if tasks is None else sorted(tasks)) == asked, item.id
        assert tuple(item.levels) == LEVELS, item.id


def test_every_dimension_of_the_extractors_has_a_counted_variable(spec):
    for extractor in spec.extractor_versions:
        roles = {v.role for v in spec.variables.values()
                 if v.extractor == extractor and not v.common}
        assert roles & {"primary", "provisional"}, extractor


# --- dictated.yaml ---------------------------------------------------------------


@pytest.fixture(scope="module")
def prompts(kind):
    return {t.task_id: t for t in load_prompts([ROOT / "prompts" / kind])}


def entries(dictated):
    for task, body in dictated["tasks"].items():
        for level in LEVELS:
            for entry in body.get(level, []):
                yield task, level, entry


def test_tasks_versions_and_quotes_match_the_prompts(kind, prompts):
    dictated = read(kind, "dictated.yaml")
    assert set(dictated["tasks"]) == set(prompts)
    for task, body in dictated["tasks"].items():
        assert body["prompt_set_version"] == prompts[task].prompt_set_version
    notes = [(task, level, note) for task, body in dictated["tasks"].items()
             for level, listed in body.get("associations", {}).items()
             for note in listed]
    for task, level, entry in list(entries(dictated)) + notes:
        quote = entry["quote"]
        for text in [quote] if isinstance(quote, str) else quote:
            assert text in prompts[task].text(level, "A"), (task, level, text)


def test_the_rubric_companion_is_included_as_it_is(kind):
    dictated = read(kind, "dictated.yaml")
    companion = yaml.safe_load(
        (ROOT / "rubrics" / f"{kind}.v1.dictated.yaml").read_text(encoding="utf-8"))
    for task, body in companion["tasks"].items():
        for level in LEVELS:
            for entry in body.get(level, []):
                assert entry in dictated["tasks"][task][level], (task, level)
        for level, notes in body.get("associations", {}).items():
            for note in notes:
                assert note in dictated["tasks"][task]["associations"][level]
    # and no rubric item is closed outside it
    for task, level, entry in entries(dictated):
        if any(name.startswith("rubric.") for name in entry["closed"]):
            assert entry in companion["tasks"][task].get(level, []), (task, level)


def test_only_given_units_close_anything_below_l2(kind):
    for task, level, entry in entries(read(kind, "dictated.yaml")):
        if level != "L2":
            assert entry["closed"] == [f"{kind}.units.unit_system"], (task, level)
            assert entry["reason"] == "content"


def test_expected_values_fit_and_closed_variables_exist(kind, spec):
    dictated = read(kind, "dictated.yaml")
    seen = set()
    for task, level, entry in entries(dictated):
        assert entry["reason"] in ("direction", "content", "constraint")
        closed = {n for pattern in entry["closed"] for n in spec.resolve(pattern)}
        for name, expect in entry.get("expect", {}).items():
            assert name in closed, (task, name)
            assert (task, level, name) not in seen, (task, level, name)
            seen.add((task, level, name))
            var = spec.variables[name]
            if var.single:
                assert {"in"} <= set(expect) <= {"in", "no_verdict"}
                assert all(isinstance(v, str) for v in expect["in"]), name
                if var.type == "number":
                    assert set(expect["in"]) <= set(var.labels), name
                if var.type == "boolean":
                    assert set(expect["in"]) <= {"true", "false"}, name
                assert not set(expect["in"]) & var.not_applicable, name
            else:
                assert expect and set(expect) <= {"present", "absent"}, name
    for task, body in dictated["tasks"].items():
        for level, notes in body.get("associations", {}).items():
            for note in notes:
                for pattern in note["variables"]:
                    assert not set(spec.resolve(pattern)) & set(spec.closed(task, level))


# --- reading records -----------------------------------------------------------


FIXTURE = {"pipeline": "csv-package", "math": "projectile", "engineering": "cantilever"}
TASKS = {"pipeline": ("csv-to-database", "daily-api-fetch", "log-aggregation"),
         "math": ("projectile-drag", "loan-amortization", "titration-curve"),
         "engineering": ("cantilever-beam", "heat-sink", "shelf-bracket")}
TAGGER = "claude-example"


def tags(rubric, task, gate="answers"):
    """Rubric features as the tagger stores them: one value for each item
    asked of the task, none for the others."""
    out = {"status": "ok"}
    for item in rubric.items_for(task, "L0"):
        out[item.id] = [item.option_ids[0]] if item.multi else item.option_ids[0]
    out[rubric.gate_item] = gate
    if gate in rubric.gate_no_solution:
        out = {"status": "ok", rubric.gate_item: gate}
    return out


def record(kind, task, run_index, text, gate="answers", tagger=TAGGER, tagged=True):
    files = [InputFile(f.path, f.content.encode()) for f in extract_files(text)]
    made = build_record(
        project_type=kind, task_id=task, prompt_text="p", provider="example",
        model_id="m1", status="ok", level="L0", wording="A", run_index=run_index,
        prompt_set_version="1", batch_id="b1", raw_response=text,
        settings={}, timestamp=f"2026-12-01T00:00:{run_index:02d}Z",
        record_id=str(uuid.uuid5(uuid.NAMESPACE_URL,
                                 f"{kind}-{task}-{run_index}-{tagger}")))
    inputs = Inputs(files, record=made)
    for name, (version, values) in run_extractors(extractors_for(kind), inputs).items():
        made = with_features(made, name, version, values)
    if tagged:
        rubric = load_checked(kind)
        made = with_features(made, rubric.extractor, f"{rubric.version}@{tagger}",
                             tags(rubric, task, gate))
    return made


def reply_text(kind):
    return (FIXTURES / kind / FIXTURE[kind] / "response.md").read_text(encoding="utf-8")


def test_records_are_read_and_tabulated(kind, spec):
    text = reply_text(kind)
    records = [record(kind, task, run, text)
               for task in TASKS[kind] for run in (1, 2)]
    selection = select(records, spec, ["b1"])
    assert [run.outcome for run in selection.runs] == ["artifact"] * 6
    result = tables.compute(selection, spec)
    assert result["models"]["m1"]["levels"]["L0"]["fingerprint"]["outcomes"]["N"] == 6


def test_an_item_not_asked_is_not_applicable(kind, spec):
    rubric = load_checked(kind)
    task = TASKS[kind][0]
    asked = {i.id for i in rubric.items_for(task, "L0")}
    run = select([record(kind, task, 1, reply_text(kind))], spec, ["b1"]).runs[0]
    for item in rubric.items:
        value = run.values[f"{rubric.extractor}.{item.id}"]
        if item.id not in asked:
            assert value is NA, item.id
        else:
            assert value is not NA and value is not UND, item.id


def test_the_gate_decides_the_outcome(kind, spec):
    task = TASKS[kind][0]
    prose = "Which one do you mean?"
    cases = [("asks-first", reply_text(kind), "no-artifact"),
             ("declines", prose, "no-artifact"),
             (None, reply_text(kind), "unread"),
             ("answers", prose,
              "no-artifact" if kind == "pipeline" else "artifact"),
             ("answers-and-asks", reply_text(kind), "artifact")]
    for gate, text, outcome in cases:
        made = record(kind, task, 1, text, gate=gate)
        assert select([made], spec, ["b1"]).runs[0].outcome == outcome, (gate, outcome)


def test_a_failed_tagging_is_unread(kind, spec):
    made = record(kind, TASKS[kind][0], 1, reply_text(kind))
    rubric = load_checked(kind)
    made = with_features(made, rubric.extractor, f"1@{TAGGER}",
                         {"status": "error", "error": "no usable reply"})
    assert select([made], spec, ["b1"]).runs[0].outcome == "unread"


def test_untagged_records_and_mixed_taggers_are_refused(kind, spec):
    task, text = TASKS[kind][0], reply_text(kind)
    with pytest.raises(Refused, match="has not run"):
        select([record(kind, task, 1, text, tagged=False)], spec, ["b1"])
    with pytest.raises(Refused, match="never mixed"):
        select([record(kind, task, 1, text),
                record(kind, task, 2, text, tagger="other-model")], spec, ["b1"])
    old = record(kind, task, 1, text)
    old = with_features(old, f"rubric.{kind}", f"2@{TAGGER}", {"status": "ok"})
    with pytest.raises(Refused, match="version"):
        select([old], spec, ["b1"])
