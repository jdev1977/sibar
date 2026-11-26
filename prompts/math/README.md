# Math and science prompts

Six math or science tasks, each at three levels of direction (L0, L1, L2) and
in two wordings (A, B): 36 prompts. One YAML file per task, in the format
described in [../README.md](../README.md). Written for task T2.1 in
[tasks.md](../../tasks.md), under the leak-check rules in
[docs/leak-check.md](../../docs/leak-check.md). The leak check itself is
T2.2; reference solutions are T2.3.

## The tasks

The plan lists seven example tasks. These six were kept because each asks for
a different kind of reasoning:

| File | Task | Kind of problem | Choices it brings out |
| --- | --- | --- | --- |
| [projectile-drag.yaml](projectile-drag.yaml) | Projectile with drag | Mechanics with a modeling choice | Drag law and constants assumed, closed form or numeric |
| [loan-amortization.yaml](loan-amortization.yaml) | Loan amortization | Finance arithmetic | Formula or month-by-month, rounding, how much of the schedule, currency |
| [titration-curve.yaml](titration-curve.yaml) | Titration pH curve | Chemistry with region shortcuts | Approximations, constants, points reported, drawn or tabulated |
| [hypothesis-test.yaml](hypothesis-test.yaml) | Hypothesis test on a small sample | Statistics | Which test, assumptions, sides, level, wording of the decision |
| [least-squares-fit.yaml](least-squares-fit.yaml) | Least-squares fit | Data fitting | Formula route, errors and residuals, precision, plot or code |
| [entropy-explanation.yaml](entropy-explanation.yaml) | Explain entropy to a student | Conceptual explanation | Framing, analogies, structure, length, formulas |

Left out: the pendulum equation. It is mechanics from Newton's second law
like the projectile, and its main open choice (an approximation assumed
silently or not) is already measured there, through the drag law.

## The levels

- **L0 Bare**: the request and its givens only, such as "Work out how a loan
  of 9000 at 7% annual interest is paid off in equal monthly payments over 5
  years."
- **L1 Brief**: L0 plus purpose and audience (who needs the answer and why).
  No numbers beyond the givens.
- **L2 Directed**: a full brief: context, stated constants and assumptions,
  what to report, and directions on method and presentation.

L0 and L1 name none of the plan's open choices for math: no method
(numerical, closed form, a named test or scheme), no presentation (table,
plot, headings, code, a named language), no precision or rounding, no unit
system, no rigor or length words, no analogy. The test file holds the word
list.

## Givens: numbers that every level carries

A checkable answer needs fixed numbers, but L0 must be the bare request. The
rule for both math and engineering:

1. **A task's givens are the numbers without which the question has no single
   answer, and nothing else.** They say nothing about method, format,
   precision or rigor.
2. **The givens are identical, word for word, at every level and in both
   wordings.** The test checks each given as an exact string in all six
   prompts. B may put them in a different order within a sentence.
3. **L0 and L1 hold no other number**, and no count written as a word.
4. **L2 may add numbers** (constants, extra outputs, a step size). It never
   changes a given.
5. **Where fixing the numbers would also fix an open choice, the task leaves
   the question open at L0 and L1 and is checkable at L2 only.** In this set
   that is the projectile: a single answer needs a drag law and its
   constants, and those are the assumptions to measure.
6. Where a standard assumption makes a question well posed (a nominal annual
   rate charged monthly; textbook acid constants; ordinary least squares), it
   is left unstated, and the reference solution (T2.3) states it. Whether a
   model states it too is recorded.

Units: where a given has units they are SI (m/s, mL, mol/L, degrees), the
convention of science in every locale. Numbers have no thousands separator.
The loan has no currency symbol at L0 and L1, so the currency stays open; L2
uses dollars, like the rest of the prompt sets.

## What is checkable at which level

| Task | Givens | L0 and L1 | L2 |
| --- | --- | --- | --- |
| projectile-drag | 25 m/s, 30° | Not graded: the answer depends on the drag law and constants assumed; record them | Range, time of flight, maximum height by the stated Heun scheme; range with no air (55.2 m) |
| loan-amortization | 9000, 7%, 5 years, equal monthly payments | Monthly payment 178.21; total interest about 1692.65 | Also the final payment and total interest under the cent-rounding rule, and the schedule |
| titration-curve | 25.0 mL of 0.100 M acetic acid, 0.100 M sodium hydroxide | Equivalence at 25.0 mL; initial pH about 2.87; half-equivalence pH about 4.74 to 4.76; equivalence pH about 8.72 | pH at the listed volumes with the stated constants |
| hypothesis-test | The eight values and 50 | t = 3.87 on 7 degrees of freedom, two-sided p about 0.006; exact Wilcoxon p = 1/64; both reject at 5% | Wilcoxon signed-rank sums 1 and 35, p = 1/64 = 0.0156, not significant at the dictated 1% level |
| least-squares-fit | The seven points | Slope 1.9464 (109/56), intercept 0.2143 (3/14) | Also standard errors, a 95% interval for the slope, residuals, R², spring constant about 514 N/m |
| entropy-explanation | None | Not checkable: rubric only | Not checkable: rubric only |

Each file repeats its own line of this table in a comment, for T2.3. Values
are approximate until T2.3 writes and re-solves the references and sets the
tolerances.

Notes for T2.3, where a brief leaves a convention to the reference:

- **Loan, interest rounding.** The L2 brief rounds each payment to the cent
  and lets the last payment absorb the difference, but does not say whether
  each month's interest is rounded to the cent before it is applied.
  Lenders usually round it; exact arithmetic does not. State the convention
  the reference uses, and set the tolerance on the final payment and the
  total interest wide enough to accept both (they differ by a few cents).
  At L0 and L1 there is no rounding rule, so grade the payment to the cent
  and the total interest within a few cents.
- **Projectile, maximum height.** "Maximum height" is the highest point of
  the path above the launch level. With a fixed step of 0.1 s the highest
  tabulated y can sit a little below the true peak. State whether the
  reference takes the highest tabulated value or interpolates the peak, and
  set the tolerance to accept both.
- **Hypothesis test.** The question says "mean" while the L2 test is about
  location; grade the L2 decision and p-value against the dictated test.

## L2 directions

Each L2 points method and presentation **away** from the expected default
for that task, and never names that default, not even to forbid it ("work it
by hand", not "no code"). The direction and the default are comments above
L2 in each file; the defaults are guesses until the pilot measures them.

| Task | Dictated at L2 | Close to the expected default |
| --- | --- | --- |
| projectile-drag | Quadratic drag and constants, Heun's method by hand at 0.1 s, table of steps, paragraphs with displayed equations, 3 significant figures | Quadratic drag is itself the likely assumption |
| loan-amortization | Payment found from the month-by-month balance with a stated check, cent rounding with last-payment adjustment, full dated schedule, answer first | None found |
| titration-curve | One charge-balance equation solved numerically, listed volumes, table to 2 decimals, the curve's shape described in words | None found |
| hypothesis-test | Exact Wilcoxon signed-rank, two-sided, 1% level, ranks listed, decision first, exact p-value | None found |
| least-squares-fit | Centered sums, table of sums, standard errors and interval, residuals, spring constant, 4 significant figures | None found |
| entropy-explanation | Energy-sharing framing, one counting example, about 300 words of paragraphs, second person, a closing question | None found |

## The wordings

- **A** is an imperative opening with the task's verb: "Work out", "Test",
  "Fit" or "Explain". At L2 it is a structured brief with labeled lines.
- **B** is a request opening "Can you" ("Can you figure out", "Can you test",
  "Can you find", "Can you explain"). At L2 it is prose in the asker's own
  voice and says "please" once.

Both wordings of a cell carry the same facts. As for websites, A and B
differ in mood, verb, length and, at L2, layout and voice: one bundled
wording factor.

## Invented content

The names (Pellmore Machine Works, a reader called Maya) are invented. Dates
are written the US way. No prompt uses text from the private catalogues.

## Versions

Each file has a `prompt_set_version`, "1" for all six. **Any change to the
text of any prompt in a file raises that file's version**; changes to
comments or `notes` do not. A change to a given also changes the reference
answer, so T2.3 must be told. The test pins each file's version and a
fingerprint of its texts; it cannot tell whether the version was raised, so
raise it in the same change. Before the first run, texts may be corrected
without a new version.

## Checks

`python -m pytest tests/test_pipeline_math_engineering_prompts.py` checks the
three Phase 2 sets together. For this set it checks, beyond the checks
listed for pipelines:

- every prompt holds its task's givens word for word, and L0 and L1 hold no
  other number and no count word;
- L0 and L1 use none of the listed math open choices;
- no L2 names a listed default (such as a plotting library, a named test it
  moves away from, or the tidiness picture of entropy);
- each file has comments for its givens and for what is checkable;
- the two L2 wordings have the same numbers (givens aside) in the same order.
