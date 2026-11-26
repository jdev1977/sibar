"""The code of a pipeline output, split once and shared by the extractors.

``programs`` are the files in a programming or scripting language,
``configs`` the configuration files. A **test file** is one that holds tests;
features about how the pipeline behaves read the other programs only.
"""

import re
from dataclasses import dataclass

from extractors.common import code
from extractors.common.response import get_doc

_TEST_NAME = re.compile(r"(?:^test_|_test\.|\.test\.|\.spec\.|^tests?\.|^conftest\.)")
_TEST_FOLDER = re.compile(r"(?:^|/)(?:tests?|spec|__tests__)/", re.IGNORECASE)
_TEST_MARKS = {
    "python": re.compile(r"^[ \t]{0,40}(?:class \w{1,80}\([\w.]{0,80}TestCase\)"
                         r"|(?:async )?def test_\w{0,80}\()", re.M),
    "go": re.compile(r"\bfunc (?:Test|Benchmark|Fuzz)\w{0,80}\([^)\n]{0,80}\*testing\."),
    "javascript": re.compile(r"(?:^|[^.\w])(?:describe|it|test)\(\s?[\"'`]", re.M),
    "typescript": re.compile(r"(?:^|[^.\w])(?:describe|it|test)\(\s?[\"'`]", re.M),
    "rust": re.compile(r"#\[(?:cfg\()?test\b"),
    "ruby": re.compile(r"\bRSpec\.describe\b|<\s?Minitest::Test\b|^[ \t]{0,40}describe\b",
                       re.M),
    "r": re.compile(r"\btest_that\("),
}
_ASSERT = re.compile(r"\bassert|TestCase\b|\bpytest\b")


@dataclass(frozen=True)
class Code:
    source: object          # extractors.common.response.Source
    parts: object           # extractors.common.code.Parts
    is_test: bool
    lines: int              # non-blank lines of code

    @property
    def language(self):
        return self.source.language


@dataclass(frozen=True)
class Output:
    programs: tuple         # Code, programming and scripting languages
    configs: tuple          # Source

    @property
    def main(self):
        """The programs that are not tests."""
        return tuple(c for c in self.programs if not c.is_test)

    def text(self, which="code", main=True):
        """The ``code`` or ``bare`` text of the programs, joined."""
        chosen = self.main if main else self.programs
        return "\n".join(getattr(c.parts, which) for c in chosen)


def _is_test(source, parts):
    marks = _TEST_MARKS.get(source.language)
    if not marks or not marks.search(parts.code):
        return False
    if _TEST_NAME.search(source.name) or _TEST_FOLDER.search(source.path):
        return True
    # elsewhere, a function named test_... needs an assertion to be a test
    return source.language != "python" or bool(_ASSERT.search(parts.bare))


def _build(inputs):
    programs, configs = [], []
    for source in get_doc(inputs).files:
        if source.language in code.PROGRAMMING | code.SCRIPTING:
            parts = code.split(source.language, source.text)
            lines = sum(1 for line in parts.code.split("\n") if line.strip())
            programs.append(Code(source, parts, _is_test(source, parts), lines))
        elif source.language in code.CONFIG:
            configs.append(source)
    return Output(tuple(programs), tuple(configs))


def get_output(inputs):
    return inputs.cached("t2.8.pipeline", lambda: _build(inputs))
