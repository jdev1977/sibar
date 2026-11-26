# analysis

What the metrics read, and later the code that computes them. The metrics are
defined in [docs/metrics.md](../docs/metrics.md) (T1.5).

One folder per project type holds two data files:

- `<type>/features.yaml`: every feature of that type's extractors, with its
  type (categorical, boolean, number, set, ordered list, count-map), its role
  (primary, provisional, secondary, diagnostic), its bins, and the reason it
  is or is not counted. Also the masks, and the metrics version.
- `<type>/dictated.yaml`: per task and level, the choices the prompt takes
  out of the model's hands, with the words of the prompt that do so and, where
  it can be said, the value a compliant output shows.

Present now: [website/](website/).

[tests/test_metrics_data.py](../tests/test_metrics_data.py) checks both files
against the extractors and the prompts: every extracted feature is declared,
the versions match, every quoted phrase is in its prompt. Raising an extractor
version or a prompt-set version makes it fail until the files are read again.

Filled by these tasks in [tasks.md](../tasks.md):

- T1.5: the website data files (done)
- T1.6: the metrics and the stability check, as a Python package here
- T2.8 and later: data files for the other project types
