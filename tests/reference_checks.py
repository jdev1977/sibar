"""Reading and checking the reference answer files (T2.3).

The format is described in checker/references/README.md. This module loads
a file, checks its shape, evaluates the small formula language and applies a
tolerance. The answer checker itself is T2.10; nothing here grades a model.
"""

import ast
import math
import operator
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "checker" / "references"
DOCUMENTS = ROOT / "docs" / "references"
TYPES = ("math", "engineering")
LEVELS = ("L0", "L1", "L2")

TOP_KEYS = {"schema_version", "project_type", "task_id", "prompt_set_version",
            "title", "givens", "assumptions", "levels", "quantities"}
TOP_OPTIONAL = {"study_data_note", "l2_givens", "criteria"}
LEVEL_KEYS = {"checkable", "partial", "note", "quantities", "one_of",
              "if_reported", "criteria", "consistency"}
QUANTITY_KEYS = {"description", "kind", "type", "unit", "value", "exact",
                 "choices", "rule", "keyed_by", "tolerance", "tolerance_at",
                 "other_units",
                 "inputs", "formula", "method", "examples", "range",
                 "alternatives", "accepted_examples", "not_accepted"}
ALTERNATIVE_KEYS = {"id", "condition", "levels", "value", "tolerance", "inputs",
                    "formula", "examples", "note"}
KINDS = ("fixed", "conditional")
VALUE_TYPES = ("number", "integer", "choice", "list", "date")


class ReferenceFileError(ValueError):
    """A reference file does not follow the format."""


def reference_paths():
    return sorted(REFERENCES.glob("*/*.yaml"))


def load_reference(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


# --- the formula language -----------------------------------------------------

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow}
_COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
            ast.GtE: operator.ge, ast.Eq: operator.eq}
_FUNCTIONS = {"sqrt": math.sqrt, "log10": math.log10, "abs": abs, "min": min,
              "max": max}


def evaluate(expression, inputs, allow_logic=False):
    """Evaluate a formula (or, with ``allow_logic``, a check) on named inputs.

    Only numbers, the named inputs, ``pi``, arithmetic, and the listed
    functions are allowed; a check may also compare and combine with and,
    or, not. Anything else raises :class:`ReferenceFileError`.
    """
    names = dict(inputs, pi=math.pi)

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise ReferenceFileError(f"unknown name {node.id!r} in {expression!r}")
            return names[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            return _BINARY[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = walk(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _FUNCTIONS and not node.keywords):
            return _FUNCTIONS[node.func.id](*[walk(arg) for arg in node.args])
        if allow_logic:
            if isinstance(node, ast.Compare) and all(type(op) in _COMPARE
                                                     for op in node.ops):
                left = walk(node.left)
                for op, right_node in zip(node.ops, node.comparators):
                    right = walk(right_node)
                    if not _COMPARE[type(op)](left, right):
                        return False
                    left = right
                return True
            if isinstance(node, ast.BoolOp):
                values = [bool(walk(value)) for value in node.values]
                return all(values) if isinstance(node.op, ast.And) else any(values)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                return not walk(node.operand)
        raise ReferenceFileError(f"{expression!r} uses something the formula "
                             f"language does not allow ({type(node).__name__})")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ReferenceFileError(f"{expression!r} is not an expression") from error
    return walk(tree)


def formula_names(expression):
    """The input names a formula or check uses."""
    reserved = set(_FUNCTIONS) | {"pi"}
    return {node.id for node in ast.walk(ast.parse(expression, mode="eval"))
            if isinstance(node, ast.Name)} - reserved


# --- tolerances ---------------------------------------------------------------


def tolerance_for(quantity, level, alternative=None):
    if alternative is not None and "tolerance" in alternative:
        return alternative["tolerance"]
    return quantity.get("tolerance_at", {}).get(level, quantity.get("tolerance"))


def within(tolerance, reference, stated):
    """The README's rule: inside abs, or inside rel times the reference."""
    gap = abs(stated - reference)
    slack = 1e-9 * max(1.0, abs(reference))        # float noise only
    if tolerance.get("abs") is not None and gap <= tolerance["abs"] + slack:
        return True
    return (tolerance.get("rel") is not None
            and gap <= tolerance["rel"] * abs(reference) + slack)


def level_quantities(entry):
    """Every quantity id a level lists, in any of its groups."""
    listed = [name for group in ("quantities", "if_reported", "consistency")
              for name in entry.get(group, ())]
    return listed + [name for group in entry.get("one_of", ()) for name in group]


def levels_using(reference, quantity_id):
    return [level for level in LEVELS
            if quantity_id in level_quantities(reference["levels"][level])]


def paired(quantity, stated):
    """Pair a list quantity's reference values with a response's values.

    ``stated`` maps each key (the measurement, the x) to the value the
    response gives for it; the order the response lists them in does not
    matter. Returns (reference, stated) pairs, or None if the keys differ.
    """
    keys = quantity["keyed_by"]["values"]
    if sorted(stated) != sorted(keys):
        return None
    return [(reference, stated[key]) for key, reference in zip(keys, quantity["value"])]


# --- shape --------------------------------------------------------------------


def _need(condition, message):
    if not condition:
        raise ReferenceFileError(message)


def _check_tolerance(tolerance, where):
    _need(isinstance(tolerance, dict) and set(tolerance) <= {"abs", "rel", "why"},
          f"{where}: a tolerance holds abs, rel and why")
    _need("abs" in tolerance or "rel" in tolerance, f"{where}: abs or rel is needed")
    for key in ("abs", "rel"):
        if key in tolerance:
            _need(type(tolerance[key]) in (int, float) and tolerance[key] >= 0,
                  f"{where}: {key} must be a number, zero or more")
    _need(isinstance(tolerance.get("why"), str) and tolerance["why"].strip(),
          f"{where}: a tolerance needs its reason (why)")


def _check_inputs(inputs, where):
    _need(isinstance(inputs, dict) and inputs, f"{where}: inputs must be a mapping")
    for name, spec in inputs.items():
        _need(name.isidentifier(), f"{where}: input {name!r} is not a plain name")
        _need(isinstance(spec, dict) and set(spec) == {"description", "unit"},
              f"{where}: input {name} needs description and unit")


def _check_examples(examples, inputs, where):
    _need(isinstance(examples, list) and examples, f"{where}: examples are needed")
    for example in examples:
        _need(set(example) <= {"inputs", "value", "note"} and "value" in example,
              f"{where}: an example holds inputs, value and note")
        _need(set(example.get("inputs", ())) == set(inputs),
              f"{where}: an example must give every input and no other")
        # PyYAML reads a number such as 1e6 (no dot, or no sign in the
        # exponent) as text, so check the type.
        for number in [example["value"], *example["inputs"].values()]:
            _need(type(number) in (int, float), f"{where}: {number!r} is not a number")


def _check_computed(holder, where, needs_tolerance):
    """A conditional quantity, or an alternative that has a formula."""
    _check_inputs(holder.get("inputs"), where)
    _need(("formula" in holder) != ("method" in holder),
          f"{where}: give a formula or a method, not both")
    if "formula" in holder:
        _need(formula_names(holder["formula"]) == set(holder["inputs"]),
              f"{where}: the formula must use every input and no other name")
    _check_examples(holder.get("examples"), holder["inputs"], where)
    if needs_tolerance:
        _check_tolerance(holder.get("tolerance"), where)


def _check_value(value, value_type, choices, where):
    if value_type == "number":
        _need(type(value) in (int, float), f"{where}: value must be a number")
    elif value_type == "integer":
        _need(type(value) is int, f"{where}: value must be a whole number")
    elif value_type == "choice":
        _need(value in (choices or ()), f"{where}: value must be one of the choices")
    elif value_type == "list":
        _need(isinstance(value, list) and value, f"{where}: value must be a list")
        _need(all(type(item) in (int, float) for item in value),
              f"{where}: a list holds numbers")
    elif value_type == "date":
        _need(isinstance(value, str) and len(value) == 10,
              f"{where}: value must be an ISO date in quotes")


def _check_quantity(name, quantity, level_names):
    where = f"quantity {name}"
    _need(isinstance(quantity, dict) and set(quantity) <= QUANTITY_KEYS,
          f"{where}: unknown key {sorted(set(quantity) - QUANTITY_KEYS)}")
    for key in ("description", "kind", "unit"):
        _need(isinstance(quantity.get(key), str) and quantity[key].strip(),
              f"{where}: {key} is needed")
    _need(quantity["kind"] in KINDS, f"{where}: kind must be one of {KINDS}")
    value_type = quantity.get("type", "number")
    _need(value_type in VALUE_TYPES, f"{where}: type must be one of {VALUE_TYPES}")
    if value_type == "choice":
        _need(isinstance(quantity.get("choices"), list) and quantity["choices"],
              f"{where}: a choice needs its choices")
    if value_type == "list":
        # A list is never compared by position: each element has a key.
        keyed = quantity.get("keyed_by")
        _need(isinstance(keyed, dict) and set(keyed) == {"description", "values"}
              and len(keyed["values"]) == len(set(keyed["values"])) == len(quantity["value"]),
              f"{where}: a list needs keyed_by, with one distinct key per element")
    else:
        _need("keyed_by" not in quantity, f"{where}: keyed_by is for lists")
    if quantity["kind"] == "fixed":
        _need("value" in quantity, f"{where}: a fixed quantity needs a value")
        _check_value(quantity["value"], value_type, quantity.get("choices"), where)
        for key in ("inputs", "formula", "method", "examples", "range"):
            _need(key not in quantity, f"{where}: {key} belongs to a conditional quantity")
        if value_type in ("choice", "date"):
            _need("tolerance" not in quantity, f"{where}: a {value_type} has no tolerance")
        else:
            _check_tolerance(quantity.get("tolerance"), where)
    else:
        _check_computed(quantity, where, needs_tolerance=True)
        if "value" in quantity:
            _check_value(quantity["value"], value_type, None, where)
        if "range" in quantity:
            span = quantity["range"]
            _need(set(span) == {"low", "high", "applies"} and span["low"] < span["high"],
                  f"{where}: a range holds low, high and applies")
    for level, tolerance in quantity.get("tolerance_at", {}).items():
        _need(level in LEVELS, f"{where}: tolerance_at names an unknown level")
        _check_tolerance(tolerance, f"{where} at {level}")
    for unit in quantity.get("other_units", ()):
        _need(set(unit) <= {"unit", "factor", "offset"} and {"unit", "factor"} <= set(unit)
              and type(unit["factor"]) in (int, float) and unit["factor"] > 0,
              f"{where}: an other_units entry holds unit, factor and maybe offset")
    seen = set()
    for alternative in quantity.get("alternatives", ()):
        _need(set(alternative) <= ALTERNATIVE_KEYS, f"{where}: unknown key in an alternative")
        label = f"{where}, alternative {alternative.get('id')}"
        _need(isinstance(alternative.get("id"), str) and alternative["id"] not in seen,
              f"{label}: alternatives need distinct ids")
        seen.add(alternative["id"])
        _need(isinstance(alternative.get("condition"), str) and alternative["condition"].strip(),
              f"{label}: the condition is needed")
        _need(set(alternative.get("levels", ())) <= set(level_names),
              f"{label}: levels must be levels that use the quantity")
        _need(("value" in alternative) != ("formula" in alternative),
              f"{label}: give a value or a formula")
        if "value" in alternative:
            _check_value(alternative["value"], value_type, quantity.get("choices"), label)
        else:
            _check_computed(alternative, label, needs_tolerance=False)
        if "tolerance" in alternative:
            _check_tolerance(alternative["tolerance"], label)
    for key in ("accepted_examples", "not_accepted"):
        for entry in quantity.get(key, ()):
            _need(set(entry) == {"value", "why"} and type(entry["value"]) in (int, float),
                  f"{where}: {key} entries hold a number and why")
            _need(quantity["kind"] == "fixed" and value_type in ("number", "integer"),
                  f"{where}: {key} is for fixed numbers")


def _check_criterion(name, criterion):
    where = f"criterion {name}"
    _need({"description", "pass_when"} <= set(criterion)
          and set(criterion) <= {"description", "pass_when", "all_passing"},
          f"{where}: description, pass_when and maybe all_passing")
    if "all_passing" in criterion:
        listed = criterion["all_passing"]
        _need(set(listed) == {"note", "inputs", "sets"} and listed["sets"]
              and all(len(row) == len(listed["inputs"]) for row in listed["sets"]),
              f"{where}: all_passing holds note, inputs and sets of that many numbers")
    _need(isinstance(criterion["pass_when"], list) and criterion["pass_when"],
          f"{where}: pass_when needs items")
    seen = set()
    for item in criterion["pass_when"]:
        _need(set(item) <= {"id", "text", "inputs", "check", "record_only"}
              and {"id", "text"} <= set(item),
              f"{where}: an item holds id, text, and maybe inputs, check and record_only")
        _need(item.get("record_only", True) is True and ("record_only" not in item
                                                         or "check" in item),
              f"{where}, {item['id']}: record_only is true or absent, and needs a check")
        _need(item["id"] not in seen, f"{where}: item ids must differ")
        seen.add(item["id"])
        _need(("check" in item) == ("inputs" in item),
              f"{where}, {item['id']}: a check needs inputs, and inputs a check")
        if "check" in item:
            _check_inputs(item["inputs"], f"{where}, {item['id']}")
            _need(formula_names(item["check"]) == set(item["inputs"]),
                  f"{where}, {item['id']}: the check must use every input and no other name")


def _check_givens(givens, where):
    _need(isinstance(givens, list), f"{where} must be a list")
    seen = set()
    for given in givens:
        _need(set(given) == {"id", "text", "value", "unit"}, f"{where}: id, text, value, unit")
        if given["unit"] != "date":
            _need(not isinstance(given["value"], str), f"{where}: {given['id']} is not a number")
        _need(given["id"] not in seen, f"{where}: ids must differ")
        seen.add(given["id"])
        _need(isinstance(given["text"], str) and given["text"].strip(),
              f"{where}: text is the exact string in the prompts")


def validate(reference, path):
    """Raise :class:`ReferenceFileError` unless the file follows the format."""
    _need(isinstance(reference, dict), "the file must be a mapping")
    _need(TOP_KEYS <= set(reference), f"missing {sorted(TOP_KEYS - set(reference))}")
    _need(set(reference) <= TOP_KEYS | TOP_OPTIONAL,
          f"unknown key {sorted(set(reference) - TOP_KEYS - TOP_OPTIONAL)}")
    _need(reference["schema_version"] == 1, "schema_version must be 1")
    _need(reference["project_type"] == path.parent.name, "project_type must be the folder")
    _need(reference["task_id"] == path.stem, "task_id must be the file name")
    _need(isinstance(reference["prompt_set_version"], str), "prompt_set_version is text")
    _need(isinstance(reference["title"], str) and reference["title"].strip(), "title")
    if reference["project_type"] == "engineering":
        _need("not a design" in reference.get("study_data_note", ""),
              "an engineering file must carry the study data note")
    _check_givens(reference["givens"], "givens")
    _check_givens(reference.get("l2_givens", []), "l2_givens")
    _need(isinstance(reference["assumptions"], list) and reference["assumptions"]
          and all(isinstance(a, str) and a.strip() for a in reference["assumptions"]),
          "assumptions must be a list of sentences")

    quantities = reference["quantities"]
    criteria = reference.get("criteria", {})
    _need(isinstance(quantities, dict) and isinstance(criteria, dict),
          "quantities and criteria are mappings")
    _need(set(reference["levels"]) == set(LEVELS), "levels must be L0, L1 and L2")
    used = set()
    for level, entry in reference["levels"].items():
        _need(set(entry) <= LEVEL_KEYS, f"{level}: unknown key")
        _need(type(entry.get("checkable")) is bool, f"{level}: checkable must be true or false")
        _need(isinstance(entry.get("note"), str) and entry["note"].strip(), f"{level}: note")
        if entry["checkable"]:
            _need(entry.get("quantities"), f"{level}: a checkable level lists quantities")
            _need("consistency" not in entry, f"{level}: consistency is for levels not checkable")
        else:
            _need("quantities" not in entry and "one_of" not in entry
                  and "partial" not in entry,
                  f"{level}: not checkable, so no quantities, one_of or partial")
        _need(entry.get("partial", True) is True, f"{level}: partial is true or absent")
        groups = entry.get("one_of", [])
        _need(isinstance(groups, list) and len(groups) != 1
              and all(isinstance(group, list) and group for group in groups),
              f"{level}: one_of holds two or more groups of quantity ids")
        listed = level_quantities(entry)
        for name in listed:
            _need(name in quantities, f"{level}: unknown quantity {name}")
        _need(len(listed) == len(set(listed)), f"{level}: a quantity is listed twice")
        for name in entry.get("consistency", ()):
            _need(quantities[name]["kind"] == "conditional",
                  f"{level}: consistency entries are conditional quantities")
        for name in entry.get("criteria", ()):
            _need(name in criteria, f"{level}: unknown criterion {name}")
        used.update(listed)
        used.update(entry.get("criteria", ()))
    unused = (set(quantities) | set(criteria)) - used
    _need(not unused, f"defined but used at no level: {sorted(unused)}")
    for name, quantity in quantities.items():
        _need(name.replace("_", "").isalnum(), f"quantity id {name!r} is not a plain name")
        _check_quantity(name, quantity, levels_using(reference, name))
    for name, criterion in criteria.items():
        _check_criterion(name, criterion)
