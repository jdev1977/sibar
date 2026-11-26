# Reference solution: least-squares fit

Task: [prompts/math/least-squares-fit.yaml](../../../prompts/math/least-squares-fit.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/math/least-squares-fit.yaml](../../../checker/references/math/least-squares-fit.yaml).

The question at every level: fit a straight line by least squares to

    (1, 2.3), (2, 4.1), (3, 5.8), (4, 8.2), (5, 9.9), (6, 11.6), (7, 14.1)

## Givens

| Given | Value |
| --- | --- |
| The seven points | As above |
| L2 only: meaning | x is the load on a spring in newtons; y is the stretch in millimeters |
| L2 only: errors | Each stretch reading has about the same uncertainty; the loads are exact |
| L2 only: asked for | Slope and intercept with standard errors; 95% interval for the slope; residuals; R²; the spring constant in N/m; 4 significant figures |

## Assumptions

1. Ordinary least squares of y on x: the line y = a + b x that makes the sum
   of squared vertical distances smallest. The line has an intercept; it is
   not forced through the origin.
2. All points have equal weight and the x values have no error. The L2 brief
   says both. At L0 and L1 they are the standard reading of "least squares".
3. L2: the standard errors use the residual variance s² = SSE / (n − 2), and
   the interval uses Student's t with n − 2 = 5 degrees of freedom.
4. L2: a residual is the measured y minus the fitted y.
5. L2: the slope is in mm/N. The spring constant is force over stretch,
   1 / slope in N/mm, which is 1000 / slope in N/m. The intercept (a small
   offset in the stretch readings) is not part of it.

## Method

With x̄ and ȳ the means, and the centered sums

    Sxx = Σ (x − x̄)²     Sxy = Σ (x − x̄)(y − ȳ)     Syy = Σ (y − ȳ)²

the least-squares line has

    slope b = Sxy / Sxx          intercept a = ȳ − b x̄

    SSE = Syy − b Sxy            s² = SSE / (n − 2)
    se(b) = s / sqrt(Sxx)        se(a) = s sqrt(1/n + x̄² / Sxx)
    R² = 1 − SSE / Syy

## Steps

1. Means: x̄ = 28 / 7 = 4; ȳ = 56.0 / 7 = 8.
2. Centered sums, one row per point:

   | x | y | x − x̄ | y − ȳ | (x − x̄)² | (x − x̄)(y − ȳ) | (y − ȳ)² |
   | --- | --- | --- | --- | --- | --- | --- |
   | 1 | 2.3 | −3 | −5.7 | 9 | 17.1 | 32.49 |
   | 2 | 4.1 | −2 | −3.9 | 4 | 7.8 | 15.21 |
   | 3 | 5.8 | −1 | −2.2 | 1 | 2.2 | 4.84 |
   | 4 | 8.2 | 0 | 0.2 | 0 | 0.0 | 0.04 |
   | 5 | 9.9 | 1 | 1.9 | 1 | 1.9 | 3.61 |
   | 6 | 11.6 | 2 | 3.6 | 4 | 7.2 | 12.96 |
   | 7 | 14.1 | 3 | 6.1 | 9 | 18.3 | 37.21 |
   | Sum | | 0 | 0.0 | **28** | **54.5** | **106.36** |

3. Slope: b = 54.5 / 28 = 109/56 = **1.9464**.
4. Intercept: a = 8 − 1.9464 × 4 = 3/14 = **0.2143**.
5. Residuals, measured minus fitted:

   | x | y | Fitted | Residual |
   | --- | --- | --- | --- |
   | 1 | 2.3 | 2.1607 | 0.1393 |
   | 2 | 4.1 | 4.1071 | −0.0071 |
   | 3 | 5.8 | 6.0536 | −0.2536 |
   | 4 | 8.2 | 8.0000 | 0.2000 |
   | 5 | 9.9 | 9.9464 | −0.0464 |
   | 6 | 11.6 | 11.8929 | −0.2929 |
   | 7 | 14.1 | 13.8393 | 0.2607 |

6. SSE = 106.36 − 1.9464 × 54.5 = 783/2800 = 0.27964 (the squared residuals
   add to the same). s² = 0.27964 / 5 = 0.055929; s = 0.23649.
7. Standard errors: se(b) = 0.23649 / sqrt(28) = **0.04469**;
   se(a) = 0.23649 × sqrt(1/7 + 16/28) = **0.1999**.
8. 95% interval for the slope: t for 5 degrees of freedom is 2.5706, so the
   half-width is 2.5706 × 0.04469 = 0.1149 and the interval is
   **1.832 to 2.061**.
9. R² = 1 − 0.27964 / 106.36 = **0.9974** (r = 0.9987).
10. Spring constant: the slope is 1.9464 mm per newton, so
    k = 1 / 1.9464 = 0.51376 N/mm = **513.8 N/m**. Its standard error is
    513.8 × 0.04469 / 1.9464 = 11.8 N/m, and the slope's interval turns into
    485.1 to 546.0 N/m.

## Answers

| Quantity | L0 and L1 | L2 (4 significant figures) |
| --- | --- | --- |
| Slope | 1.946 | 1.946 mm/N, standard error 0.04469 |
| Intercept | 0.2143 | 0.2143 mm, standard error 0.1999 |
| 95% interval for the slope | (if given) | 1.832 to 2.061 mm/N |
| Residuals | (if given) | 0.1393, −0.0071, −0.2536, 0.2000, −0.0464, −0.2929, 0.2607 mm |
| R² | 0.9974 (if given) | 0.9974 |
| Spring constant | (not asked) | 513.8 N/m |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Slope | ±0.005 | The givens have two or three significant figures: 1.95, 1.946 and 1.9464 pass |
| Intercept | ±0.005 | 0.21, 0.214 and 0.2143 pass |
| Standard errors | ±1% | 0.04469 or 0.0447; 0.1999 or 0.200 |
| Interval ends | ±0.002 | Accepts an interval built from rounded parts (1.946 − 0.115 = 1.831) |
| Residuals | ±0.005 each | Accepts two-decimal rounding and values worked from the rounded slope and intercept |
| R² | ±0.0005 | 0.997 and 0.9974 pass; r = 0.9987 does not |
| Spring constant | ±0.5% | 513.8 or 514; a value from the rounded slope, 513.9, passes |

The L2 brief asks for 4 significant figures. The tolerances are nevertheless
the same at every level: a right value given to three figures is still
right, and whether the precision asked for was given is read by the
extractors, not by the answer check. The nearest wrong slope (1.9667, the
line through the end points) is 0.02 away.

## Alternatives accepted

- **Residual sign.** If the response says a residual is fitted minus
  measured, every sign flips.
- **Interval for the spring constant.** If the response builds it as
  k ± t × se(k), it is 483.4 to 544.1 N/m, not 485.1 to 546.0.

## Not accepted

| Value | What went wrong |
| --- | --- |
| Slope 1.9893, intercept 0 | Line forced through the origin |
| Slope 0.5124 | x regressed on y |
| Slope 1.9667, intercept 0.3333 | Line through the first and last points |
| se(b) = 0.03777 | Residual variance divided by n, not n − 2 |
| Interval 1.859 to 2.034 | The normal value 1.96 used in place of t = 2.571 |
| R² = 0.9987 | The correlation coefficient r reported as R² |
| k = 1946 N/m | The slope multiplied by 1000 with no reciprocal taken |
| k = 502.7 N/m | Slope of the line through the origin |

## Checks

- The residuals add to zero, and so do the residuals weighted by x, as they
  must for a least-squares line with an intercept.
- SSE computed two ways agrees: from the residuals, and as Syy − b Sxy.
- The fitted line passes through the mean point (4, 8): 0.2143 + 1.9464 × 4
  = 8.000.
- The slope and intercept are exact fractions, 109/56 and 3/14, and were
  computed in exact arithmetic.
- The slope by the uncentered formula agrees:
  (7 × 278.5 − 28 × 56.0) / (7 × 140 − 28²) = 381.5 / 196 = 1.9464.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_least_squares_fit`).
