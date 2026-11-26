"""Language, file layout, tests and comments of a pipeline output."""

import re

from extractors.base import Extractor
from extractors.common import code
from extractors.common.response import NO_INPUT, get_doc, result
from extractors.pipeline.source import get_output

SNIPPET_LINES = 8       # an unnamed block shorter than this is a usage snippet
_DEPENDENCIES = re.compile(
    r"requirements[\w.-]{0,40}\.txt|pyproject\.toml|setup\.py|setup\.cfg|pipfile|"
    r"environment\.ya?ml|package\.json|go\.mod|cargo\.toml|gemfile|description")
_GUARD = re.compile(r"""^if __name__ ?== ?["']__main__["'] ?:""", re.M)
_FRAMEWORKS = (
    ("pytest", "python", re.compile(r"^[ \t]{0,40}(?:import|from) pytest\b", re.M)),
    ("unittest", "python", re.compile(
        r"^[ \t]{0,40}(?:import|from) unittest\b", re.M)),
    ("go-testing", "go", re.compile(r"\*testing\.[TBF]\b")),
    ("jest", None, re.compile(r"@jest/|from [\"']jest|\bjest\.")),
    ("vitest", None, re.compile(r"[\"']vitest[\"']")),
    ("mocha", None, re.compile(r"[\"'](?:mocha|chai)[\"']")),
    ("node-test", None, re.compile(r"[\"']node:test[\"']")),
    ("rust-test", "rust", re.compile(r"#\[(?:cfg\()?test\b")),
    ("rspec", "ruby", re.compile(r"\bRSpec\b|[\"']rspec")),
    ("testthat", "r", re.compile(r"\btest_that\(")),
)


def language(inputs):
    output = get_output(inputs)
    if not output.programs and not output.configs:
        return dict(NO_INPUT)
    found = {c.language for c in output.programs}
    weight = {}
    for item in output.programs:
        if item.language in code.PROGRAMMING:
            weight[item.language] = weight.get(item.language, 0) + len(item.parts.code)
    if not weight:
        for item in output.programs:
            weight[item.language] = weight.get(item.language, 0) + len(item.parts.code)
    primary = min(weight, key=lambda k: (-weight[k], k)) if weight else "none"
    return result(get_doc(inputs), {"primary_language": primary,
                                    "languages": sorted(found)})


def _sources(output):
    """The files that make up the program, tests and ``setup.py`` left out."""
    programs = [c for c in output.main if c.source.name != "setup.py"]
    first = [c for c in programs if c.language in code.PROGRAMMING] or programs
    return [c for c in first if c.source.named or c.lines >= SNIPPET_LINES] or first


def _structure(output):
    """``(structure, number of source files)``; ``(None, None)`` where the
    reply does not show whether its blocks are files or alternatives."""
    sources = _sources(output)
    if not sources:
        if output.configs:
            return "config-only", 0
        return ("single-file", 1) if output.programs else ("no-code", 0)
    if len(sources) == 1:
        return "single-file", 1
    if not all(c.source.named for c in sources):
        return None, None
    folders = [c.source.path.rpartition("/")[0] for c in sources]
    nested = [f for f in folders if f]
    package = (any(c.source.name in ("__init__.py", "__main__.py") for c in sources)
               or len(nested) != len(set(nested))
               or any(s.name == "go.mod" for s in output.configs))
    return ("package" if package else "multiple-files"), len(sources)


def layout(inputs):
    doc = get_doc(inputs)
    if not doc.has_text and not doc.files:
        return dict(NO_INPUT)
    output = get_output(inputs)
    structure, count = _structure(output)
    named = [f for f in doc.files if f.named]
    main = "\n".join(c.parts.code for c in output.main if c.language == "python")
    python = any(c.language == "python" for c in output.main)
    return result(doc, {
        "structure": structure,
        "source_files": count,
        "file_names": sorted({f.path.lower() for f in named}),
        "has_readme": any(f.name.startswith("readme") for f in named),
        "dependency_files": sorted({f.name for f in named
                                    if _DEPENDENCIES.fullmatch(f.name)}),
        "entry_point_guard": bool(_GUARD.search(main)) if python else None,
    })


def testing(inputs):
    output = get_output(inputs)
    if not output.programs:
        return dict(NO_INPUT)
    tests = [c for c in output.programs if c.is_test]
    frameworks = set()
    for item in tests:
        # `bare` empties strings; the imports of a JavaScript test are strings
        for name, only, pattern in _FRAMEWORKS:
            if only in (None, item.language) and pattern.search(item.parts.code):
                frameworks.add(name)
        if item.language == "python" and not frameworks & {"pytest", "unittest"}:
            frameworks.add("pytest")      # bare test_ functions are run by pytest
    return result(get_doc(inputs), {
        "tests_present": bool(tests),
        "test_files": len(tests),
        "test_frameworks": sorted(frameworks),
    })


def comments(inputs):
    output = get_output(inputs)
    if not output.programs:
        return dict(NO_INPUT)
    lines = sum(c.parts.comment_lines for c in output.programs)
    docstrings = sum(c.parts.docstrings for c in output.programs)
    code_lines = sum(c.lines for c in output.programs)
    share = lines / (lines + code_lines) if lines + code_lines else 0
    density = ("none" if not lines else "low" if share < 0.05
               else "medium" if share < 0.15 else "high")
    python = any(c.language == "python" for c in output.programs)
    return result(get_doc(inputs), {
        "comment_lines": lines,
        "comment_density": density,
        "docstrings": docstrings if python else None,
        "has_docstrings": bool(docstrings) if python else None,
    })


EXTRACTORS = (
    Extractor("pipeline.language", "1", "pipeline", language,
              "programming languages of the code"),
    Extractor("pipeline.layout", "1", "pipeline", layout,
              "single file or modules, file names, README, dependency files"),
    Extractor("pipeline.testing", "1", "pipeline", testing,
              "tests present and their framework"),
    Extractor("pipeline.comments", "1", "pipeline", comments,
              "comment and docstring counts"),
)
