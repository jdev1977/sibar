"""Load and validate the list of models under test (models.yaml, task T0.2).

A value that could not be confirmed from an official page is ``null`` in the
file and has an entry under the model's ``notes`` that says why.
"""

import datetime
import math
import re
from collections.abc import Hashable
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

import yaml

SCHEMA_VERSION = 1
TIERS = ("main", "small")
PILOT_SIZE = 3


class ModelsError(ValueError):
    """The model list is unreadable or breaks a rule."""


@dataclass(frozen=True)
class Defaults:
    """What a call with no system prompt and no parameters gets."""

    temperature: Optional[float]
    thinking_on_by_default: Optional[bool]
    default_effort: Optional[str]
    max_output_tokens: Optional[int]  # the most the model can be asked for
    default_max_tokens: Optional[int]  # the limit applied when none is sent
    max_tokens_required: Optional[bool]


@dataclass(frozen=True)
class PriceTier:
    """Rates for a whole call whose prompt is longer than the threshold."""

    above_input_tokens: int
    input_price_per_mtok_usd: float
    output_price_per_mtok_usd: float


@dataclass(frozen=True)
class Model:
    id: str
    provider: str
    tier: str
    display_name: str
    input_price_per_mtok_usd: Optional[float]
    output_price_per_mtok_usd: Optional[float]
    defaults: Defaults
    retirement_date: Optional[datetime.date]  # an announced date
    retirement_not_before: Optional[datetime.date]  # a promised earliest date
    api_key_env: str
    sources: Tuple[str, ...]
    date_checked: datetime.date
    notes: Mapping[str, str]
    price_tiers: Tuple[PriceTier, ...] = ()  # ascending by threshold


@dataclass(frozen=True)
class ModelList:
    schema_version: int
    confirmed_by_human: bool
    pilot: Tuple[str, ...]
    models: Tuple[Model, ...]

    def get(self, model_id):
        for model in self.models:
            if model.id == model_id:
                return model
        raise KeyError(model_id)


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a repeated key instead of keeping the last."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, Hashable):
                raise ModelsError(
                    f"unusable key on line {key_node.start_mark.line + 1}"
                )
            if key in seen:
                raise ModelsError(
                    f"repeated key {key!r} on line {key_node.start_mark.line + 1}"
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_number(value):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0)


def _is_count(value):
    return type(value) is int and value > 0


def _is_flag(value):
    return type(value) is bool


def _date(value):
    """A date from a YAML date or a YYYY-MM-DD string, else None."""
    if type(value) is datetime.date:
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None
    return None


# Nullable fields, each with the test a non-null value must pass.
_NULLABLE_DEFAULTS = {
    "temperature": _is_number,
    "thinking_on_by_default": _is_flag,
    "default_effort": _is_text,
    "max_output_tokens": _is_count,
    "default_max_tokens": _is_count,
    "max_tokens_required": _is_flag,
}
_PRICES = ("input_price_per_mtok_usd", "output_price_per_mtok_usd")
_RETIREMENT = ("retirement_date", "retirement_not_before")


def _check_keys(mapping, where, required, optional=()):
    if not isinstance(mapping, dict):
        raise ModelsError(f"{where}: must be a mapping")
    for key in required:
        if key not in mapping:
            raise ModelsError(f"{where}: missing {key}")
    for key in mapping:
        if key not in required and key not in optional:
            raise ModelsError(f"{where}: unknown key {key!r}")


def _require(ok, where, key, expected):
    if not ok:
        raise ModelsError(f"{where}: {key} must be {expected}")


def _require_note(notes, where, key):
    if key not in notes:
        raise ModelsError(f"{where}: null value needs a note under notes.{key}")


def _price_tiers(raw, where, base):
    """The tiers in ascending order; no tier is cheaper than the one below."""
    _require(isinstance(raw, list) and raw, where, "price_tiers",
             "a non-empty list, or left out")
    _require(all(base[key] is not None for key in _PRICES), where,
             "price_tiers", "left out when a base price is null")
    below = {"above_input_tokens": 0, **base}
    tiers = []
    for index, entry in enumerate(raw):
        at = f"{where}: price_tiers[{index}]"
        _check_keys(entry, at, tuple(f.name for f in fields(PriceTier)))
        threshold = entry["above_input_tokens"]
        _require(
            _is_count(threshold) and threshold > below["above_input_tokens"],
            at, "above_input_tokens",
            "a whole number above 0 and above the tier before",
        )
        for key in _PRICES:
            _require(
                _is_number(entry[key]) and entry[key] >= below[key],
                at, key, "a number no lower than the price below this tier",
            )
        below = entry
        tiers.append(PriceTier(**entry))
    return tuple(tiers)


def _model(raw, index):
    where = f"models[{index}]"
    names = tuple(field.name for field in fields(Model))
    optional = ("notes", "price_tiers")
    required = tuple(name for name in names if name not in optional)
    _check_keys(raw, where, required, optional=optional)

    for key in ("id", "provider", "display_name"):
        _require(_is_text(raw[key]), where, key, "non-empty text")
    where = f"model {raw['id']!r}"

    _require(raw["tier"] in TIERS, where, "tier", "one of " + ", ".join(TIERS))

    env = raw["api_key_env"]
    _require(
        isinstance(env, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", env),
        where, "api_key_env", "an environment variable name",
    )

    sources = raw["sources"]
    _require(
        isinstance(sources, list) and sources and all(
            isinstance(url, str) and re.fullmatch(r"https://[^\s/]+\.\S+", url)
            for url in sources
        ),
        where, "sources", "a non-empty list of https links",
    )

    checked = _date(raw["date_checked"])
    _require(checked is not None, where, "date_checked", "a YYYY-MM-DD date")

    notes = raw.get("notes", {})
    _require(
        isinstance(notes, dict)
        and all(_is_text(k) and _is_text(v) for k, v in notes.items()),
        where, "notes", "a mapping of field name to non-empty text",
    )

    values = {}
    for key in _PRICES:
        value = raw[key]
        if value is None:
            _require_note(notes, where, key)
        else:
            _require(_is_number(value), where, key, "a number of at least 0")
        values[key] = value

    if "price_tiers" in raw:
        values["price_tiers"] = _price_tiers(
            raw["price_tiers"], where, {key: raw[key] for key in _PRICES})

    for key in _RETIREMENT:
        value = raw[key]
        if value is None:
            _require_note(notes, where, key)
        else:
            value = _date(value)
            _require(value is not None, where, key, "a YYYY-MM-DD date or null")
        values[key] = value

    defaults = raw["defaults"]
    _check_keys(defaults, f"{where}: defaults", tuple(_NULLABLE_DEFAULTS))
    for key, valid in _NULLABLE_DEFAULTS.items():
        value = defaults[key]
        if value is None:
            _require_note(notes, where, key)
        else:
            _require(valid(value), where, key, "of the right type, or null")

    return Model(
        id=raw["id"],
        provider=raw["provider"],
        tier=raw["tier"],
        display_name=raw["display_name"],
        defaults=Defaults(**defaults),
        api_key_env=env,
        sources=tuple(sources),
        date_checked=checked,
        notes=MappingProxyType(dict(notes)),
        **values,
    )


def _model_list(raw):
    _check_keys(raw, "top level", tuple(f.name for f in fields(ModelList)))

    version = raw["schema_version"]
    _require(
        type(version) is int and version == SCHEMA_VERSION,
        "top level", "schema_version", str(SCHEMA_VERSION),
    )
    _require(
        _is_flag(raw["confirmed_by_human"]),
        "top level", "confirmed_by_human", "true or false",
    )

    entries = raw["models"]
    _require(
        isinstance(entries, list) and entries,
        "top level", "models", "a non-empty list",
    )
    models = tuple(_model(entry, index) for index, entry in enumerate(entries))

    ids = set()
    for model in models:
        if model.id in ids:
            raise ModelsError(f"duplicate model id {model.id!r}")
        ids.add(model.id)

    pilot = raw["pilot"]
    _require(
        isinstance(pilot, list)
        and len(pilot) == PILOT_SIZE
        and all(isinstance(item, str) for item in pilot)
        and len(set(pilot)) == PILOT_SIZE,
        "top level", "pilot", f"a list of {PILOT_SIZE} different model ids",
    )
    for model_id in pilot:
        if model_id not in ids:
            raise ModelsError(f"pilot names an unknown model id {model_id!r}")

    return ModelList(
        schema_version=version,
        confirmed_by_human=raw["confirmed_by_human"],
        pilot=tuple(pilot),
        models=models,
    )


def load_models(path):
    """Read a model list file and return it as a :class:`ModelList`.

    Raises :class:`ModelsError` if the file is not valid YAML or breaks a rule,
    and :class:`OSError` if it cannot be read.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
        return _model_list(yaml.load(text, Loader=_UniqueKeyLoader))
    except (ModelsError, yaml.YAMLError, ValueError) as error:
        raise ModelsError(f"{path.name}: {error}") from error
