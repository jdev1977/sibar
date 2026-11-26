# Leak check for prompts

A prompt **leaks** when its wording steers a choice that the prompt is meant
to leave open. The project measures what a model chooses by default, so a
leak is counted as a default when it is really an instruction.

These rules were written for the website prompts (T1.2 in
[tasks.md](../tasks.md)) and are meant to be reused by T2.2 and by the Wave 2
leak checks (W2.x.2). The website log is
[prompts/website/leak-check.md](../prompts/website/leak-check.md).

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
  safety factor, a document structure.
