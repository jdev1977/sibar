"""Prompt files: one YAML file per task under ``prompts/<type>/`` (T0.5).

The format is described in ``prompts/README.md``. A file names its task, its
project type and its prompt-set version, and holds the prompt text for each
level of direction (L0, L1, L2) in each wording (A, and usually B)::

    schema_version: 1
    project_type: website        # must equal the folder name
    task_id: bakery-landing      # must equal the file name without .yaml
    prompt_set_version: "1"      # text: quote it
    prompts:
      L0: {A: "...", B: "..."}
      L1: {A: "...", B: "..."}
      L2: {A: "...", B: "..."}
    notes: optional text for prompt authors; never sent

Texts are sent exactly as loaded, after leading and trailing whitespace is
removed.
"""

from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Tuple

import yaml

from runner.record import LEVELS, WORDINGS, _is_slug, _is_word

SCHEMA_VERSION = 1
SUFFIXES = (".yaml", ".yml")
REQUIRED_WORDINGS = ("A",)  # B may be left out by a one-wording type
KEYS = ("schema_version", "project_type", "task_id", "prompt_set_version",
        "prompts")
OPTIONAL_KEYS = ("notes",)


class PromptError(ValueError):
    """A prompt file is unreadable or breaks the format."""


@dataclass(frozen=True)
class PromptTask:
    """One task's prompts, as loaded from its file."""

    project_type: str
    task_id: str
    prompt_set_version: str
    texts: Mapping[Tuple[str, str], str]  # (level, wording) -> text
    path: Path

    def text(self, level, wording):
        """The prompt for ``level`` and ``wording``; KeyError if absent."""
        return self.texts[(level, wording)]

    def variants(self):
        """(level, wording, text) for every prompt, L0 A first."""
        return [(level, wording, self.texts[(level, wording)])
                for level in LEVELS for wording in WORDINGS
                if (level, wording) in self.texts]


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a repeated key instead of keeping the last."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            line = key_node.start_mark.line + 1
            if not isinstance(key, Hashable):
                raise PromptError(f"unusable key on line {line}")
            if key in seen:
                raise PromptError(f"repeated key {key!r} on line {line}")
            seen.add(key)
        return super().construct_mapping(node, deep)


def _texts(raw):
    if not isinstance(raw, dict):
        raise PromptError("prompts must be a mapping of level to wordings")
    for level in raw:
        if level not in LEVELS:
            raise PromptError(f"prompts: unknown level {level!r} "
                              f"(levels are {', '.join(LEVELS)})")
    texts = {}
    for level in LEVELS:
        if level not in raw:
            raise PromptError(f"prompts: missing level {level}")
        wordings = raw[level]
        if not isinstance(wordings, dict):
            raise PromptError(f"prompts.{level} must be a mapping of wording "
                              "to text")
        for wording in wordings:
            if wording not in WORDINGS:
                raise PromptError(f"prompts.{level}: unknown wording "
                                  f"{wording!r} (wordings are "
                                  f"{', '.join(WORDINGS)})")
        for wording in REQUIRED_WORDINGS:
            if wording not in wordings:
                raise PromptError(f"prompts.{level}.{wording} is missing")
        for wording in WORDINGS:
            if wording not in wordings:
                continue
            text = wordings[wording]
            if not isinstance(text, str) or not text.strip():
                raise PromptError(f"prompts.{level}.{wording} must be "
                                  "non-empty text")
            texts[(level, wording)] = text.strip()
    return texts


def _task(raw, path):
    if not isinstance(raw, dict):
        raise PromptError("the file must be a mapping")
    for key in KEYS:
        if key not in raw:
            raise PromptError(f"missing {key}")
    for key in raw:
        if key not in KEYS and key not in OPTIONAL_KEYS:
            raise PromptError(f"unknown key {key!r}")
    version = raw["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise PromptError(f"schema_version must be {SCHEMA_VERSION}")
    for key in ("project_type", "task_id"):
        if not _is_slug(raw[key]):
            raise PromptError(f"{key} must be a slug (lower-case letters, "
                              "digits, '.', '_' or '-')")
    if raw["task_id"] != path.stem:
        raise PromptError(f"task_id {raw['task_id']!r} must equal the file "
                          f"name {path.stem!r}")
    if raw["project_type"] != path.parent.name:
        raise PromptError(f"project_type {raw['project_type']!r} must equal "
                          f"the folder name {path.parent.name!r}")
    prompt_set = raw["prompt_set_version"]
    if not isinstance(prompt_set, str):
        raise PromptError("prompt_set_version must be text: quote it, "
                          'such as "1"')
    if not _is_word(prompt_set):
        raise PromptError("prompt_set_version must be text with no spaces")
    notes = raw.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise PromptError("notes must be text")
    return PromptTask(
        project_type=raw["project_type"],
        task_id=raw["task_id"],
        prompt_set_version=prompt_set,
        texts=MappingProxyType(_texts(raw["prompts"])),
        path=path,
    )


def load_prompt_file(path):
    """Read one prompt file; raise :class:`PromptError` naming the file."""
    path = Path(path)
    try:
        if path.suffix.lower() not in SUFFIXES:
            raise PromptError("a prompt file must end in .yaml or .yml")
        text = path.read_text(encoding="utf-8")
        return _task(yaml.load(text, Loader=_UniqueKeyLoader), path)
    except (PromptError, yaml.YAMLError, OSError, UnicodeDecodeError) as error:
        raise PromptError(f"{path.name}: {error}") from error


def load_prompts(paths):
    """Load prompt files from files and directories (searched recursively).

    Returns tasks in path order. Raises :class:`PromptError` for a bad file, a
    missing path, no files at all, or a task (type and id) found twice.
    """
    files = []
    for path in map(Path, paths):
        if path.is_dir():
            files += sorted(p for p in path.rglob("*")
                            if p.is_file() and p.suffix.lower() in SUFFIXES)
        elif path.is_file():
            files.append(path)
        else:
            raise PromptError(f"{path}: not found")
    if not files:
        raise PromptError("no prompt files (*.yaml) found")
    tasks, seen = [], {}
    for file in files:
        task = load_prompt_file(file)
        key = (task.project_type, task.task_id)
        if key in seen:
            raise PromptError(f"task {task.project_type}/{task.task_id} is "
                              f"defined more than once: {seen[key]} and {file}")
        seen[key] = file
        tasks.append(task)
    return tuple(tasks)
