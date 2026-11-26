"""The model list from task T0.2 and its validator."""

import copy
import datetime
import re
from pathlib import Path

import pytest
import yaml

from runner.models import ModelsError, load_models

ROOT = Path(__file__).resolve().parents[1]
DAY = datetime.date(2030, 1, 2)


def model(model_id, tier="main"):
    return {
        "id": model_id,
        "provider": "example",
        "tier": tier,
        "display_name": "Example " + model_id,
        "input_price_per_mtok_usd": 1.5,
        "output_price_per_mtok_usd": 7,
        "defaults": {
            "temperature": 1.0,
            "thinking_on_by_default": True,
            "default_effort": "medium",
            "max_output_tokens": 1000,
            "default_max_tokens": 500,
            "max_tokens_required": False,
        },
        "retirement_date": None,
        "retirement_not_before": "2031-01-01",
        "api_key_env": "EXAMPLE_API_KEY",
        "sources": ["https://example.com/models"],
        "date_checked": DAY,
        "notes": {"retirement_date": "no date announced"},
    }


def document():
    return {
        "schema_version": 1,
        "confirmed_by_human": False,
        "pilot": ["a", "b", "c"],
        "models": [model("a"), model("b", "small"), model("c")],
    }


def load(tmp_path, data):
    path = tmp_path / "models.yaml"
    text = data if isinstance(data, str) else yaml.safe_dump(data)
    path.write_text(text, encoding="utf-8")
    return load_models(path)


def rejects(tmp_path, data, match):
    with pytest.raises(ModelsError, match=match):
        load(tmp_path, data)


def test_returns_typed_objects(tmp_path):
    result = load(tmp_path, document())

    assert result.schema_version == 1
    assert result.confirmed_by_human is False
    assert result.pilot == ("a", "b", "c")
    assert [m.id for m in result.models] == ["a", "b", "c"]
    first = result.get("a")
    assert first is result.models[0]
    assert first.tier == "main"
    assert first.input_price_per_mtok_usd == 1.5
    assert first.output_price_per_mtok_usd == 7
    assert first.defaults.max_tokens_required is False
    assert first.defaults.default_max_tokens == 500
    assert first.retirement_date is None
    assert first.retirement_not_before == datetime.date(2031, 1, 1)
    assert first.date_checked == DAY
    assert first.sources == ("https://example.com/models",)
    assert first.notes["retirement_date"] == "no date announced"


def test_get_rejects_an_unknown_id(tmp_path):
    with pytest.raises(KeyError):
        load(tmp_path, document()).get("zzz")


@pytest.mark.parametrize("value", [None, [], "https://example.com", [""], ["example.com"], [5]])
def test_rejects_a_missing_or_bad_source_link(tmp_path, value):
    data = document()
    data["models"][0]["sources"] = value
    rejects(tmp_path, data, "sources")


@pytest.mark.parametrize("value", [None, "", "yesterday", "2030-13-01", 20300102,
                                   datetime.datetime(2030, 1, 2, 3, 4)])
def test_rejects_a_missing_or_bad_check_date(tmp_path, value):
    data = document()
    data["models"][0]["date_checked"] = value
    rejects(tmp_path, data, "date_checked")


@pytest.mark.parametrize("key", sorted(model("a").keys() - {"notes"}))
def test_rejects_an_absent_model_key(tmp_path, key):
    data = document()
    del data["models"][0][key]
    rejects(tmp_path, data, key)


@pytest.mark.parametrize("key", sorted(model("a")["defaults"]))
def test_rejects_an_absent_default(tmp_path, key):
    data = document()
    del data["models"][0]["defaults"][key]
    rejects(tmp_path, data, key)


@pytest.mark.parametrize("key", sorted(document()))
def test_rejects_an_absent_top_level_key(tmp_path, key):
    data = document()
    del data[key]
    rejects(tmp_path, data, key)


@pytest.mark.parametrize("where", ["top", "model", "defaults"])
def test_rejects_an_unknown_key(tmp_path, where):
    data = document()
    target = {"top": data, "model": data["models"][0],
              "defaults": data["models"][0]["defaults"]}[where]
    target["temprature"] = 1
    rejects(tmp_path, data, "temprature")


def test_rejects_duplicate_model_ids(tmp_path):
    data = document()
    data["models"].append(copy.deepcopy(data["models"][0]))
    rejects(tmp_path, data, "duplicate model id 'a'")


def test_rejects_an_unknown_tier(tmp_path):
    data = document()
    data["models"][0]["tier"] = "medium"
    rejects(tmp_path, data, "tier")


def test_rejects_an_unknown_pilot_id(tmp_path):
    data = document()
    data["pilot"] = ["a", "b", "nope"]
    rejects(tmp_path, data, "nope")


@pytest.mark.parametrize("pilot", [["a", "b"], ["a", "a", "b"], "abc", None])
def test_rejects_a_pilot_that_is_not_three_different_models(tmp_path, pilot):
    data = document()
    data["pilot"] = pilot
    rejects(tmp_path, data, "pilot")


NULLABLE = [
    ("input_price_per_mtok_usd", False),
    ("output_price_per_mtok_usd", False),
    ("retirement_not_before", False),
    ("temperature", True),
    ("thinking_on_by_default", True),
    ("default_effort", True),
    ("max_output_tokens", True),
    ("default_max_tokens", True),
    ("max_tokens_required", True),
]


@pytest.mark.parametrize("key,in_defaults", NULLABLE)
def test_null_needs_a_note(tmp_path, key, in_defaults):
    data = document()
    target = data["models"][0]["defaults"] if in_defaults else data["models"][0]
    target[key] = None
    rejects(tmp_path, data, "note.*" + key)

    data["models"][0]["notes"][key] = "could not be verified"
    load(tmp_path, data)


def test_null_retirement_date_needs_a_note(tmp_path):
    data = document()
    del data["models"][0]["notes"]
    rejects(tmp_path, data, "note.*retirement_date")


@pytest.mark.parametrize("value", [None, "", "  "])
def test_rejects_an_empty_note(tmp_path, value):
    data = document()
    data["models"][0]["notes"]["retirement_date"] = value
    rejects(tmp_path, data, "notes")


@pytest.mark.parametrize("key,value", [
    ("id", ""),
    ("id", None),
    ("provider", 3),
    ("display_name", None),
    ("input_price_per_mtok_usd", "$1"),
    ("input_price_per_mtok_usd", -1),
    ("output_price_per_mtok_usd", True),
    ("output_price_per_mtok_usd", float("nan")),
    ("retirement_date", "soon"),
    ("api_key_env", None),
    ("api_key_env", "sk-lowercase"),
    ("defaults", None),
])
def test_rejects_a_bad_model_value(tmp_path, key, value):
    data = document()
    data["models"][0][key] = value
    rejects(tmp_path, data, key)


@pytest.mark.parametrize("key,value", [
    ("temperature", "1"),
    ("thinking_on_by_default", "yes"),
    ("default_effort", 2),
    ("max_output_tokens", "128K"),
    ("max_output_tokens", 0),
    ("default_max_tokens", 1.5),
    ("max_tokens_required", 1),
])
def test_rejects_a_bad_default(tmp_path, key, value):
    data = document()
    data["models"][0]["defaults"][key] = value
    rejects(tmp_path, data, key)


@pytest.mark.parametrize("key,value", [
    ("schema_version", 2),
    ("schema_version", True),
    ("confirmed_by_human", "no"),
    ("models", []),
    ("models", None),
])
def test_rejects_a_bad_top_level_value(tmp_path, key, value):
    data = document()
    data[key] = value
    rejects(tmp_path, data, key)


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "a: [unclosed\n"])
def test_rejects_a_file_that_is_not_a_model_list(tmp_path, text):
    rejects(tmp_path, text, "models.yaml")


def test_rejects_a_repeated_yaml_key(tmp_path):
    text = yaml.safe_dump(document()) + "confirmed_by_human: true\n"
    rejects(tmp_path, text, "repeated key 'confirmed_by_human'")


def test_rejects_a_key_that_is_a_list(tmp_path):
    rejects(tmp_path, "? [a, b]\n: 1\n", "models.yaml")


def test_rejects_a_file_that_is_not_utf_8(tmp_path):
    path = tmp_path / "models.yaml"
    path.write_bytes(bytes([255, 254, 0]))
    with pytest.raises(ModelsError, match="models.yaml"):
        load_models(path)


# The committed list.

@pytest.fixture(scope="module")
def committed():
    return load_models(ROOT / "models.yaml")


def test_committed_list_has_a_main_and_a_small_model_per_provider(committed):
    pairs = sorted((m.provider, m.tier) for m in committed.models)
    providers = sorted({m.provider for m in committed.models})

    assert {"anthropic", "openai", "google"} <= set(providers)
    assert len(providers) == 4
    assert pairs == sorted((p, t) for p in providers for t in ("main", "small"))


def test_committed_key_names_are_in_env_example(committed):
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    names = set(re.findall(r"^([A-Z0-9_]+)=", text, re.MULTILINE))

    assert {m.api_key_env for m in committed.models} <= names


def test_pyyaml_is_pinned():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert re.search(r"^PyYAML==\d+\.\d+\.\d+$", text, re.MULTILINE)


# Price tiers above a prompt-size threshold.

def tier(above, input_price=3, output_price=14):
    return {
        "above_input_tokens": above,
        "input_price_per_mtok_usd": input_price,
        "output_price_per_mtok_usd": output_price,
    }


def test_price_tiers_default_to_none(tmp_path):
    assert load(tmp_path, document()).get("a").price_tiers == ()


def test_price_tiers_are_typed(tmp_path):
    data = document()
    data["models"][0]["price_tiers"] = [tier(1000), tier(2000, 4, 15)]

    first, second = load(tmp_path, data).get("a").price_tiers

    assert (first.above_input_tokens, first.input_price_per_mtok_usd,
            first.output_price_per_mtok_usd) == (1000, 3, 14)
    assert second.above_input_tokens == 2000


@pytest.mark.parametrize("tiers", [
    None, [], {}, "above 100K", [5],
    [tier(0)], [tier(-1)], [tier(1.5)], [tier("100K")], [tier(True)],
    [tier(1000, None)], [tier(1000, 3, None)], [tier(1000, "3")],
    [tier(1000, 3, float("inf"))],
    [{"above_input_tokens": 1000, "input_price_per_mtok_usd": 3}],
    [dict(tier(1000), extra=1)],
    [tier(2000), tier(1000)], [tier(1000), tier(1000)],
    # a longer prompt is never cheaper
    [tier(1000, 1.4, 14)], [tier(1000, 3, 6)],
    [tier(1000), tier(2000, 2, 15)],
])
def test_rejects_bad_price_tiers(tmp_path, tiers):
    data = document()
    data["models"][0]["price_tiers"] = tiers
    rejects(tmp_path, data, "price_tiers")


@pytest.mark.parametrize("key", ["input_price_per_mtok_usd",
                                 "output_price_per_mtok_usd"])
def test_rejects_price_tiers_without_a_base_price(tmp_path, key):
    data = document()
    data["models"][0][key] = None
    data["models"][0]["notes"][key] = "could not be verified"
    data["models"][0]["price_tiers"] = [tier(1000)]
    rejects(tmp_path, data, "price_tiers")


def test_committed_price_tiers_match_the_notes(committed):
    tiers = {
        m.id: [(t.above_input_tokens, t.input_price_per_mtok_usd,
                t.output_price_per_mtok_usd) for t in m.price_tiers]
        for m in committed.models if m.price_tiers
    }

    assert tiers == {
        "claude-haiku-5-5": [(100000, 0.50, 2.50)],
        "gpt-6.2-sol": [(272000, 4.00, 15.00)],
        "gpt-6-luna": [(272000, 0.20, 0.75)],
    }
