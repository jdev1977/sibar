# rubrics

Multiple-choice rubrics for choices that need reading, such as which method was
used or which assumptions were stated. One versioned file per project type
(`<type>.v1.yaml`), with an example of each answer for every item.

The format, the reasons for it, the items of each type, the versioning rule
and the calibration plan are in [docs/rubrics.md](../docs/rubrics.md).

| File | Holds |
|---|---|
| `pipeline.v1.yaml` | 20 items; 7 to 13 asked about one output |
| `math.v1.yaml` | 20 items; 5 to 11 asked about one output |
| `engineering.v1.yaml` | 24 items; 12 to 15 asked about one output. Its examples are invented and are not designs |
| `website.v1.yaml` | 6 items, for what the website extractors cannot read. In the calibration plan with the other three (accepted 2026-11-26; docs/rubrics.md, "Calibration (T2.5)"). Its tags are stored, but the website metrics do not read them yet ([analysis/README.md](../analysis/README.md#data-files)) |
| `<type>.v1.dictated.yaml` | The companion of each: which items each prompt takes out of the model's hands, in the entry format of `analysis/website/dictated.yaml` |

[tagger/rubric.py](../tagger/rubric.py) loads and checks them;
`python -m pytest tests/test_rubrics.py` runs the checks.

A version that has been used for a paid tagging run is frozen. A change to
anything the tagger is told goes into a new file, `<type>.v2.yaml`. Until the
first paid run a file may be corrected in place.

Filled by these tasks in [tasks.md](../tasks.md):

- T2.4: pipeline, math or science, and engineering rubrics, and a small
  website rubric (done)
- W2.x.3: Wave 2 rubrics
- W3.x: Wave 3 rubrics
