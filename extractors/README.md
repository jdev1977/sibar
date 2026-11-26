# extractors

Python package of deterministic extractors, which parse an output directly and
record the choices made in it. Each extracted feature is stored with the version
of the extractor that produced it. See [docs/extractors.md](../docs/extractors.md)
for the interface, the command line and every feature.

- `base.py`: `Extractor`, `Inputs` and running extractors safely
- `registry.py`: extractors by project type (`PACKAGES`)
- `records.py`, `__main__.py`: `python -m extractors` over a record file
- `website/`: the twelve website extractors (T1.4) and their readers

Filled by these tasks in [tasks.md](../tasks.md):

- T1.4: website extractors (done)
- T2.8: pipeline, math or science, and engineering extractors
- W2.x.4: extractors and checkers for Wave 2 types
- W3.x: extractors and checkers for Wave 3 types
