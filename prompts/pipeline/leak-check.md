# Leak check of the pipeline prompts (T2.2)

All 36 prompts in this folder were read as sent and judged against the rules
in [docs/leak-check.md](../../docs/leak-check.md): rules 1 to 6 from the
website check, and rules 7, 8, 10 to 14, 16 and 18, which this check added.

**Result: 29 pass as written, 7 rewritten.**

| Level | Pass | Rewritten |
| --- | --- | --- |
| L0 | 10 | 2 (csv-to-database B, image-resize B) |
| L1 | 10 | 2 (csv-to-database B, image-resize B) |
| L2 | 9 | 3 (csv-to-database A and B, image-resize B) |

No run had used these texts, so `prompt_set_version` stays "1" under the
pre-run rule in [README.md](README.md). The fingerprints in
[tests/test_pipeline_math_engineering_prompts.py](../../tests/test_pipeline_math_engineering_prompts.py)
were updated. The text before this check is in git at commit `9fa4ff6`.

## Rulings that apply to every task

The reasons are in [docs/leak-check.md](../../docs/leak-check.md).

1. **The data a task works on is subject** (rule 7). "A CSV file", "an API",
   "log files", "images" and "a database" are the plan's own words for the
   tasks. No L0 or L1 names a language, library, framework, tool, build
   service, scheduler or file layout.
2. **"Pipeline" stays** (rule 8). It is the type's name. It may suggest code
   in stages or a pipeline framework, so structure at L0 is the default for a
   request that says "pipeline". The image task says "code" and the CI task
   "workflow"; do not pool structure across those nouns as if they were one.
3. **"Write" against "Can you set up" stays** (rule 10). Neither names a
   technology, and the pair is the same in every cell. "Set up" may bring
   more text on installing and scheduling; that is part of wording
   sensitivity.
4. **An L2 names data formats and never a library** (rule 12).
5. **An L2 asks for a behavior as the outcome wanted** (rule 16).
6. **How an L2 pipeline is started, and paths the brief does not name, stay
   open** (rule 18).
7. **B says "please" once at L2 and never below it; A never does.** US
   spelling throughout. Both hold in all 36 prompts.

Phrases that were flagged and kept are listed under each task.

## csv-to-database

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The verb, "pipeline", and the plan's subject: a CSV file in, a database out. No language, library or database engine. |
| L0 B | rewritten | "Tidies up the data" is an idiom that leans to one locale, and "tidy" beside "data" is also the name of a data-cleaning convention tied to particular libraries. A had no such word. |
| L1 A | pass | Adds whose data it is (orders from a small business that sells online) and the purpose (the owner looks up past orders). |
| L1 B | rewritten | As L0 B. Otherwise the same facts as A. |
| L2 A | rewritten | The re-run line named the default behavior it moves away from ("adds nothing new"). |
| L2 B | rewritten | As L2 A, and "tidies up" and "need tidying" as at L0. |

Flagged and kept:

- "A database" (all levels) closes the choice between a database and files
  for this task. It is the plan's task. The engine stays open.
- "Look up past orders" (L1) implies that the data will be queried. That is
  the purpose; it names no storage and no interface.
- "Small" (L1) describes the business, not the pipeline.
- "No separate server to install" (L2) points toward an embedded database,
  the expected default. Kept under rule 14: a real need, written as a need.
  Do not read storage at L2 for this task.
- "Use only the language's standard library: nothing else is installed on
  that laptop" (L2) is the positive form this project uses in place of a
  named package. With "a database" it narrows the language, because few
  languages ship a database in their standard library. Do not read language
  at L2 for this task.
- "Drop a row that repeats an earlier row exactly" and "send a row ... to a
  rejects file" (L2) are cleaning rules, which are content of the brief.
- The stored forms (dates as 2027-03-02, emails in lower case, prices in
  cents) are what the data must look like. Two of them are close to what
  code does unasked; they are content, not direction.

Rewrites:

**L0 B**

Old:
> Can you set up a pipeline that takes a CSV file, tidies up the data and puts it into a database?

New:
> Can you set up a pipeline that takes a CSV file, cleans up the data and puts it into a database?

**L1 B**

Old:
> Can you set up a pipeline that takes the CSV file of orders a small business exports from its online sales, tidies up the data and puts it into a database? The owner wants to be able to look up past orders.

New:
> Can you set up a pipeline that takes the CSV file of orders a small business exports from its online sales, cleans up the data and puts it into a database? The owner wants to be able to look up past orders.

**L2 A**

Old:
> - Loading the same file a second time adds nothing new.

New:
> - Loading the same file a second time leaves the database as it was.

**L2 B**

Old:
> Can you set up a pipeline that takes the CSV file of orders we export from Brindlecote Tea, our small business selling loose-leaf tea online, tidies up the data and puts it into a database? I want to be able to look up past orders.

New:
> Can you set up a pipeline that takes the CSV file of orders we export from Brindlecote Tea, our small business selling loose-leaf tea online, cleans up the data and puts it into a database? I want to be able to look up past orders.

Old:
> The values need tidying in a few ways.

New:
> The values need cleaning up in a few ways.

Old:
> The database has to run on my laptop without a separate server to install, and loading the same file a second time shouldn't add anything new.

New:
> The database has to run on my laptop without a separate server to install, and loading the same file a second time should leave the database just as it was.

## daily-api-fetch

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The plan's task: fetch from an API every day and store the result. The service, the schedule and the storage are open. |
| L0 B | pass | "Pulls" for "fetches", "saves what it gets" for "stores it", "daily" for "every day". The same facts. |
| L1 A | pass | Adds the data (a city's air quality readings from its open data API), the audience (a local environmental group) and the purpose (follow pollution levels over time). |
| L1 B | pass | "In the area" for "local", "watch how pollution levels develop" for "follow ... over time". The same facts. |
| L2 A | pass | Every direction says what is wanted: one run under the machine's own scheduler, a missed day fetched later, a fixed retry rule, one CSV file per month, a second fetch that "leaves the files as they were", one log line per run. |
| L2 B | pass | The same facts in the same order as A. "Shouldn't change the files" states the outcome and names no default. |

Flagged and kept:

- "API" (all levels) is a technology word. It is the source the plan names,
  so it is subject (rule 7).
- "Every day" and "daily" (all levels) make a schedule necessary. That is the
  task; how it is scheduled stays open at L0 and L1.
- "Open data" (L1) may suggest that no key is needed. It describes the
  source. The L2 brief asks for a key in a header.
- "Follow ... over time" (L1) may suggest stored history or charts. It is the
  purpose and names no storage.
- The key (L2): the brief says where it goes and not where it comes from, so
  how a key is handled stays open at L2.
- "The machine's own scheduler" (L2) names no product. It may itself be the
  expected default, and 3 is a common number of retries. See the table at
  the end.
- "JSON" and "CSV" (L2) are data formats (rule 12).

## log-aggregation

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The plan's task: parse log files, aggregate the entries. The kind of log and the report are open. |
| L0 B | pass | "Reads through" for "parses", "adds up what they record" for "aggregates the entries". The same facts. |
| L1 A | pass | Adds the logs (access logs of a small website), the audience (the site's owner) and the purpose (most visited pages; when the site has problems). |
| L1 B | pass | "Get the most visits" and "when things go wrong". The same facts. |
| L2 A | pass | An invented line format with sample lines, the figures wanted, and three directions in positive form: one line at a time, a small package with separate parts and a command-line entry point, tests built on the sample lines. |
| L2 B | pass | The same facts in the same order; the sample lines are identical. |

Flagged and kept:

- "Access logs" (L1) may suggest a well-known server log format. It says
  which logs they are, which the purpose needs. The L2 format is invented,
  away from any well-known one.
- "See which pages" (L1) is the purpose, as "see how the day's distribution
  is going" was for the website dashboard. It names no report or chart.
- "Adds up" (B) is narrower than "aggregates" (a sum, not a median). Both
  leave open what is aggregated, and L1 and L2 say what the owner wants.
- "So a 10 GB log works on a laptop with little memory" (L2) is the need
  behind "one line at a time" (rule 16).
- "The 10 most requested paths" (L2) uses a common list length. It is part of
  the output wanted.

## image-resize

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | "Code" is the most neutral noun for the thing to be made: it suggests no structure, no language and no tool. |
| L0 B | rewritten | "A way" did not mean the same as A's "code". It left open whether the answer is code at all: a command for an existing tool or an app to install is also a way. |
| L1 A | pass | Adds the images (product photos for a pottery studio's website) and the purpose (they load quickly for customers). |
| L1 B | rewritten | As L0 B. Otherwise the same facts as A. |
| L2 A | pass | Describes the input and the output wanted, and gives five directions in positive form. "A photo that fails leaves the others unaffected" states the outcome. |
| L2 B | rewritten | "A way", as L0 B. And "one photo failing shouldn't stop the rest" named the default behavior (a run that stops), which A does not name. |

Flagged and kept:

- "Batch" (all levels) is the plan's word. It says there are many images, not
  how they are processed.
- "Load quickly" (L1) may suggest a smaller file format or stronger
  compression. It is the purpose.
- "Stored sideways with a flag that says how to turn them" and "camera and
  location details" (L2) describe the photos without naming the metadata
  standard, so the library stays open.
- "JPEG at quality 85" (L2) is the output wanted, and a data format (rule
  12). 85 is a value code often uses unasked; see the table at the end.
- "Changes nothing" and "touches nothing" (L2) define the dry run. They name
  no default.

Rewrites:

**L0 B**

Old:
> Can you set up a way to resize a batch of images?

New:
> Can you set up some code to resize a batch of images?

**L1 B**

Old:
> Can you set up a way to resize a batch of product photos? They're for a pottery studio's website, and they need to load quickly for its customers.

New:
> Can you set up some code to resize a batch of product photos? They're for a pottery studio's website, and they need to load quickly for its customers.

**L2 B**

Old:
> Can you set up a way to resize a batch of product photos? They're for our Saltmarsh Pottery website, and they need to load quickly for our customers.

New:
> Can you set up some code to resize a batch of product photos? They're for our Saltmarsh Pottery website, and they need to load quickly for our customers.

Old:
> One photo failing shouldn't stop the rest, and when it's done it should report how many photos were resized, skipped and failed, giving the reason for every failure.

New:
> If one photo fails, the rest should still go through, and when it's done it should report how many photos were resized, skipped and failed, giving the reason for every failure.

## ci-workflow

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The plan's task: a continuous integration workflow for a small software package. The build service, the package's language and the steps are open. |
| L0 B | pass | "A workflow that runs continuous integration" and "little" for "small". The same facts. |
| L1 A | pass | Adds the package (open-source, maintained by a few volunteers) and the purpose (every proposed change is checked before it is merged). |
| L1 B | pass | "Each change people propose" and "before it goes in". The same facts. |
| L2 A | pass | Says what the package is and what the workflow must do. Every check is in positive form, and no build service or tool is named. |
| L2 B | pass | The same facts in the same order as A. |

Flagged and kept:

- "Workflow" (all levels) is also the word some build services use for their
  own files. Kept under rule 8: it is the plan's noun. The service chosen at
  L0 is the default for a request that says "workflow".
- "Small" and "little" (all levels) describe the package, which is the
  subject, and are in the plan's task name.
- "Open-source" (L1) may suggest a public code host. It describes the
  package.
- "Merged" (A) against "goes in" (B) (L1): "merged" is the common word for
  the same event. No fact differs.
- "A library written in Go" (L2): the package's language is content in a CI
  brief (rule 13).
- "Linux, macOS and Windows" (L2) are where the package must work, and so a
  dictated test matrix, away from the expected single system.
- "The language's own formatter" and "its built-in vet check" (L2) name the
  checks without naming a command.
- The triggers and the branch name "main" (L2) are close to the expected
  default; see the table at the end.

## data-validation

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The plan's task: a data validation step for a pipeline. The data, the rules and the reporting are open. |
| L0 B | pass | "A step in a data pipeline that checks whether incoming data is valid". The same facts; "incoming" only says that the data arrives at the step. |
| L1 A | pass | Adds the pipeline (daily readings from weather stations run by volunteers) and the purpose (bad readings are caught before they reach the shared dataset). |
| L1 B | pass | The same facts as A. |
| L2 A | pass | Gives the input layout with sample data, the rules, the outputs and two directions in positive form: the rules in a separate file, every rule checked on every reading. |
| L2 B | pass | The same facts in the same order; the sample lines are identical. |

Flagged and kept:

- "Data validation" (all levels) is also the name of a kind of library. It is
  the plan's task.
- "Can edit without changing the code" (A) and "without touching the code"
  (B) (L2) are the need behind the separate rules file, in both wordings
  (rule 16). The file's name and format stay open.
- **What the L2 leaves open, and whether that is intended.** The brief does
  not say how the step is told which day to check, where `stations.csv` and
  the rejects file sit, what the rejects file and the rules file are called,
  or where the summary goes. That is intended (rule 18): arguments,
  configuration and naming are choices the plan records, both wordings leave
  the same things open, and the other five briefs do the same. The brief
  does fix what a fixture needs: the folder per day, the file per station,
  the header of `stations.csv`, and where valid readings go.
- "JSON Lines" and `stations.csv` (L2) are data formats (rule 12).
- The exit codes 0 and 2 (L2) are dictated. 2 is not the code a failing
  program returns unasked.
- The sample dates are in March 2026, before any run, so the rule "no later
  than the moment of the check" passes them. The sandbox should still use a
  fixed clock (see [README.md](README.md)).

## What each L2 dictates

For the extractors and the metrics. Everything else is left open at L2 as
well: the language (except where noted), the libraries, how the program is
started, configuration, naming, and the shape of the README.

| Task | Dictated at L2 | Close to the expected default |
| --- | --- | --- |
| csv-to-database | Standard library only, a test per cleaning rule, a rejects file with reasons, a re-run that changes nothing, a printed summary | An embedded database ("no separate server"); the language, narrowed by "standard library only" |
| daily-api-fetch | One run under the machine's own scheduler, catch-up of missed days, a fixed retry rule, one CSV file per month, a re-run that changes nothing, one log line per run | The machine's own scheduler may be the default itself; 3 retries is a common count |
| log-aggregation | An invented line format, compressed and plain files, one line at a time, a small package with a command-line entry point, parser tests | None found |
| image-resize | All processor cores, done photos skipped, a dry-run option, photos turned upright, details removed, failures kept apart, a summary with reasons | JPEG quality 85 |
| ci-workflow | A Go library, three operating systems, two Go releases, format and vet checks, a coverage gate, a changelog check on tags, a time limit, superseded runs canceled | Triggers on proposed changes and on pushes to main |
| data-validation | Rules in a separate file, every rule on every reading, warnings, a summary per station, an exit code with a threshold | None found |

## Choices not to read as defaults

| Task | Choice | Why |
| --- | --- | --- |
| csv-to-database | Database or files, at every level | "A database" is the task |
| csv-to-database | Storage engine and language, at L2 | A real need points to the expected default (rule 14) |
| ci-workflow | Build service, at every level | Read it as the default for a request that says "workflow" (rule 8) |
| ci-workflow | Triggers, at L2 | Dictated, and equal to the expected default |
| All but image-resize and ci-workflow | Structure, at L0 and L1 | Read it as the default for a request that says "pipeline" (rule 8) |
| daily-api-fetch | Scheduling, at L2 | Check against the pilot first |

The expected defaults are guesses until the pilot measures them.
