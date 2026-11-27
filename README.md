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

**Status:** the tools for Phases 0 to 2 are written; nothing has been run
against a provider. In place: the repository layout and the secret scan, the
model list ([models.yaml](models.yaml), confirmed), the run record format,
the cost ledger, the generation runner, the offline renderer, the sandbox
for generated code, the prompts of all four project types, the deterministic
extractors of all four types, the rubrics and the tagger (batch tagging,
agreement, the calibration sample), the reference solutions for the math
and engineering tasks, and the metrics ([docs/metrics.md](docs/metrics.md),
implemented in [analysis/](analysis/README.md)). Every tool that calls a
provider (the runner and the tagger) has been tested only against fakes: no
live call has been made, so the first paid runs are also the first live
tests ([docs/runner.md](docs/runner.md)). Not built yet: the answer checker
(T2.10) and the viewer. No results exist: the pilot (T1.7) has not run.

## Layout

| Path | What goes there |
|---|---|
| [models.yaml](models.yaml) | The models under test: IDs, prices, defaults and sources |
| [prompts/](prompts/README.md) | Task prompts, by project type |
| [runner/](runner/README.md) | Python package: run record format and generation runs |
| [renderer/](docs/renderer.md) | Python package: offline screenshots of generated pages |
| [sandbox/](docs/sandbox.md) | Python package: runs generated code in a Windows sandbox (no network, no files outside its folder, limits) and records the outcome |
| [extractors/](docs/extractors.md) | Python package: features parsed from outputs |
| [analysis/](analysis/README.md) | Python package: the metrics and the stability check, with the data files they read (how each feature is counted, what each prompt dictates) |
| [rubrics/](rubrics/README.md) | Versioned tagging rubrics, by project type |
| [tagger/](tagger/README.md) | Python package: loads and checks the rubrics, tags outputs through the providers' batch APIs, and measures agreement between taggings |
| [checker/](checker/references/README.md) | Reference answers for the math and engineering tasks, with tolerances; the answer checker itself is not written yet |
| [viewer/](viewer/README.md) | Local page for comparing outputs (not built yet, T3.5) |
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
    .venv/Scripts/python -m playwright install chromium
    git config core.hooksPath .githooks

The Chromium download is for the [renderer](docs/renderer.md); it goes to the
user profile. To run generated code, also build the
[sandbox](docs/sandbox.md)'s own Python once (it downloads its pinned
packages): `.venv/Scripts/python -m sandbox setup`. The last command turns on the pre-commit and pre-push secret scan. Run it once
per clone. See [docs/secrets.md](docs/secrets.md).

API keys are read from environment variables only; no command reads a `.env`
file. `.env.example` lists the variable names, and
[docs/secrets.md](docs/secrets.md#setting-keys-in-powershell) shows how to
set them in PowerShell.

Commands in the docs are written `python -m ...`, one per line: in
PowerShell, run them from the repository root as `.venv\Scripts\python -m ...`.

## Tests

    .venv/Scripts/python -m pytest

## Publishing rule

This repository is public. Generated model outputs stay out of git until each
provider's terms on storing, sharing and publishing them are cleared (tasks T0.7
and T6.3). `data/`, `runs/` and `outputs/` are gitignored; do not force-add
anything in them.

Outputs for engineering tasks are collected to study defaults, not to be used as
designs. Anything published carries that note.
