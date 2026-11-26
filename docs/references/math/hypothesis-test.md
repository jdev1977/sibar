# Reference solution: hypothesis test on a small sample

Task: [prompts/math/hypothesis-test.yaml](../../../prompts/math/hypothesis-test.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/math/hypothesis-test.yaml](../../../checker/references/math/hypothesis-test.yaml).

The question at every level: does the mean of these eight measurements differ
from 50?

    50.8, 51.6, 49.7, 52.3, 51.1, 50.4, 52.0, 51.5

## Givens

| Given | Value |
| --- | --- |
| The eight measurements | As above (pin lengths in millimeters at L2) |
| The value tested | 50 (the target length, 50 mm, at L2) |
| The hypothesis, in words | "differs from 50": two-sided, about the mean |
| L2 only: test | Exact Wilcoxon signed-rank, two-sided, 1% level |
| L2 only: assumption | The lengths are spread symmetrically about their center |

## Assumptions

1. The eight values are independent measurements of one quantity.
2. H0: the mean is 50. H1: the mean is not 50. The question says "differs
   from", so the test is two-sided at every level. That is a given, not a
   default.
3. L0 and L1: the reference is the one-sample t test, which treats the
   values as roughly normal. No significance level is given; the reference
   uses 5%, and a decision is graded against the level the response states.
4. L2: the exact Wilcoxon signed-rank test at the 1% level, as dictated. The
   brief states that the lengths are symmetric about their center, so the
   center the test is about is the mean, and the question and the test agree.
5. L2: under H0 and symmetry each difference is as likely to be positive as
   negative, so all 2^8 = 256 patterns of signs on the ranks are equally
   likely. The exact two-sided p-value is twice the chance of a smaller rank
   sum no larger than the one seen.

## L0 and L1: one-sample t test

1. Sum of the values: 409.4. Mean: 409.4 / 8 = **51.175**.
2. Deviations from the mean: −0.375, 0.425, −1.475, 1.125, −0.075, −0.775,
   0.825, 0.325. Sum of their squares: 5.155.
3. Sample variance: 5.155 / 7 = 0.73643. Sample standard deviation:
   s = **0.8582**.
4. Standard error of the mean: 0.8582 / sqrt(8) = **0.3034**.
5. Test statistic: t = (51.175 − 50) / 0.3034 = **3.873**, with 8 − 1 = 7
   degrees of freedom.
6. Two-sided p-value: **0.0061**. (The 5% critical value of t on 7 degrees
   of freedom is 2.365, and the 1% value is 3.499; 3.873 is beyond both.)
7. Decision at the 5% level: **reject H0**. The mean differs from 50; the
   sample mean is above it.
8. 95% confidence interval for the mean: 51.175 ± 2.365 × 0.3034 =
   **50.46 to 51.89**, which does not contain 50.

## L2: exact Wilcoxon signed-rank test at the 1% level

1. Differences from 50, and the ranks of their sizes (1 = smallest). No
   difference is zero and no two sizes are equal, so no rank is shared.

   | Value | Difference | Rank |
   | --- | --- | --- |
   | 50.8 | +0.8 | 3 |
   | 51.6 | +1.6 | 6 |
   | 49.7 | −0.3 | 1 |
   | 52.3 | +2.3 | 8 |
   | 51.1 | +1.1 | 4 |
   | 50.4 | +0.4 | 2 |
   | 52.0 | +2.0 | 7 |
   | 51.5 | +1.5 | 5 |

2. Signed-rank sums: W+ = 3 + 6 + 8 + 4 + 2 + 7 + 5 = **35**; W− = **1**.
   (They add to 8 × 9 / 2 = 36.)
3. The smaller sum is 1. Of the 256 sign patterns, one gives a sum of 0 (no
   negative rank) and one gives a sum of 1 (only rank 1 negative), so
   P(W ≤ 1) = 2/256. Two-sided: p = 2 × 2/256 = 4/256 = **1/64 = 0.0156**.
4. Decision at the 1% level: 0.0156 is above 0.01, so **H0 is not rejected**.
   At the 1% level the sample does not show that the batch is off target.
   (The same data are significant at 5%. The most extreme result possible
   with 8 values, a smaller sum of 0, has p = 2/256 = 0.0078, so only a
   sample with every value on one side of 50 could reject at 1%.)

## Answers

| Quantity | L0 and L1 (t test) | L2 (exact Wilcoxon) |
| --- | --- | --- |
| Sample mean | 51.175 | 51.175 |
| Statistic | t = 3.873 on 7 degrees of freedom | W+ = 35, W− = 1 |
| Two-sided p-value | 0.0061 | 1/64 = 0.0156 |
| Decision | Reject at 5% (and at 1%) | Do not reject at 1% |

The L2 decision is the opposite of the L0 one. That is the point of the L2
direction.

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Sample mean | ±0.006 | Accepts 51.175, 51.18 and 51.17; the median, 51.3, fails |
| t statistic | ±0.03 | Accepts 3.87 and 3.9; grade its size, either sign |
| p-value, t test | ±0.0006 | Accepts 0.006 and 0.0061; the one-sided 0.0031 fails |
| p-value, exact Wilcoxon at L2 | ±0.0005 | The brief asks for 4 decimals: 0.0156 or 0.015625; 0.016 also passes, and the normal approximation, 0.0173, does not |
| Rank sums, ranks | exact | Whole numbers |
| Decision | no tolerance | It must follow from the response's own p-value and level |

## Alternatives accepted (L0 and L1)

The prompt names no test. A response is graded against the test it uses:

| Test the response uses | Two-sided p | At 5% | At 1% |
| --- | --- | --- | --- |
| One-sample t test (reference) | 0.0061 | reject | reject |
| Exact Wilcoxon signed-rank | 1/64 = 0.0156 | reject | do not reject |
| Exact sign-flip permutation test of the mean | 4/256 = 0.0156 | reject | do not reject |
| Wilcoxon, normal approximation (z = 2.380) | 0.0173 | reject | do not reject |
| Wilcoxon, normal approximation with continuity correction (z = 2.310) | 0.0209 | reject | do not reject |
| Sign test (7 of 8 above 50) | 18/256 = 0.0703 | do not reject | do not reject |

The sign test is a test of the median and has little power with 8 values.
It is listed so its arithmetic can be checked; a match is recorded as the
sign test, and its decision at 5% is the opposite of the reference's.

At L2 only the exact Wilcoxon value passes: the normal approximations
(0.0173, 0.0209) are not the exact test the brief asks for.

## Not accepted

| Value | What went wrong |
| --- | --- |
| p = 0.0031 | One-sided |
| p = 0.0001 | A z test: the normal distribution used in place of t on 7 degrees of freedom |
| s = 0.8027, t = 4.14 | Standard deviation with n, not n − 1, in the divisor |
| L2 p = 0.0078 | One-sided |
| L2 decision "reject" | 0.0156 compared with 5%, or the t test used |

## Checks

- The deviations from the mean add to zero, and their squares to 5.155.
- The p-value of the t test was found two ways: by integrating the density
  of t on 7 degrees of freedom numerically, and from the closed form for an
  odd number of degrees of freedom. Both give 0.006110.
- The exact Wilcoxon distribution was built by listing all 256 sign patterns.
  The sign-flip permutation test of the mean, a different statistic, gives
  the same 4/256.
- W+ + W− = 36 = n(n + 1)/2.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_hypothesis_test`).

## Note on the prompt

At L2 the question says "mean" while the Wilcoxon test is about the center
of a symmetric distribution. The brief states the symmetry, so the two are
the same point and the prompt is well posed.
