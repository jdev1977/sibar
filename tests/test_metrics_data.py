"""The data files the metrics read (T1.5): analysis/website/features.yaml and
dictated.yaml agree with the extractors, the prompts and each other.

These tests check the declarations only. The metrics themselves are T1.6.
"""

import json
from pathlib import Path

import pytest
import yaml

from extractors.base import Inputs, run_extractors
from extractors.registry import extractors_for
from runner.prompts import load_prompts

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis" / "website"
FIXTURES = ROOT / "tests" / "fixtures" / "website"
# Pages that between them give every feature a value of its usual type.
PAGES = ("tailwind-landing", "plain-css", "react-spa", "bootstrap", "negative")

TYPES = {"categorical", "boolean", "number", "set", "ordered-list", "count-map"}
ROLES = {"primary", "provisional", "secondary", "diagnostic"}
WHYS = {"raw", "redundant", "detail", "heuristic", "thin-rules", "health"}
SINGLE = {"categorical", "boolean", "number", "coverage"}
MULTI = {"set", "ordered-list", "count-map"}
JSON_TYPES = {"categorical": str, "boolean": bool, "number": int, "set": list,
              "ordered-list": list, "count-map": dict}
LEVELS = ("L0", "L1", "L2")
REASONS = {"direction", "content", "constraint"}


def load(name):
    return yaml.safe_load((ANALYSIS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def features():
    return load("features.yaml")


@pytest.fixture(scope="module")
def dictated():
    return load("dictated.yaml")


@pytest.fixture(scope="module")
def extracted():
    """``{page: {extractor: values}}`` for the pages in PAGES."""
    website = extractors_for("website")
    return {page: {name: values for name, (_, values) in run_extractors(
        website, Inputs.from_directory(FIXTURES / page)).items()} for page in PAGES}


@pytest.fixture(scope="module")
def prompts():
    return {task.task_id: task for task in load_prompts([ROOT / "prompts" / "website"])}


def variables(features):
    """``{<extractor>.<name>: declaration}`` for features and derived variables."""
    out = {}
    for section in ("features", "derived"):
        for extractor, entries in features[section].items():
            for name, entry in entries.items():
                assert f"{extractor}.{name}" not in out, f"{extractor}.{name} twice"
                out[f"{extractor}.{name}"] = entry
    return out


def resolve(pattern, known):
    """The variables a name or ``<extractor>.*`` pattern stands for."""
    if pattern.endswith(".*"):
        return [name for name in known if name.rsplit(".", 1)[0] == pattern[:-2]]
    return [pattern] if pattern in known else []


def bin_labels(edges):
    labels = []
    for index, low in enumerate(edges):
        if index + 1 == len(edges):
            labels.append(f"{low}+")
        else:
            high = edges[index + 1] - 1
            labels.append(str(low) if low == high else f"{low}-{high}")
    return labels


# --- features.yaml -----------------------------------------------------------


def test_extractors_and_versions_match_the_registry(features):
    registry = {e.name: e.version for e in extractors_for("website")}
    assert features["project_type"] == "website"
    assert features["extractor_versions"] == registry
    assert set(features["features"]) == set(registry)
    assert set(features["dimensions"]) == set(registry)
    assert set(features["derived"]) <= set(registry)


def test_every_extracted_feature_is_declared_and_nothing_else(features, extracted):
    common = set(features["common"])
    for extractor, declared in features["features"].items():
        seen = set()
        for page in PAGES:
            seen |= set(extracted[page][extractor])
        assert seen - common == set(declared), extractor


def test_declared_types_match_the_extracted_values(features, extracted):
    for extractor, declared in features["features"].items():
        for name, entry in declared.items():
            expected = JSON_TYPES[entry["type"]]
            for page in PAGES:
                value = extracted[page][extractor].get(name)
                if value is None:
                    continue
                assert isinstance(value, expected), (extractor, name, value)
                if entry["type"] != "boolean":
                    assert not isinstance(value, bool), (extractor, name)
                if entry["type"] == "number":
                    assert value >= entry["bins"][0], (extractor, name, value)


def test_declarations_are_well_formed(features):
    for full, entry in variables(features).items():
        extractor = full.rsplit(".", 1)[0]
        names = set(features["features"][extractor]) | set(
            features["derived"].get(extractor, {}))
        assert entry["role"] in ROLES, full
        if entry["type"] == "coverage":
            for part in ("part", "whole"):
                assert features["features"][extractor][entry[part]]["type"] == "number"
            continue
        assert entry["type"] in TYPES, full
        assert (entry["role"] == "primary") == ("why" not in entry), full
        if "why" in entry:
            assert entry["why"] in WHYS, full
            assert (entry["role"] == "diagnostic") == (entry["why"] == "health"), full
        if "see" in entry:
            assert entry["see"] in names and entry["see"] != full.rsplit(".", 1)[1], full
        if entry["type"] == "number":
            bins = entry["bins"]
            assert bins[0] == 0 and bins == sorted(set(bins)) and len(bins) >= 2, full
            assert all(isinstance(edge, int) for edge in bins), full
        else:
            assert "bins" not in entry, full
        if "empty" in entry:
            assert entry["type"] in MULTI and entry["empty"] in ("value", "not-applicable")
        if "not_applicable" in entry:
            assert entry["type"] == "categorical", full
        assert ("min_count" in entry) == (entry["type"] == "count-map"), full
        if "min_count" in entry:
            assert all(isinstance(n, int) and n >= 1 for n in entry["min_count"].values())
            assert "default" in entry["min_count"], full
    for name, entry in features["common"].items():
        assert entry["role"] == "diagnostic", name


def test_call_to_action_rules_named_in_min_count_exist(features):
    rules = json.loads((ROOT / "extractors" / "website" /
                        "stock_phrases.json").read_text(encoding="utf-8"))
    rule_ids = {rule["id"] for rule in rules["rules"]}
    minimum = features["features"]["website.stock-phrases"]["stock_phrase_counts"]["min_count"]
    assert set(minimum) - {"default"} <= rule_ids
    assert {rule for rule in rule_ids if rule.startswith("cta-")} == set(minimum) - {"default"}


def test_variable_counts_behind_the_stability_simulation(features):
    """docs/metrics.md checks the stability rule by simulation with 45
    one-value variables and 17 set variables. If these counts change, redo the
    simulation and update the document."""
    primary = [entry for entry in variables(features).values() if entry["role"] == "primary"]
    assert sum(entry["type"] in SINGLE for entry in primary) == 45
    assert sum(entry["type"] in MULTI for entry in primary) == 17
    provisional = [e for e in variables(features).values() if e["role"] == "provisional"]
    assert len(provisional) == 6
    # every dimension has at least one primary variable to summarise
    for extractor in features["features"]:
        assert any(entry["role"] == "primary" for full, entry in variables(features).items()
                   if full.rsplit(".", 1)[0] == extractor), extractor


def test_masks_name_declared_variables(features):
    known = variables(features)
    for mask in features["masks"]:
        when = mask["when"]
        assert known[when["variable"]]["type"] == "categorical"
        assert ("in" in when) != ("not_in" in when)
        for pattern in mask["undetermined"]:
            hit = resolve(pattern, known)
            assert hit, pattern
            assert when["variable"] not in hit, "a mask may not hide its own condition"


# --- dictated.yaml -------------------------------------------------------------


def entries(dictated):
    for task, body in dictated["tasks"].items():
        for level in LEVELS:
            for entry in body.get(level, []):
                yield task, level, entry


def quotes(entry):
    quote = entry["quote"]
    return [quote] if isinstance(quote, str) else quote


def test_tasks_and_versions_match_the_prompts(dictated, prompts):
    assert dictated["project_type"] == "website"
    assert set(dictated["tasks"]) == set(prompts)
    for task, body in dictated["tasks"].items():
        assert body["prompt_set_version"] == prompts[task].prompt_set_version, task
        assert set(body) <= {"prompt_set_version", "associations", *LEVELS}, task


def test_l0_and_l1_close_nothing(dictated):
    """L0 and L1 give no direction (docs/leak-check.md); content that may
    pull a choice is an association, not a closed variable."""
    assert all(level == "L2" for _, level, _ in entries(dictated))
    assert all("L2" in body for body in dictated["tasks"].values())


def test_every_quote_is_in_wording_a(dictated, prompts):
    for task, level, entry in entries(dictated):
        for quote in quotes(entry):
            assert quote in prompts[task].text(level, "A"), (task, level, quote)
    for task, body in dictated["tasks"].items():
        for level, notes in body.get("associations", {}).items():
            assert level in LEVELS
            for note in notes:
                for quote in quotes(note):
                    assert quote in prompts[task].text(level, "A"), (task, level, quote)


def test_closed_and_associated_variables_are_declared(dictated, features):
    known = variables(features)
    for task, level, entry in entries(dictated):
        assert entry["reason"] in REASONS, (task, entry)
        assert set(entry) <= {"closed", "reason", "quote", "expect", "note"}
        for pattern in entry["closed"]:
            assert resolve(pattern, known), (task, pattern)
    for task, body in dictated["tasks"].items():
        for notes in body.get("associations", {}).values():
            for note in notes:
                assert set(note) == {"variables", "quote", "note"}
                for pattern in note["variables"]:
                    assert resolve(pattern, known), (task, pattern)


def test_an_association_is_not_also_closed(dictated, features):
    known = variables(features)
    for task, body in dictated["tasks"].items():
        for level, notes in body.get("associations", {}).items():
            closed = {name for entry in body.get(level, [])
                      for pattern in entry["closed"] for name in resolve(pattern, known)}
            for note in notes:
                for pattern in note["variables"]:
                    assert not closed & set(resolve(pattern, known)), (task, level, pattern)


def test_expected_values_fit_the_variable(dictated, features):
    known = variables(features)
    for task, level, entry in entries(dictated):
        closed = {name for pattern in entry["closed"] for name in resolve(pattern, known)}
        for name, expect in entry.get("expect", {}).items():
            assert name in closed, (task, name, "expected but not closed by this entry")
            declared = known[name]
            assert declared["role"] != "diagnostic", name
            if declared["type"] in SINGLE:
                assert set(expect) == {"in"} and expect["in"], (task, name)
                assert all(isinstance(value, str) for value in expect["in"]), (task, name)
                if declared["type"] == "number":
                    assert set(expect["in"]) <= set(bin_labels(declared["bins"])), (task, name)
                if declared["type"] == "boolean":
                    assert set(expect["in"]) <= {"true", "false"}, (task, name)
            else:
                assert declared["type"] == "set", (task, name)
                assert expect and set(expect) <= {"absent", "present"}, (task, name)


def test_no_variable_has_two_expectations_in_one_cell(dictated, features):
    for task, body in dictated["tasks"].items():
        for level in LEVELS:
            seen = set()
            for entry in body.get(level, []):
                for name in entry.get("expect", {}):
                    assert name not in seen, (task, level, name)
                    seen.add(name)


def test_bin_labels():
    assert bin_labels([0, 1, 3, 6]) == ["0", "1-2", "3-5", "6+"]
    assert bin_labels([0, 5000, 15000, 40000]) == ["0-4999", "5000-14999",
                                                   "15000-39999", "40000+"]
    assert bin_labels([0, 1]) == ["0", "1+"]
