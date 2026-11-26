"""Survey of an output's Python files, run inside the sandbox (T2.7).

Run with ``python -I survey.py <folder> <result file>``: isolated, so nothing
in the output's folder can be imported in place of what this needs. It only
parses (never imports or runs) the output's files, and writes what it found
as JSON. Whatever it reports came from untrusted files: the sandbox treats it
as data.
"""

import ast
import importlib.util
import json
import os
import sys

MAX_FILES = 500
MAX_BYTES = 2 << 20
SKIPPED_FOLDERS = {"__pycache__", ".git", ".venv", "venv", "env", "node_modules"}
TOP_LEVEL_SAFE = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
                  ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Pass)


def _imports(tree):
    """(all top-level module names imported, those imported only inside try)."""
    found, guarded = set(), set()

    def visit(node, in_try):
        if isinstance(node, ast.Try):
            for child in node.body:
                visit(child, True)
            for part in node.handlers + node.orelse + node.finalbody:
                visit(part, in_try)
            return
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module.split(".")[0]]
        else:
            names = []
        for name in names:
            (guarded if in_try else found).add(name)
        for child in ast.iter_child_nodes(node):
            visit(child, in_try)

    visit(tree, False)
    return found, guarded - found


def _main_guard(tree):
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"):
                return True
    return False


CALLS = (ast.Call, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Await)


def _runs_code(tree):
    """Whether the module does more at import than define things: any
    statement but imports, definitions and assignments of plain values."""
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # a docstring
        if isinstance(node, ast.If) and _main_guard(ast.Module([node], [])):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if node.value is not None and any(isinstance(part, CALLS)
                                              for part in ast.walk(node.value)):
                return True
            continue
        if not isinstance(node, TOP_LEVEL_SAFE):
            return True
    return False


def _is_test(path, tree):
    name = os.path.basename(path)
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            return True
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            return True
    return False


def _uses(tree, names):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names:
            return True
        if isinstance(node, ast.Attribute) and node.attr in names:
            return True
    return False


def survey_file(root, relative):
    path = os.path.join(root, *relative.split("/"))
    entry = {"path": relative}
    try:
        if os.path.getsize(path) > MAX_BYTES:
            entry["error"] = "too large to read"
            return entry
        with open(path, "rb") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=relative)
    except SyntaxError as error:
        entry["syntax_error"] = f"line {error.lineno}: {error.msg}"
        return entry
    except (OSError, ValueError, RecursionError, MemoryError) as error:
        entry["error"] = type(error).__name__
        return entry
    imports, guarded = _imports(tree)
    entry.update(
        imports=sorted(imports), optional_imports=sorted(guarded),
        main_guard=_main_guard(tree), runs_code=_runs_code(tree),
        test=_is_test(relative, tree),
        arguments=_uses(tree, {"ArgumentParser", "argv", "click", "typer", "docopt"}),
        functions=[node.name for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))][:200])
    return entry


def scripts(root):
    """Console scripts declared in pyproject.toml: {name: "module:function"}."""
    path = os.path.join(root, "pyproject.toml")
    if not os.path.isfile(path) or os.path.getsize(path) > MAX_BYTES:
        return {}
    try:
        import tomllib

        with open(path, "rb") as handle:
            data = tomllib.load(handle)
        found = data.get("project", {}).get("scripts", {})
        return {str(k): str(v) for k, v in found.items() if isinstance(v, str)}
    except Exception:
        return {}


def main():
    root, result = sys.argv[1], sys.argv[2]
    files = []
    for folder, folders, names in os.walk(root):
        folders[:] = sorted(f for f in folders if f not in SKIPPED_FOLDERS
                            and not f.startswith("."))
        for name in sorted(names):
            if name.endswith(".py") and len(files) < MAX_FILES:
                relative = os.path.relpath(os.path.join(folder, name), root)
                files.append(relative.replace(os.sep, "/"))
    surveyed = [survey_file(root, relative) for relative in files]
    modules = sorted({name for entry in surveyed for name in
                      entry.get("imports", []) + entry.get("optional_imports", [])})
    available = {}
    for name in modules:
        try:
            available[name] = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            available[name] = False
    with open(result, "w", encoding="utf-8") as handle:
        json.dump({"files": surveyed, "available": available, "scripts": scripts(root)},
                  handle)


if __name__ == "__main__":
    main()
