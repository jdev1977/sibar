# Pipeline prompts

Six pipeline tasks, each at three levels of direction (L0, L1, L2) and in two
wordings (A, B): 36 prompts. One YAML file per task, in the format described
in [../README.md](../README.md). Written for task T2.1 in
[tasks.md](../../tasks.md), under the leak-check rules in
[docs/leak-check.md](../../docs/leak-check.md). The leak check (T2.2) read
every prompt; its verdicts, reasons and rewrites are in
[leak-check.md](leak-check.md).

## The tasks

The plan lists exactly six example pipeline tasks, and all six are kept. Each
is a different kind of data work, so the model faces different choices:

| File | Task | Kind of work | Choices it brings out |
| --- | --- | --- | --- |
| [csv-to-database.yaml](csv-to-database.yaml) | CSV to cleaned table to database | Batch extract, clean, load | Parsing messy values, storage, bad rows, safe re-runs |
| [daily-api-fetch.yaml](daily-api-fetch.yaml) | Fetch an API daily and store results | Scheduled ingestion | Scheduling, keys, retries, gaps after a failed run, storage |
| [log-aggregation.yaml](log-aggregation.yaml) | Parse logs and aggregate | Text parsing and statistics | Line format, malformed lines, memory, report shape |
| [image-resize.yaml](image-resize.yaml) | Batch-resize images | File-by-file binary processing | Libraries, orientation and metadata, parallel work, partial failure |
| [ci-workflow.yaml](ci-workflow.yaml) | CI workflow for a small package | Build-service configuration | Service, triggers, test matrix, quality gates |
| [data-validation.yaml](data-validation.yaml) | Data validation step | One stage of a larger pipeline | Where rules live, how problems are reported, stopping the next stage |

## The levels

- **L0 Bare**: the request only, such as "Write a pipeline that cleans a CSV
  file and loads it into a database."
- **L1 Brief**: L0 plus purpose and audience: whose data it is and what they
  need to do with it. No names, numbers or formats beyond L0.
- **L2 Directed**: a full brief: invented names, the input format with sample
  data, the expected outputs, and engineering-practice directions.

L0 and L1 name none of the open choices the plan lists for pipelines: no
language, library, framework, storage engine, scheduler, build service,
structure (script, module, function), configuration, logging, retries, tests
or documentation. The test file holds the word list.

The task nouns are part of the task and stay the same at every level:
"pipeline", "continuous integration workflow", "data validation step". The
input formats the plan names are part of the task too ("a CSV file", "log
files", "an API", "images"); the output storage is left open ("a database").
For the image task the noun is "code" in both wordings, so that neither
"script" nor "tool" suggests a structure. (B first said "a way"; T2.2 ruled
that this left open whether the answer is code at all.) T2.2 looked at two
more words and kept both: "pipeline" may suggest staged code or a pipeline
framework, and B's "set up" may suggest configuration. Both are the same in
every task; [leak-check.md](leak-check.md) says how to read them.

## L2 directions

Each L2 points the open choices **away** from the expected default for that
task, and never names that default (not even to forbid it). The direction and
the default it moves away from are comments above L2 in each file; the
defaults are guesses until the pilot measures them.

| Task | Dictated at L2 | Close to the expected default |
| --- | --- | --- |
| csv-to-database | Standard library only, a test per cleaning rule, rejects file with reasons, safe re-run, printed summary | "No separate server to install" points to an embedded database |
| daily-api-fetch | Run once under the system scheduler, catch-up of missed days, fixed retry rule, monthly CSV files, safe re-run, one log line per run | The system scheduler may be the default itself; 3 retries is a common count |
| log-aggregation | Invented line format, gzip and plain files, line-by-line reading, a small package with a command-line entry point, parser tests | None found |
| image-resize | All processor cores, skip done photos, dry-run option, upright photos, metadata removed, failures isolated, summary | JPEG quality 85 |
| ci-workflow | Go library, three operating systems, two Go releases, format and vet checks, coverage gate, changelog check on tags, time limit, cancel superseded runs | Triggers on proposed changes and on pushes to main |
| data-validation | Rules in a separate editable file, every rule checked on every reading, warnings, per-station summary, exit code with a threshold | None found |

Left open at L2 as well: the language (except in ci-workflow), the libraries
(except "standard library only" in csv-to-database), and in most tasks the
configuration and logging style. How a program is started, and any path a
brief does not name, are open in all six briefs; T2.2 ruled that this is
intended (rule 18 in [docs/leak-check.md](../../docs/leak-check.md)), so the
sandbox cannot assume a command line.

In csv-to-database, "standard library only" narrows the language as well as
the storage, because few languages ship a database in their standard library.
Neither is read as a default at L2 for that task.

Two type-specific rulings, confirmed by T2.2 (rules 12 and 13 in
[docs/leak-check.md](../../docs/leak-check.md)):

- **A format at L2 describes data, not the build.** L2 briefs may name input
  and output formats (CSV, JSON, JSON Lines, gzip, JPEG), because a real
  brief says what the data looks like and what must come out. They never name
  a library or a tool to use; "standard library only" is written as a need
  ("nothing else is installed on that laptop").
- **The CI package's language is content.** A CI configuration cannot be
  written without knowing the language, and a real brief always says it. The
  ci-workflow L2 names Go, away from the most common scripting language. The
  build service is not named at any level.

## Running offline (T2.7)

No task needs the network to be attempted, and the sandbox runs every output
with no network:

- **daily-api-fetch.** L0 and L1 outputs call whatever service the model
  invents; with the network blocked they fail, and the record shows how
  (error handling is one of the open choices). Their own tests, usually with
  a fake response, run as written. The L2 brief names the reserved host
  `api.example.com` and gives the exact response, so the sandbox can serve
  that response from a local stub at that host. The URL is `https`, so the
  sandbox must both resolve `api.example.com` to the stub and make the
  program trust the stub's certificate (for example, a local certificate
  authority installed in the sandbox's trust store and the language's).
  Without both, an L2 output fails for a reason that is not the model's.
- **ci-workflow.** A workflow cannot run without its build service. The
  sandbox checks that the configuration parses and runs the commands it
  names against a fixture package that matches the L2 description. At L0 and
  L1 only parsing, and any package code the model writes, can be checked.
- **image-resize.** The sandbox supplies a folder of generated images that
  matches the L2 description. Most languages need an imaging library for
  this task, so whether an output runs depends on which libraries the sandbox
  provides; T2.7 should record that choice, because it affects every task in
  which a model reaches for a third-party library.
- **csv-to-database, log-aggregation, data-validation.** The L2 sample data
  gives a known result: the CSV rows load three, reject two and drop one
  repeat; the log lines hold four requests (one with status 500) and one
  malformed line; the readings hold one valid reading and one that breaks
  three rules and carries one warning.
- **data-validation, clock.** One rule says a reading may be no later than
  the moment of the check. The sample readings are dated March 2026, before
  any run, so they pass it; the sandbox should still run this task with a
  fixed clock, as the renderer does for websites, so the rule behaves the
  same on every run. The L2 brief gives the input layout (one folder per
  day, one file per station), the header of `stations.csv` and where valid
  readings go, so a fixture can be built from it.

## The wordings

- **A** is an imperative opening "Write". At L2 it is a structured brief with
  labeled lines and lists.
- **B** is a request opening "Can you set up". At L2 it is prose in the
  client's own voice and says "please" once.

Both wordings of a cell carry the same facts. Sample data (CSV rows, JSON
records, log lines) is identical in both, line for line. As for websites, A
and B differ in mood, verb, length and, at L2, layout and voice: one bundled
wording factor.

## Invented content

Every name is invented (Brindlecote Tea, Quellmouth, Fernhollow Recipes,
Saltmarsh Pottery, tallyfold, Ostley Valley). Emails and hosts use
`example.com`; the addresses in the log sample come from the ranges reserved
for documentation. Dates are in March 2027 (March 2026 in data-validation,
see above) and written the US way; prices use
dollars. No prompt uses text from the private catalogues.

## Versions

Each file has a `prompt_set_version`, "1" for all six. **Any change to the
text of any prompt in a file raises that file's version**, as for websites;
changes to comments or `notes` do not. The test pins each file's version and
a fingerprint of its texts, prints the new values when a text changes, and
cannot tell whether the version was raised: raise it in the same change.
Before the first run, texts may be corrected without a new version (for
example after the T2.2 leak check), as was done for websites.

## Checks

`python -m pytest tests/test_pipeline_math_engineering_prompts.py` checks the
three Phase 2 sets together. For this set it checks:

- 6 tasks x 3 levels x 2 wordings, each file's version and fingerprint, and
  an L2 direction comment in each file;
- every prompt names its task's subject;
- L0 and L1 use none of the listed pipeline open choices, and hold no
  number, count word, quoted text, email or URL;
- no L2 writes a ban ("do not", "avoid", "instead of", "rather than",
  "never") or names a listed default (such as a data-frame library or a
  scheduler);
- the rulings of the leak check: every prompt names the same thing to be
  made in both wordings ("pipeline", "code", "workflow", "step"), no prompt
  uses an idiom that leans to one locale, and no L2 names the behavior it
  moves away from (such as "shouldn't stop");
- US spelling; reserved emails, hosts and addresses only;
- A opens "Write" and B "Can you", with "please" once in each L2 B only;
- each level is longer than the one before;
- the two wordings of a cell differ in phrasing (sample-data lines left out
  of the comparison), and the two L2 wordings have the same numbers, emails
  and quoted text in the same order and the same invented names.

The word lists catch known hints; only reading catches new ones.
