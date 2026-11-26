# Leak check of the math and science prompts (T2.2)

All 36 prompts in this folder were read as sent and judged against the rules
in [docs/leak-check.md](../../docs/leak-check.md): rules 1 to 6 from the
website check, and rules 8 to 10, 14 and 15, which this check added.

**Result: 32 pass as written, 4 rewritten.**

| Level | Pass | Rewritten |
| --- | --- | --- |
| L0 | 12 | 0 |
| L1 | 11 | 1 (hypothesis-test B) |
| L2 | 9 | 3 (hypothesis-test A and B, loan-amortization B) |

No run had used these texts, so `prompt_set_version` stays "1" under the
pre-run rule in [README.md](README.md). The fingerprints in
[tests/test_pipeline_math_engineering_prompts.py](../../tests/test_pipeline_math_engineering_prompts.py)
were updated. The text before this check is in git at commit `9fa4ff6`.

**No given changed**, so no reference answer for L0 or L1 changes. One L2
brief changed in a way the reference solution (T2.3) should know: the
hypothesis test now states that the lengths are symmetric about their center.
The dictated test, its level and its result are the same.

## Rulings that apply to every task

The reasons are in [docs/leak-check.md](../../docs/leak-check.md).

1. **Givens stay** (rule 9). Every prompt of a task holds the same numbers,
   word for word, and L0 and L1 hold no other number. Read significant
   figures in an answer against the precision of the givens.
2. **A question in words can be a given** (rule 9): "the mean ... differs
   from 50", "equal monthly payments", "a straight line".
3. **The plan's noun stays** (rule 8): "pH curve", "least squares", "air
   resistance".
4. **The verbs stay** (rule 10). A opens "Work out", "Test", "Fit" or
   "Explain"; B opens "Can you figure out", "Can you test", "Can you find" or
   "Can you explain". "Work out" may bring more shown working than "figure
   out"; that is part of wording sensitivity. Neither is marked for a
   locale.
5. **An assumption of the problem is content, unless what it sets aside is a
   recorded choice** (rule 15). At L2 the brief gives the assumptions, so
   "assumptions stated or silent" is read at L0 and L1 only.
6. **B says "please" once at L2 and never below it; A never does.** US
   spelling throughout. Both hold in all 36 prompts.

Phrases that were flagged and kept are listed under each task.

## projectile-drag

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The verb, the plan's task (the range of a projectile with air resistance) and the two givens. No drag law, object, method or precision. |
| L0 B | pass | "How far away it lands" for "range". The same facts. |
| L1 A | pass | Adds the audience (a first-year physics student) and the purpose (learning how air resistance affects motion). |
| L1 B | pass | "What air resistance does to moving objects". The same facts. |
| L2 A | pass | Dictates the object and its constants, the method, the step, a table, paragraphs and the precision, each in positive form ("by hand", "plain paragraphs"). |
| L2 B | pass | The same facts in the same order as A. |

Flagged and kept:

- "Taking air resistance into account" (all levels) is the plan's task
  ("projectile with drag"). It names no drag law.
- The givens, 25 m/s and 30° (all levels), do not make L0 and L1 checkable,
  because the drag law is open there. They keep the problem the same at
  every level.
- "A first-year physics student" (L1) may suggest the simplest drag law, the
  one with a closed form. It describes the audience. A shift in the drag law
  from L0 to L1 includes this association.
- "Drag force proportional to the square of the speed" (L2) is likely the L0
  default too. Kept under rule 14: at this speed no real object follows
  another law. Do not read the drag law at L2.
- "Ignore spin and wind" (L2) is an assumption of the problem (rule 15).
  Neither is a recorded choice.
- "The range the same kick would have with no air at all" (L2) is an output
  the brief asks for.
- "Soccer" (L2) is US vocabulary in dictated content, in both wordings.

## loan-amortization

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The request and its givens. "How ... is paid off" leaves open what is reported: the payment, a schedule, the total interest. |
| L0 B | pass | The same givens and the same question. |
| L1 A | pass | Adds the audience (a first-time car buyer) and the purpose (whether they can afford it). |
| L1 B | pass | "Someone buying their first car who is trying to decide if they can afford it". The same facts. |
| L2 A | pass | Dictates how interest is charged, the dates, the rounding, the outputs, the method ("building the balance month by month") and the order of the answer, each in positive form. |
| L2 B | rewritten | "The lender adds a twelfth of the yearly rate to whatever is still owed" did not say plainly what the rate is charged on. A does ("on the balance still owed"). |

Flagged and kept:

- "Paid off" (all levels) is the plan's task in plain words (amortization).
- "Equal monthly payments" (all levels) is a given in words: without it
  there is no single answer. It says nothing about how the payments are
  shown.
- "9000" (L0 and L1) has no currency symbol and no thousands separator, so
  the currency stays open below L2.
- "7% annual interest" leaves open whether the rate is nominal or
  effective. The standard reading is left unstated on purpose
  ([README.md](README.md), rule 6 of the givens).
- "Car buyer" (L1) may bring car-loan habits and advice about affording it.
  It describes the audience and the purpose.
- "$" and the US dates (L2) follow the set's one locale.

Rewrites:

**L2 B**

Old:
> Every month the lender adds a twelfth of the yearly rate to whatever is still owed.

New:
> Every month the lender charges interest at a twelfth of the yearly rate on whatever is still owed.

## titration-curve

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The request and its givens. No approximation, constant, list of points or presentation. |
| L0 B | pass | "The pH curve you get when ... is added to ..." describes the same titration without the word. The same givens. |
| L1 A | pass | Adds the audience (a chemistry student) and the purpose (about to do this titration in a lab class; wants to know what to expect). |
| L1 B | pass | "In a lab session shortly" and "what will happen". The same facts. |
| L2 A | pass | Dictates the constants, the points, one equation solved numerically, a table and a paragraph on the curve's shape, each in positive form. |
| L2 B | pass | The same facts in the same order as A. |

Flagged and kept:

- "pH curve" (all levels) may suggest a drawn curve, and whether a plot is
  offered is a recorded choice. Kept under rule 8: it is the plan's noun and
  the chemistry name of the result. For this task, read "plot offered" as
  the default for a request that says "curve", and do not pool it with the
  other five tasks. How the curve is given (code that draws it, a table, a
  description) stays open at L0 and L1.
- "25.0 mL" and "0.100 M" (all levels) show three significant figures.
- "Acetic acid" is the common name used in chemistry everywhere; some school
  systems teach another name. Kept: it is the name both wordings and every
  level use.
- "What to expect" (L1) may bring talk of indicators and color change. It is
  the purpose.
- "So that a single method covers the whole curve" (L2) gives the reason for
  the method and names no other method.

## hypothesis-test

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The request, the hypothesis and the eight values. No test, level, assumption or wording of the decision. |
| L0 B | pass | "Have a mean that differs from 50". The same facts. |
| L1 A | pass | Adds the audience (a quality-control technician), where the values come from (a new batch of parts) and the purpose (deciding whether the batch is on target). |
| L1 B | rewritten | "Meets its target" can be read as one-sided (reaches at least the target). A's "on target" cannot. |
| L2 A | rewritten | "Will not assume that the lengths follow a normal distribution" named the expected default assumption in order to forbid it. |
| L2 B | rewritten | As L2 A ("not willing to assume the lengths are normally distributed"). |

Flagged and kept:

- "The mean ... differs from 50" (all levels) is the hypothesis, a given in
  words (rule 9). It is two-sided and about the mean. Do not read "two-sided"
  as a default here, and read the choice of test as a choice among tests of
  a mean.
- "A sample" (L1 B) is the plan's own word for the data and adds no fact.
- "A new batch of parts" (L1) may suggest millimeters and a tolerance. It
  says where the values come from. The values have no units below L2.
- The Wilcoxon test at the 1% level (L2) points away from the expected t
  test at 5%, and the decision changes with it.
- "Mean" beside a test of location (L2): with the lengths stated to be
  symmetric about their center, the mean and the median are the same point,
  so the question and the dictated test agree.

Rewrites:

**L1 B**

Old:
> They're a sample a quality-control technician pulled from a fresh batch of parts, to judge whether that batch meets its target.

New:
> They're a sample a quality-control technician pulled from a fresh batch of parts, to judge whether that batch is on target.

**L2 A**

Old:
> - The technician will not assume that the lengths follow a normal distribution.

New:
> - The technician assumes only that the lengths are spread symmetrically about their center.

**L2 B**

Old:
> I'm not willing to assume the lengths are normally distributed.

New:
> All I'm willing to assume about the lengths is that they're spread symmetrically around their center.

Why the new line states symmetry: a line that only said less ("makes few
assumptions") would give no fact. Symmetry about the center is the one
assumption the dictated test needs, so the brief says what holds, as rule 15
asks, and names no distribution.

## least-squares-fit

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The request and the seven points. No formula route, no list of what to report, no precision. |
| L0 B | pass | "The least-squares straight line through these points". The same facts. |
| L1 A | pass | Adds the audience (a student), where the points come from (a physics lab) and the purpose (the line is for a lab report). |
| L1 B | pass | The same facts as A. |
| L2 A | pass | Says what x and y are, what to report, and how: centered sums, a table of sums, 4 significant figures, one sentence per step. All in positive form. |
| L2 B | pass | The same facts in the same order as A. "Stiffness" for "spring constant". |

Flagged and kept:

- "By least squares" and "straight line" (all levels) name a method and a
  model. They are the plan's task and are needed for a single answer (rules
  8 and 9). The route to the line and what is reported with it stay open.
- "A lab report" (L1) may bring uncertainties and a plot. It is the purpose.
- The points have no units below L2.

## entropy-explanation

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The verb and the subject, as short as the plan's website example. |
| L0 B | pass | "Explain what entropy is". The same request. |
| L1 A | pass | Adds the audience (a teenager who has just started chemistry) and the purpose (follow the word when it comes up in class). |
| L1 B | pass | "New to chemistry", "keep running into the word at school". The same facts. |
| L2 A | pass | Names the reader, one framing, one example with its counts, a length, a voice and a closing question, each in positive form. |
| L2 B | pass | The same facts in the same order as A. |

Flagged and kept:

- The plan's task says "to a student". The audience is added at L1, as for
  every task, so L0 is the bare word.
- "Teenager" and "chemistry" (L1) steer the framing and the level of the
  language. That is what L1 adds. "Teenager" names an age and no school
  system.
- "Has not met calculus" (A) and "calculus is new to her" (B) (L2) are read
  as the same fact about the reader: she has not learned it.
- "The number of ways energy can be shared out among particles" (L2) is the
  framing wanted. No other picture of entropy is named.
- "Shared out" (L2) is vocabulary in dictated content, which rule 5
  tolerates.

## What each L2 dictates

For the extractors and the metrics. Everything else is left open at L2 as
well, such as notation and whether code is offered beside the working.

| Task | Dictated at L2 | Close to the expected default |
| --- | --- | --- |
| projectile-drag | The object and its constants, drag that grows as the square of the speed, Heun's method by hand at 0.1 s, a table of steps, paragraphs with each equation on its own line, 3 significant figures | The drag law |
| loan-amortization | The payment found from the month-by-month balance, with a stated check; cent rounding with the last payment absorbing the difference; a full dated schedule; a two-sentence answer first | None found |
| titration-curve | The constants, the listed volumes, one charge-balance equation solved numerically, a table to 2 decimal places, the curve's shape in a paragraph | None found |
| hypothesis-test | The exact Wilcoxon signed-rank test, two-sided, at the 1% level; symmetry as the one assumption; ranks listed; the decision first; the exact p-value | Two-sided (it is the question at every level) |
| least-squares-fit | Centered sums, a table of sums, standard errors and an interval for the slope, every residual, a spring constant, 4 significant figures, one sentence per step | None found |
| entropy-explanation | The energy-sharing framing, one counting example, about 300 words of paragraphs, the second person, a closing question | None found |

## Choices not to read as defaults

| Task | Choice | Why |
| --- | --- | --- |
| titration-curve | Plot offered, at every level | Read it as the default for a request that says "curve" (rule 8) |
| hypothesis-test | Number of sides, at every level | The question is two-sided (rule 9) |
| hypothesis-test | Kind of test, at L0 and L1 | Read it as a choice among tests of a mean (rule 9) |
| least-squares-fit | Fitting method, at every level | "Least squares" is the task (rule 8) |
| projectile-drag | Drag law, at L2 | A real need equal to the expected default (rule 14) |
| All tasks with givens | Significant figures as a bare count | Read them against the precision of the givens (rule 9) |
| All tasks | Assumptions stated or silent, at L2 | The brief gives them (rule 15) |

The expected defaults are guesses until the pilot measures them.
