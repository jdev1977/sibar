"""The reference answer files, the formula language and the tolerance rule.

Shared by the checker and by the tests of the reference files
(tests/reference_checks.py imports these). The formats are described in
checker/references/README.md.
"""

import ast
import math
import operator
from pathlib import Path

import yaml

REFERENCES = Path(__file__).resolve().parent / "references"
LEVELS = ("L0", "L1", "L2")


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
