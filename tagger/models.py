"""The tagging models: ``tagger/taggers.yaml``, read and checked (T2.6).

A tagger that is also a model under test takes its prices from models.yaml;
one that is not (Claude Sonnet 5.5) gives them in taggers.yaml. Either way it
becomes a ``runner.models.Model``, so the ledger prices tagging requests with
the code that prices generation requests. The models-under-test list is not
changed: :func:`ledger_models` returns it with the tagger-only models added,
for the ledger only.
"""

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Tuple

import yaml

from runner.models import Defaults, Model, ModelList, ModelsError, load_models

ROOT = Path(__file__).resolve().parents[1]
TAGGERS_PATH = Path(__file__).resolve().with_name("taggers.yaml")
MODELS_PATH = ROOT / "models.yaml"
SCHEMA_VERSION = 1
PROVIDERS = ("anthropic", "openai")  # the providers tagger/backends.py speaks
TIER = "tagger"  # the tier of a tagger-only Model (not a model under test)

_TOP = {"schema_version", "confirmed_by_human", "max_tokens", "batch_discount",
        "taggers"}
_TAGGER = {"id", "provider"}
_TAGGER_OPTIONAL = {"model", "max_tokens"}
_MODEL = {"display_name", "input_price_per_mtok_usd", "output_price_per_mtok_usd",
          "max_output_tokens", "api_key_env", "sources", "date_checked"}
_DISCOUNT = {"factor", "source", "date_checked"}


class TaggersError(ValueError):
    """taggers.yaml is unreadable or breaks a rule."""


@dataclass(frozen=True)
class Tagger:
    id: str
    provider: str
    model: Model                 # prices and limits, as the ledger reads them
    max_tokens: int              # output limit sent with every request
    batch_discount: Decimal      # share of the standard rates a batch costs
    in_models_yaml: bool         # prices come from models.yaml


@dataclass(frozen=True)
class TaggerList:
    confirmed_by_human: bool
    taggers: Tuple[Tagger, ...]
    path: Path

    def get(self, tagger_id):
        for tagger in self.taggers:
            if tagger.id == tagger_id:
                return tagger
        known = ", ".join(t.id for t in self.taggers)
        raise TaggersError(f"{tagger_id!r} is not a tagger in {self.path.name} "
                           f"(taggers: {known})")


def _keys(raw, required, optional, at):
    if not isinstance(raw, dict):
        raise TaggersError(f"{at} must be a mapping")
    for key in required:
        if key not in raw:
            raise TaggersError(f"{at}: missing {key}")
    for key in raw:
        if key not in required and key not in optional:
            raise TaggersError(f"{at}: unknown key {key!r}")


def _date(value, at):
    if type(value) is datetime.date:
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise TaggersError(f"{at} must be a YYYY-MM-DD date") from None


def _count(value, at):
    if type(value) is not int or value < 1:
        raise TaggersError(f"{at} must be a whole number above 0")
    return value


def _price(value, at):
    if type(value) not in (int, float) or value < 0:
        raise TaggersError(f"{at} must be a number of at least 0")
    return value


def _own_model(tagger_id, provider, raw, at):
    _keys(raw, _MODEL, {"notes"}, at)
    env = raw["api_key_env"]
    if not isinstance(env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", env):
        raise TaggersError(f"{at}.api_key_env must be an environment variable name")
    sources = raw["sources"]
    if not isinstance(sources, list) or not sources or not all(
            isinstance(url, str) and url.startswith("https://") for url in sources):
        raise TaggersError(f"{at}.sources must be a non-empty list of https links")
    notes = raw.get("notes") or {}
    if not isinstance(notes, dict):
        raise TaggersError(f"{at}.notes must be a mapping")
    if not isinstance(raw["display_name"], str) or not raw["display_name"].strip():
        raise TaggersError(f"{at}.display_name must be text")
    return Model(
        id=tagger_id, provider=provider, tier=TIER,
        display_name=raw["display_name"],
        input_price_per_mtok_usd=_price(raw["input_price_per_mtok_usd"],
                                        f"{at}.input_price_per_mtok_usd"),
        output_price_per_mtok_usd=_price(raw["output_price_per_mtok_usd"],
                                         f"{at}.output_price_per_mtok_usd"),
        defaults=Defaults(None, None, None,
                          _count(raw["max_output_tokens"], f"{at}.max_output_tokens"),
                          None, True),
        retirement_date=None, retirement_not_before=None, api_key_env=env,
        sources=tuple(sources), date_checked=_date(raw["date_checked"],
                                                   f"{at}.date_checked"),
        notes=MappingProxyType({str(k): str(v) for k, v in notes.items()}))


def _discounts(raw):
    _keys(raw, set(), set(PROVIDERS), "batch_discount")
    out = {}
    for provider, entry in raw.items():
        at = f"batch_discount.{provider}"
        _keys(entry, _DISCOUNT, {"note"}, at)
        try:
            factor = Decimal(str(entry["factor"]))
        except InvalidOperation:
            raise TaggersError(f"{at}.factor must be a number") from None
        if not (factor.is_finite() and 0 < factor <= 1):
            raise TaggersError(f"{at}.factor must be above 0 and at most 1")
        _date(entry["date_checked"], f"{at}.date_checked")
        out[provider] = factor
    return out


def load_taggers(path=TAGGERS_PATH, models=None):
    """Read taggers.yaml; ``models`` is the models-under-test list (read
    from models.yaml if not given). Raises :class:`TaggersError`."""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        models = load_models(MODELS_PATH) if models is None else models
    except (OSError, yaml.YAMLError, ModelsError) as error:
        raise TaggersError(f"{path.name}: {error}") from None
    try:
        _keys(raw, _TOP, set(), "the file")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise TaggersError(f"schema_version must be {SCHEMA_VERSION}")
        if type(raw["confirmed_by_human"]) is not bool:
            raise TaggersError("confirmed_by_human must be true or false")
        default_tokens = _count(raw["max_tokens"], "max_tokens")
        discounts = _discounts(raw["batch_discount"])
        if not isinstance(raw["taggers"], list) or not raw["taggers"]:
            raise TaggersError("taggers must be a non-empty list")
        taggers = []
        for index, entry in enumerate(raw["taggers"]):
            at = f"taggers[{index}]"
            _keys(entry, _TAGGER, _TAGGER_OPTIONAL, at)
            tagger_id, provider = entry["id"], entry["provider"]
            if provider not in PROVIDERS:
                raise TaggersError(f"{at}.provider must be one of "
                                   f"{', '.join(PROVIDERS)} (the batch APIs "
                                   "tagger/backends.py speaks)")
            if provider not in discounts:
                raise TaggersError(f"{at}: batch_discount has no entry for {provider}")
            if any(t.id == tagger_id for t in taggers):
                raise TaggersError(f"{at}: {tagger_id!r} is listed twice")
            try:
                known = models.get(tagger_id)
            except KeyError:
                known = None
            if known is not None:
                if "model" in entry:
                    raise TaggersError(f"{at}: {tagger_id} is in models.yaml, which "
                                       "holds its prices; remove `model` here")
                if known.provider != provider:
                    raise TaggersError(f"{at}: models.yaml says {tagger_id} is a "
                                       f"{known.provider} model")
                model = known
            elif "model" in entry:
                model = _own_model(tagger_id, provider, entry["model"], f"{at}.model")
            else:
                raise TaggersError(f"{at}: {tagger_id} is not in models.yaml, so "
                                   "give its prices and limits under `model`")
            max_tokens = _count(entry.get("max_tokens", default_tokens),
                                f"{at}.max_tokens")
            limit = model.defaults.max_output_tokens
            if limit and max_tokens > limit:
                raise TaggersError(f"{at}: max_tokens {max_tokens} is above the "
                                   f"model's maximum output {limit}")
            taggers.append(Tagger(tagger_id, provider, model, max_tokens,
                                  discounts[provider], known is not None))
        return TaggerList(raw["confirmed_by_human"], tuple(taggers), path)
    except TaggersError as error:
        raise TaggersError(f"{path.name}: {error}") from None


def ledger_models(models, taggers):
    """``models`` (a ModelList) with the tagger-only models added: what the
    ledger needs to price tagging requests. Not a list of models under test."""
    extra = tuple(t.model for t in taggers.taggers if not t.in_models_yaml)
    return ModelList(models.schema_version, models.confirmed_by_human,
                     models.pilot, models.models + extra)


def with_max_tokens(tagger, max_tokens):
    """The tagger with another output limit (``--max-tokens``)."""
    limit = tagger.model.defaults.max_output_tokens
    if type(max_tokens) is not int or max_tokens < 1 or (limit and max_tokens > limit):
        raise TaggersError(f"max_tokens must be a whole number from 1 to {limit}")
    return Tagger(tagger.id, tagger.provider, tagger.model, max_tokens,
                  tagger.batch_discount, tagger.in_models_yaml)

