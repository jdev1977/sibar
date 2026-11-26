"""The repository layout from task T0.1."""

import importlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("prompts", "runner", "extractors", "rubrics", "viewer", "docs")
PACKAGES = ("runner", "extractors")


def tracked(path):
    return subprocess.run(
        ["git", "ls-files", "--", path],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()


@pytest.mark.parametrize("path", ["README.md"] + [d + "/README.md" for d in DIRECTORIES])
def test_readme_is_tracked(path):
    assert tracked(path) == [path]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_is_importable_from_the_root(name):
    module = importlib.import_module(name)
    assert Path(module.__file__) == ROOT / name / "__init__.py"


def test_nothing_in_data_is_tracked():
    assert tracked("data") == []
