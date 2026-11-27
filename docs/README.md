# docs

Project documents. Present now:

- [secrets.md](secrets.md): the secret scan and key handling (X1)
- [record-format.md](record-format.md): the run record format (T0.4)
- [ledger.md](ledger.md): the cost ledger and budget cap (X3)
- [runner.md](runner.md): the generation runner and its live check (T0.5)
- [terms/](terms/README.md): what each provider's terms allow for storing,
  sharing and publishing outputs, and the decisions left to the Human (T0.7)
- [renderer.md](renderer.md): offline screenshots of generated pages, their
  isolation and limits (T1.3)
- [leak-check.md](leak-check.md): the rules for checking prompts for leaks,
  written in T1.2 and reused by T2.2 and the Wave 2 leak checks
- [extractors.md](extractors.md): the extractor interface and the twelve
  website extractors, feature by feature (T1.4)
- [metrics.md](metrics.md): the fingerprint tables, convergence, prompt
  sensitivity, intervals, the stability rule and their worked examples (T1.5)
- [analysis/README.md](../analysis/README.md): how to compute them from
  record files, and the stability check command (T1.6)
- [references/](references/README.md): worked reference solutions for the
  math and engineering tasks, with assumptions and tolerances (T2.3). The
  engineering ones are study data, not designs
- [rubrics.md](rubrics.md): the rubric format, the items of each type, the
  split with the extractors, the versioning rule and how to calibrate the
  tagger (T2.4)
- [tagger/README.md](../tagger/README.md): the tagger, its money safety and
  crash recovery, the agreement command and the human tag file (T2.6)
- [sandbox.md](sandbox.md): running generated code: setup, use, outcomes,
  boundaries and their tests, the threat model and what it does not defend,
  task fixtures and measurements (T2.7)
- [webdev-arena.md](webdev-arena.md): the WebDev Arena dataset's licence, the
  decision it leaves to the owner, and the importer (T5.2)

Added by later tasks in [tasks.md](../tasks.md):

- T0.6: `cost.md`, cost estimate
- T1.9: `pilot.md`, pilot report
- T2.5: `tagger.md`, tagger calibration
- T4.1: `scoring.md`, scoring design
