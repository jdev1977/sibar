"""Checking a tagger's answers against the rubric, and what is stored (T2.6).

A tagger's reply is checked strictly, item by item:

- the reply is one JSON object (no repeated keys) whose keys are exactly the
  item ids asked: a key that is not an item asked is an **extra item**, an
  item with no key a **missing item**;
- each value is ``{"evidence": text, "answer": ...}`` and nothing else;
- a single-select answer is one of the item's answer ids; ``not-applicable``
  only where the item allows it; ``none`` never;
- a multi-select answer is a non-empty list of distinct option ids, or one
  of ``none``, ``cannot-tell``, ``not-applicable`` (where allowed) alone.

Answer ids are compared exactly (they are lower case, without spaces).
Stored values follow docs/rubrics.md: single-select the option id or
``"not-applicable"``; multi-select the sorted list, ``["none"]`` or ``[]``;
``cannot-tell`` is ``null`` in both. ``Rubric.check_value`` checks each.

**What happens to a fault** (see ``tagger/README.md``): a reply with any fault
that matters (an extra or missing item, an unknown answer, a reply that is
not a JSON object, a refusal, a cut-off or failed request) is asked again
once, with the same request. The second reply is then used as it is: each
item it answers validly is stored; each item still at fault is stored as
``null`` (cannot tell), with ``status: partial`` and an ``error`` that names
the items. A second reply with no usable object stores ``status: error`` and
no item values. Faults in items after a gate that stops the tagging do not
matter and cause no retry.
"""

import json
from dataclasses import dataclass, field

from tagger.prompt import ERROR, STATUS
from tagger.rubric import CANNOT_TELL, NONE, NOT_APPLICABLE, RubricError

MAX_ATTEMPTS = 2  # the first request and one retry


@dataclass
class Parsed:
    """One reply, checked. ``values`` holds the valid items only."""

    values: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    problems: dict = field(default_factory=dict)   # item id (or "") -> text
    usable: bool = False                            # a JSON object was found


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"repeated key {key!r}")
        out[key] = value
    return out


def _single(item, answer):
    allowed = set(item.option_ids) | {CANNOT_TELL}
    if item.not_applicable is not None:
        allowed.add(NOT_APPLICABLE)
    if not isinstance(answer, str) or answer not in allowed:
        raise ValueError(f"{answer!r} is not one of {sorted(allowed)}")
    return None if answer == CANNOT_TELL else answer


def _multi(item, answer):
    if not isinstance(answer, list) or not answer or \
            not all(isinstance(x, str) for x in answer):
        raise ValueError("a multi-select answer is a non-empty list of answer ids")
    if len(set(answer)) != len(answer):
        raise ValueError(f"{answer!r} repeats an answer")
    reserved = {NONE, CANNOT_TELL, NOT_APPLICABLE} & set(answer)
    if reserved:
        if len(answer) != 1:
            raise ValueError(f"{sorted(reserved)[0]!r} must stand alone")
        if answer[0] == CANNOT_TELL:
            return None
        if answer[0] == NONE:
            return [NONE]
        if item.not_applicable is None:
            raise ValueError(f"{NOT_APPLICABLE!r} is not an answer of this item")
        return []
    unknown = [x for x in answer if x not in item.option_ids]
    if unknown:
        raise ValueError(f"{unknown} are not options")
    return sorted(answer)


def parse_reply(rubric, item_ids, text):
    """Check a reply's text against the items asked; return :class:`Parsed`."""
    parsed = Parsed()
    try:
        data = json.loads(text, object_pairs_hook=_unique)
    except (TypeError, ValueError) as error:
        parsed.problems[""] = f"not one JSON object: {error}"
        return parsed
    if not isinstance(data, dict):
        parsed.problems[""] = "the reply is not a JSON object"
        return parsed
    parsed.usable = True
    for key in data:
        if key not in item_ids:
            parsed.problems[""] = f"extra item {key!r}"
    for item_id in item_ids:
        item = rubric.item(item_id)
        entry = data.get(item_id)
        if item_id not in data:
            parsed.problems[item_id] = "missing item"
            continue
        if not isinstance(entry, dict) or set(entry) != {"evidence", "answer"} \
                or not isinstance(entry["evidence"], str):
            parsed.problems[item_id] = "an answer is {evidence: text, answer: ...}"
            continue
        try:
            value = (_multi if item.multi else _single)(item, entry["answer"])
            rubric.check_value(item_id, value)
        except (ValueError, RubricError) as error:
            parsed.problems[item_id] = str(error)
            continue
        parsed.values[item_id] = value
        parsed.evidence[item_id] = entry["evidence"]
    return parsed


def _stops(rubric, parsed):
    gate = rubric.gate_item
    if gate not in parsed.values:
        return True  # a gate without a valid answer is cannot tell: it stops
    return rubric.stops_at_gate(parsed.values[gate])


def needs_retry(rubric, parsed):
    """Whether a reply has a fault that matters (see the module text)."""
    if not parsed.usable or "" in parsed.problems:
        return True
    if rubric.gate_item in parsed.problems:
        return True
    return not _stops(rubric, parsed) and bool(parsed.problems)


def stored_features(rubric, item_ids, parsed, failure=None):
    """The feature values stored for an output after its last attempt.

    ``parsed`` is the last reply checked, or None when the last request
    produced no reply text (``failure`` says why).
    """
    if parsed is None or not parsed.usable:
        reason = (parsed.problems.get("") if parsed else None) or failure \
            or "no answer"
        return {STATUS: "error", ERROR: f"no usable answer after retry: {reason}"}
    gate = rubric.gate_item
    values = {gate: parsed.values.get(gate)}
    faulty = [gate] if gate in parsed.problems else []
    if not rubric.stops_at_gate(values[gate]):
        for item_id in item_ids:
            if item_id == gate:
                continue
            values[item_id] = parsed.values.get(item_id)
            if item_id in parsed.problems:
                faulty.append(item_id)
    out = dict(values)
    if faulty or "" in parsed.problems:
        out[STATUS] = "partial"
        named = ", ".join(faulty) if faulty else "an extra item"
        out[ERROR] = f"invalid answer after retry, stored as cannot-tell: {named}"
    else:
        out[STATUS] = "ok"
    return out


def item_values(features):
    """The item values of stored features (status and error left out)."""
    return {k: v for k, v in features.items() if k not in (STATUS, ERROR)}
