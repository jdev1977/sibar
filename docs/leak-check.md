# Leak check for prompts

A prompt **leaks** when its wording steers a choice that the prompt is meant
to leave open. The project measures what a model chooses by default, so a
leak is counted as a default when it is really an instruction.

These rules were written for the website prompts (T1.2 in
[tasks.md](../tasks.md)) and reused for the pipeline, math and engineering
prompts (T2.2). They are meant to be reused by the Wave 2 leak checks
(W2.x.2). The logs:

- [prompts/website/leak-check.md](../prompts/website/leak-check.md) (T1.2)
- [prompts/pipeline/leak-check.md](../prompts/pipeline/leak-check.md),
  [prompts/math/leak-check.md](../prompts/math/leak-check.md) and
  [prompts/engineering/leak-check.md](../prompts/engineering/leak-check.md)
  (T2.2)

Rules 1 to 6 and the two rulings below come from the website check. Rules 7
to 18, under
[Rules for pipeline, math and engineering prompts](#rules-for-pipeline-math-and-engineering-prompts),
were added by T2.2 and say how the same rules read where the open choices are
a language, a method or a unit system and not a look.

## How to run a check

1. Read every prompt as it is sent, not the YAML around it.
2. For each level, list what the prompt is allowed to say (rules below). Flag
   every other word or phrase.
3. Rule on each flagged phrase: keep it with a reason, or rewrite it.
4. Read the two wordings of each cell side by side and list the facts each
   one gives. The lists must be equal.
5. Log every prompt: pass or rewritten, the reason, and the old and new text
   of each rewrite.
6. Add each word that caused a rewrite to the word lists in the tests, so the
   ruling cannot be undone by a later edit.

Word lists catch known hints. Only reading catches new ones.

## What counts as a leak

**1. Words about the thing to be made are leaks. Words about the world it is
for are content.** "A sourdough bakery", "freelancers" and "a food bank"
describe a business or an audience. "Clean", "modern", "a landing page" and
"at a glance" describe the page. Only the second kind is a leak at L0 and L1.

Content carries associations too: a sourdough bakery suggests a warm,
handmade look. That is accepted, because it is what L1 exists to add, and L0
stays free of it. Record the association in the log, so that a shift from L0
to L1 is read as the effect of that content.

**2. The noun for the thing to be made is part of the task.** "Website", "web
page", "pricing page" and "web app" say what is asked for and keep the output
inside the project type. The noun stays the same at every level of a task and
means the same in both wordings.

**3. A phrase that is also the name of a pattern is a leak, even inside a
purpose.** "So they can compare the plans" shares its root with "comparison
table". "See at a glance" and "a quick overview" describe how a page reads.
Words to watch: compare, glance, overview, browse, showcase, gallery,
landing. A purpose that names no pattern stays: "keep track of assignments",
"pick the plan that suits them".

**4. When in doubt, use the two-way test.** Either the phrase adds nothing to
the task word ("at a glance" adds nothing to "dashboard"), and removing it
loses nothing; or it adds something, and what it adds is a direction. Both
ways the phrase goes.

**5. One locale for the whole set.** Spelling, date format, currency and units
hint at a locale, and a model may follow the hint in its copy, prices and
dates. L0 and L1 carry no locale hint at all, including idioms ("weigh up").
L2 uses one spelling, date and currency convention. Vocabulary that leans one
way in L2 content ("food parcels") is tolerated; the tests check spelling.

**6. No format, file or technology at any level**, unless an L2 states a real
constraint. Then it is written as a need ("it cannot rely on an internet
connection"), never as a technology.

## The levels

- **L0** is the request only: a verb, the noun for the thing, and the
  subject. No adjective that describes the thing, no purpose, no audience.
- **L1** adds purpose and audience and nothing else: who it is for, and what
  they need to do. The subject may be made specific where the purpose needs it
  (an invoicing tool, a repair event). No names, numbers or quoted text.
- **L2** is a full brief. It may dictate anything, under two rules:
  1. **The direction points away from the expected default for that task.**
     Check each dictated value against the default the author expects, and
     check the main color against the best-known model defaults as well
     (violet and indigo above all). A value in the same family as the default
     makes a model that obeys look like a model that did not move.
  2. **The brief says what it wants and never names the default it moves away
     from, not even to forbid it.** See the first ruling below.

## The two wordings

- The two wordings of a cell give **the same facts**. At L2 they also give
  them in the same order, and neither one fixes something the other leaves
  open, such as the order of the sections.
- Each wording keeps **the same voice in every task and at every level**. For
  websites, A is a command that opens with "Make" and is a labelled list at
  L2; B is a request that opens with "Can you build", is first-person prose at
  L2, and says "please" once at L2 and never below it.
- A hint must not sit in one wording only. If a phrase is rewritten in A,
  check its counterpart in B.

## Rulings

### Naming a default to forbid it: not accepted

Lines such as "no gradients", "not as separate cards" or 'no hype words such
as "seamless"' were rewritten to say what is wanted: "flat, solid color",
"one comparison table", "everyday words".

Reasons:

- L2 exists to show which defaults give way to a brief and which persist.
  When a default appears in an L2 output, that finding needs one explanation:
  the default beat the brief. If the brief names the default, there is a
  second explanation, that the prompt put the word there, and this design
  cannot tell the two apart.
- A ban tests whether a model obeys a blacklist. A positive direction tests
  whether the default gives way, which is the question the plan asks.
- The named defaults are guesses until the pilot measures them. A wrong guess
  written into a prompt is noise.
- The bans were uneven: gradients were banned in three tasks and not
  mentioned in three. Pooled over tasks, one feature would mix "banned" with
  "not mentioned".

How to write the positive form:

- Name the wanted value: "square corners", "flat, solid color".
- Use "only" or "alone" where the limit matters: "the only accent",
  "hairline rules alone", "words only".
- Give the principle in place of the examples: "claim only what a plan
  includes" in place of a list of hype words.

The rule covers the direction lines of a brief (tone, look, interface text).
It does not cover page content ("no gas appliances" in an event's house
rules), and it does not cover a functional limit that is not a measured
default ("no accounts or sign-in").

What this gives up: the realism of briefs that list dislikes, and the
finding "this default survives an explicit ban". If that finding is wanted
later, add it as a designed pair, the same L2 with and without the ban, under
a new prompt-set version, so the two explanations can be separated.

### Wording B is longer, a question and (at L2) prose: kept

A and B differ in mood, verb, length and, at L2, layout and voice. This was
kept as it is.

Reasons:

- The plan has two wordings "so that one phrasing does not define the
  result". Two wordings that differ in several ways cover more of how people
  ask than two that differ in one word.
- Two wordings cannot separate mood from verb from length whatever is done.
  Making them equal in length or mood would only make them more alike.
- Every cell has one A and one B, and each keeps its voice in every task, so
  wording is balanced across levels and tasks when the metrics pool them.
- What matters for a fair pair is equal information, and that was checked by
  reading.

What follows for the metrics (T1.5):

- Pool A and B with equal weight.
- Report the gap between A and B as **wording sensitivity**, one bundled
  factor. Do not read it as the effect of a question, of "build", of length
  or of politeness.
- Use that gap as a yardstick: a shift between levels that is no larger than
  the gap between wordings at those levels is not evidence that direction
  moved the choice.
- The bundle is wider at L2 (list against prose) than at L0, so do not
  compare the gap across levels as if it were one treatment.
- If the pilot shows a large gap on one dimension, re-read that wording pair.

## Notes for other tasks

- **Metrics (T1.5), L2 cells.** An L2 dictates some choices and leaves
  others open (often responsiveness, dark mode, accessibility, libraries,
  file structure). Read persistence of a default only on the choices the
  brief dictates, and only where the dictated value differs from the L0
  default the pilot measured. The website log lists what each L2 dictates and
  where a dictated value is still close to the expected default.
- **Pilot (T1.7, T1.9).** The expected defaults in the prompt files are
  guesses. After the pilot, compare each L2 direction with the measured L0
  defaults. Where they match, change the direction and raise the prompt-set
  version.
- **Renderer (T1.3).** Some L2 briefs hold dates (to-do due dates, an event
  date, a dashboard date). A page that reads the clock looks different
  depending on the day it is rendered: before March 2027 the to-do app shows
  nothing overdue, and later everything. Render with a fixed clock. Noon on
  March 9, 2027 shows three to-do tasks overdue, two due within 7 days and
  one later, with no task on the 7-day boundary; it is before the event and
  two days before the dashboard's date.
- **Other project types (T2.2, Wave 2).** The same rules apply with other
  words. A pipeline L2 says "standard library only", not "do not use" a named
  package. A math L2 says "solve it numerically", not "no closed form". The
  words to watch at L0 and L1 are the type's open choices in
  [plan.md](../plan.md): a language, a library, a method, a unit system, a
  safety factor, a document structure. Rules 7 to 18 below are what T2.2
  added for pipelines, math and engineering.

## Rules for pipeline, math and engineering prompts

Added by T2.2, which read all 108 prompts of the three Phase 2 types. Rules 1
to 6 stay as they are. Each rule here is a ruling on a question those rules
left open, with its reasons and with what it costs.

### At L0 and L1

**7. The data a task works on is subject. The build is the thing to be
made.** "A CSV file", "an API", "log files", "images" and "a database" are the
world a pipeline works in, and the plan names each task by them ("CSV to
cleaned table to database", "fetch an API daily"). They stay at every level.
Rule 6 is about the build: no language, library, framework, tool, build
service, scheduler or file layout at L0 and L1.

- Reason: without its input a pipeline task is not a task, as a website
  prompt is not one without its subject.
- Cost: where the task names the storage kind ("a database"), the choice
  between a database and files is closed for that task. The engine stays
  open, and the kind of storage is read on the task that only says "stores
  it" (daily-api-fetch).

**8. The plan's noun for the thing to be made stays, even where it leans
toward one value of an open choice.** This is rule 2. The nouns ruled on:

| Noun | Task | Leans toward | Ruling |
| --- | --- | --- | --- |
| "pipeline" | csv-to-database, daily-api-fetch, log-aggregation | Code in stages; a pipeline framework | Kept. It is the type's own name, as "website" is. |
| "code" | image-resize | Nothing | Kept, and now in both wordings (see below). |
| "workflow" | ci-workflow | Build services that call their own files workflows | Kept. It is the plan's noun ("CI workflow"); other words lean to other services ("pipeline", "job"). |
| "data validation step" | data-validation | Nothing found | Kept. |
| "pH curve" | titration-curve | A drawn curve | Kept. It is the plan's noun ("titration pH curve") and the chemistry name of the result, drawn or not. |
| "by least squares", "straight line" | least-squares-fit | Nothing: they are the question | Kept. A method that the plan's task name states is the task. What is measured is the route to it and what is reported with it. |
| "taking air resistance into account" | projectile-drag | Nothing: it names no drag law | Kept. |
| "gear ratio" | conveyor-gear-ratio | Gears | Kept. It is the plan's noun, and a ratio does not need gears. |
| "CAD file" | shelf-bracket | Nothing: it names no format | Kept. It says a file is wanted, as "website" says a site is wanted. |

- Reasons: the noun is the same at every level and in both wordings, so a
  shift between levels is not caused by it. A neutral substitute is another
  request ("how the pH changes" does not ask for the curve).
- Cost: the L0 share of the value a noun leans toward is the default **for a
  request worded with that noun**. The logs name the choices this touches:
  the plot for the titration, the build service for CI, the structure for
  "pipeline". Do not pool those cells with the other tasks as if the noun
  were silent.
- **The noun means the same in both wordings.** The image task's B said "a
  way", which leaves open whether the answer is code at all (a command for an
  existing tool, or an app to install). A said "code". B was rewritten to
  "some code".

**9. Givens: fixed numbers that every level carries.** Accepted for math and
engineering, under the rule in
[prompts/math/README.md](../prompts/math/README.md): a given is a number
without which the question has no single answer; it says nothing about
method, format, precision or rigor; it is the same string at every level and
in both wordings; L0 and L1 hold no other number.

- Reasons: the plan wants checkable answers for these two types, and a
  number that changes between levels would make L0 and L2 two different
  problems. Because the givens are equal at every level, they cannot cause a
  shift between levels.
- What a given closes or suggests, and how to read it:
  - **Unit system.** SI givens close it in four engineering tasks. It is
    measured on the two tasks without givens (shelf bracket, spring).
  - **Locale.** SI givens lean away from US practice. Standards cited,
    material grades, the motor speed (which shows a mains frequency) and the
    pump's supply are defaults for a request in SI units.
  - **Significant figures.** "25.0 mL", "0.100 M" and "1.0 °C/W" show a
    precision. Read the figures in an answer against the givens (more, the
    same or fewer), not as a bare count.
  - **A question in words can be a given.** "The mean ... differs from 50",
    "equal monthly payments" and "a straight line" are needed for a single
    answer. They close what they state: the test is two-sided and about the
    mean. Do not read those as defaults.
- No currency symbol and no thousands separator at L0 and L1.
- Where a given would fix a choice being measured, it is left out and the
  task is checkable at L2 only: the projectile's drag law, the bracket's and
  the spring's size and load.

**10. The verbs are part of the wording factor.** A opens "Write", "Work
out", "Size", "Design", "Test", "Fit" or "Explain". B opens "Can you set up",
"Can you figure out", "Can you work out", "Can you size" and so on. Kept, for
the reasons given for "Make" and "Can you build". "Set up" may bring more
installing and scheduling text than "Write"; "Work out" may bring more shown
working than "figure out". Both are inside the one bundled factor, wording
sensitivity.

**11. An idiom that leans to one locale goes, at every level.** B's "tidies
up the data" and "pick a pump to suit" were rewritten ("cleans up", "to
match"). Each of these types records a choice that shows a locale (currency,
mains frequency, a pump's power supply), so the reason for rule 5 is stronger
here. "Tidy" next to "data" is also the name of a data-cleaning convention
tied to particular libraries (rule 3).

### At L2

**12. A data format is content. A library is not.** An L2 brief may name the
formats the pipeline reads and writes (CSV, JSON, JSON Lines, gzip, JPEG,
PNG), with sample data. It never names a library, a tool, a build service or
a scheduler product.

- Reasons: a real brief says what the data looks like, and without it the
  two wordings cannot be checked for equal facts and the sandbox cannot build
  a fixture. A format is not the build: the language and the libraries stay
  open. An output format (one CSV file per month) is a dictated storage
  choice, which an L2 may give, and it points away from the expected
  database.
- Cost: a format narrows the libraries (JSON Lines needs a JSON reader, JPEG
  an imaging library). Read library choice at L2 within that limit.
- "Standard library only" is written as a need ("nothing else is installed
  on that laptop").

**13. In a CI brief the package's language is content.** The ci-workflow L2
says the package is a Go library. A workflow cannot be written without the
language, and a real request always gives it. It is a fact about the
subject, like "a sourdough bakery". It points away from the language a model
is expected to invent at L0 and L1, where the invented language is itself
recorded. The build service is named at no level.

**14. A real need may coincide with the expected default.** Keep it, written
as a need. Mark that choice as not readable at L2 for that task, and say
where the choice is read. Two cases:

- **csv-to-database, "no separate server to install".** Kept. The output
  must run on a laptop and in a sandbox with nothing installed, and the
  phrase names no technology, like the dashboard's "it cannot rely on an
  internet connection". It points toward an embedded database, the expected
  default, and "standard library only" narrows the storage and the language
  the same way. Storage and language are not read at L2 for this task.
  Storage that persists against a brief is read on daily-api-fetch, whose L2
  asks for monthly CSV files.
- **projectile-drag, drag that grows as the square of the speed.** Kept. At
  25 m/s no real object follows another law, and a brief that is wrong about
  the physics measures how a model handles an error, not a default (rule 17).
  The drag law is measured at L0 and L1, where it is open. At L2 the choices
  that move are the object and its constants, the method, the step and the
  presentation.

A dictated value that is close to a default without being a need is still
checked against the pilot, as for websites. The logs list each one.

**15. An assumption of the problem is content, unless the thing it sets aside
is a choice being recorded.** A math or engineering L2 must state assumptions
to have one answer. "Ignore spin and wind" stays: neither is a recorded
choice. Two lines were rewritten to say what holds:

- "Ignore the beam's own weight" became "the load at the free end is the only
  load on the beam". Self-weight is a recorded choice for that task.
- "Will not assume that the lengths follow a normal distribution" became
  "assumes only that the lengths are spread symmetrically about their
  center". Normality is the expected default assumption, and the new line
  states the one assumption the dictated test needs.

At L2 the brief gives the assumptions, so "assumptions stated or silent" is
read at L0 and L1 only.

**16. A behavior is asked for as the outcome wanted.** "Loading the same file
a second time leaves the database as it was"; "if one photo fails, the rest
should still go through". The earlier lines named the default behavior they
moved away from ("adds nothing new", "shouldn't stop the rest"), one of them
in wording B only. A purpose clause that states the need stays ("so a 10 GB
log works on a laptop with little memory", "can edit without changing the
code").

**17. A brief must be possible as written.** The shelf-bracket L2 asked for
screw holes in a flat laser-cut piece that stands square to the wall, with
the screws going into the wall. Such a piece can only have holes through its
face, so the screws could not be placed. A model given an impossible brief
either breaks one line of it or points out the fault, and the output then
measures that and not its defaults. The brief now has a wood strip on the
wall, and the bracket is screwed through its face into the side of the strip.

**18. How an L2 pipeline is started, and paths the brief does not name, stay
open.** The data-validation L2 gives the folder layout, the file names of the
input and where valid readings go. It does not say how the step is told
which day to check, where `stations.csv` and the rejects file sit, what the
rules file is called or where the summary goes. That is intended, and it is
the same in all six pipeline briefs.

- Reasons: arguments, configuration and naming are open choices the plan
  lists for pipelines, and a brief that fixed them would leave less to
  measure at L2. Both wordings leave the same things open.
- Cost: the sandbox (T2.7) cannot assume a command line. It runs an output's
  own tests and reads its entry point from the output.

### Notes for other tasks (T2.2)

- **Reference solutions (T2.3).** No given changed. Three L2 briefs changed:
  the shelf bracket now asks for the force on each screw (across the screw,
  from the load's moment about the screw pair) in place of a pull-out force;
  the hypothesis test states symmetry, under which the mean and the median
  agree; the cantilever says the tip load is the only load, which changes no
  number. The reference notes in the files and READMEs were updated.
- **Extractors and metrics (T2.8, T1.5).** Each log ends with a table of what
  each L2 dictates and which dictated values are close to a default. Each log
  also lists the choices not to read as defaults for a task (rules 8, 9 and
  14).
- **Pilot (T2.9).** The expected defaults are guesses. Where a measured L0
  default matches an L2 direction, change the direction and raise the
  prompt-set version.
