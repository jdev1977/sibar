# Reference solution: explain entropy

Task: [prompts/math/entropy-explanation.yaml](../../../prompts/math/entropy-explanation.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/math/entropy-explanation.yaml](../../../checker/references/math/entropy-explanation.yaml).

## What is checkable

**No level of this task has a checkable answer.** It asks for an explanation,
and an explanation has no single right text. It is scored by rubric only, at
L0, L1 and L2, and the checker records no correctness result for it.

The L2 brief states three counts for its example, and a response may repeat
them or add others. Those counts are facts, and this document confirms them
so that a wrong count in a response can be noticed. Checking them is not a
grade of the explanation.

## Givens

None at L0 and L1. The L2 brief gives the example: two groups of 3 atoms
share 6 packets of energy; with all 6 packets in one group there are 28 ways
to arrange them; with 3 packets in each group there are 10 × 10 = 100 ways;
across all splits there are 462 ways.

## Assumptions

1. The packets of energy are identical and the atoms can be told apart. An
   arrangement says how many packets each atom holds.
2. "All 6 packets in one group" means a named group holds all six. Counting
   either group would give 56.

## Method

The number of ways to place n identical packets on 3 atoms is the number of
ways to write n as an ordered sum of three whole numbers, zero allowed:

    W(n) = C(n + 2, 2) = (n + 2)(n + 1) / 2

For a split with n packets in the first group and 6 − n in the second, the
two groups are arranged independently, so the ways multiply:
W(n) × W(6 − n).

## Steps

| Packets on 3 atoms | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ways W(n) | 1 | 3 | 6 | 10 | 15 | 21 | 28 |

| Split (first group, second group) | Ways |
| --- | --- |
| 6 and 0 | 28 × 1 = 28 |
| 5 and 1 | 21 × 3 = 63 |
| 4 and 2 | 15 × 6 = 90 |
| 3 and 3 | 10 × 10 = 100 |
| 2 and 4 | 6 × 15 = 90 |
| 1 and 5 | 3 × 21 = 63 |
| 0 and 6 | 1 × 28 = 28 |
| All splits | 462 |

So the brief's three counts are right: 28, 100 and 462. The even split has
the most arrangements, 100 of 462 (21.6%), against 28 of 462 (6.1%) for all
the energy in one named group. That is the point the example is meant to
make: left alone, the energy is most often found spread out, because more
arrangements look that way.

## Answers

| Fact, if a response states it | Value |
| --- | --- |
| Ways with all 6 packets in one named group | 28 |
| Ways to place 3 packets on one group | 10 |
| Ways with 3 packets in each group | 100 |
| Ways with a 5 and 1 split, in a named order | 63 |
| Ways with a 4 and 2 split, in a named order | 90 |
| Ways across all splits | 462 |
| Share of all ways that are the even split | 21.6% |

Counts are exact. The share has a tolerance of ±0.5 percentage points, so
"about 22%" passes.

## Checks

- The seven splits add to 462.
- Counted another way: 6 packets on all 6 atoms at once is
  C(6 + 5, 5) = C(11, 5) = 462.
- Recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_entropy_explanation`).
