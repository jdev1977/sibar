# sibar

Baselines of what LLMs produce by default, across several project types.

The goal is to record what each model produces, on each date, for a standard set
of tasks when the prompt asks for a solution and gives little or no direction.
The styling, methods and choices that keep recurring are the model's default. A
real artifact can then be scored by how much of it matches that default.

The first four project types are a website, a pipeline, a math or science
problem, and an engineering or mechanical problem. Each task is written at three
levels of direction (L0 bare, L1 brief, L2 directed) and run several times.

- [plan.md](plan.md): the method, project types, deliverables and phases.
- [tasks.md](tasks.md): the task list, with IDs such as T0.1.

**Status:** early setup (Phase 0). The repository layout and the secret scan are
in place. The runner, prompts, extractors, rubrics and viewer are not built yet,
and no results exist.

## Layout

| Path | What goes there |
|---|---|
| [prompts/](prompts/README.md) | Task prompts, by project type |
| [runner/](runner/README.md) | Python package: run record format and generation runs |
| [extractors/](extractors/README.md) | Python package: features parsed from outputs |
| [rubrics/](rubrics/README.md) | Versioned tagging rubrics, by project type |
| [viewer/](viewer/README.md) | Local page for comparing outputs |
| [docs/](docs/README.md) | Project documents |
| `data/` | Local only, gitignored: run records, raw responses, extracted files and dataset releases. Not part of a clone |
| `tests/` | pytest tests |
| `tools/` | Repository tooling (the secret scan) |
| `.githooks/` | Git hooks that run the secret scan |

## Setup

You need Git and Python 3.13. From the repository root, in a Windows shell (use
`.venv/bin/python` instead of `.venv/Scripts/python` elsewhere):

    python -m venv .venv
    .venv/Scripts/python -m pip install -r requirements.txt
    git config core.hooksPath .githooks

The last command turns on the pre-commit and pre-push secret scan. Run it once
per clone. See [docs/secrets.md](docs/secrets.md).

API keys are read from environment variables only. `.env.example` lists the
variable names.

## Tests

    .venv/Scripts/python -m pytest

## Publishing rule

This repository is public. Generated model outputs stay out of git until each
provider's terms on storing, sharing and publishing them are cleared (tasks T0.7
and T6.3). `data/`, `runs/` and `outputs/` are gitignored; do not force-add
anything in them.

Outputs for engineering tasks are collected to study defaults, not to be used as
designs. Anything published carries that note.
