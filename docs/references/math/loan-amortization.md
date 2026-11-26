# Reference solution: loan amortization

Task: [prompts/math/loan-amortization.yaml](../../../prompts/math/loan-amortization.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/math/loan-amortization.yaml](../../../checker/references/math/loan-amortization.yaml).

The question at every level: how is a loan of 9000 at 7% annual interest paid
off in equal monthly payments over 5 years?

## Givens

| Given | Value |
| --- | --- |
| Amount borrowed | 9000 (no currency at L0 and L1; dollars at L2) |
| Annual interest rate | 7% |
| Term | 5 years, in equal monthly payments |
| L2 only: loan starts | March 1, 2027 |
| L2 only: first payment due | April 1, 2027 |
| L2 only: rounding | Each payment to the cent; the last payment absorbs the difference |

## Assumptions

1. The 7% is a nominal annual rate charged monthly, so the rate per month is
   i = 0.07 / 12 = 0.58333%. The L2 brief says so ("one twelfth of the annual
   rate"). At L0 and L1 it is the standard reading of a quoted loan rate.
2. There are n = 60 payments, each made at the end of a month, the first one
   month after the loan starts.
3. No fees, and no payment is missed or made early.
4. L2, interest rounding: each month's interest is rounded to the cent (half
   a cent rounds up) before it is applied, as lenders do. The brief does not
   say this. The other reading, exact interest with only the last payment
   rounded, is worked below as well; for this loan the two give the same last
   payment and the same total.
5. L2, last payment: the balance left after 59 payments, plus the last
   month's interest on it.

## Method

Follow the balance month by month. If B is the balance at the start of a
month, the interest for the month is B × i, and after a payment P the balance
is B × (1 + i) − P. Starting from 9000, the balance after k payments is

    B_k = 9000 (1 + i)^k − P ((1 + i)^k − 1) / i

The equal payment is the P that makes B_60 = 0:

    P = 9000 × i / (1 − (1 + i)^−60)

This is the same number the L2 brief asks to be found by building the balance
month by month and choosing the payment that brings it to zero. A search does
it without the formula: 178.21 a month leaves 0.06 still owed after 60
payments, and 178.22 overpays by 0.66, so the exact payment lies between
them, much nearer 178.21.

## Steps

1. Monthly rate: i = 0.07 / 12 = 0.0058333.
2. Growth over the term: (1 + i)^60 = 1.417625, so (1 + i)^−60 = 0.705405.
3. Payment: P = 9000 × 0.0058333 / (1 − 0.705405) = 52.50 / 0.294595
   = **178.2108**, which is **178.21** to the cent.
4. With no rounding rule (L0 and L1): total paid = 60 × 178.2108 = 10 692.65,
   and total interest = 10 692.65 − 9000 = **1692.65**.
5. With the L2 rule: 59 payments of 178.21, then a last payment that clears
   the balance. Month 1: interest 9000 × 0.0058333 = 52.50; principal
   178.21 − 52.50 = 125.71; balance 8874.29. Carrying on (full schedule
   below), the balance after payment 59 is 177.24, the last month's interest
   is 1.03, and the last payment is 177.24 + 1.03 = **178.27**.
6. L2 totals: total paid = 59 × 178.21 + 178.27 = 10 692.66; total interest
   = **1692.66**.

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Monthly payment | 178.21 | $178.21 |
| Last payment | (not asked) | $178.27, due March 1, 2032 |
| Total interest | 1692.65 | $1692.66 |
| Total paid | 10 692.65 | $10 692.66 |
| Schedule | (not asked) | 60 rows, April 1, 2027 to March 1, 2032 |

Whether the buyer can afford it (L1 and L2) is a judgment and is not graded.

## The L2 schedule

Interest rounded to the cent each month. Amounts in dollars.

| No. | Date | Payment | Interest | Principal | Balance |
| --- | --- | --- | --- | --- | --- |
| 1 | April 1, 2027 | 178.21 | 52.50 | 125.71 | 8874.29 |
| 2 | May 1, 2027 | 178.21 | 51.77 | 126.44 | 8747.85 |
| 3 | June 1, 2027 | 178.21 | 51.03 | 127.18 | 8620.67 |
| 4 | July 1, 2027 | 178.21 | 50.29 | 127.92 | 8492.75 |
| 5 | August 1, 2027 | 178.21 | 49.54 | 128.67 | 8364.08 |
| 6 | September 1, 2027 | 178.21 | 48.79 | 129.42 | 8234.66 |
| 7 | October 1, 2027 | 178.21 | 48.04 | 130.17 | 8104.49 |
| 8 | November 1, 2027 | 178.21 | 47.28 | 130.93 | 7973.56 |
| 9 | December 1, 2027 | 178.21 | 46.51 | 131.70 | 7841.86 |
| 10 | January 1, 2028 | 178.21 | 45.74 | 132.47 | 7709.39 |
| 11 | February 1, 2028 | 178.21 | 44.97 | 133.24 | 7576.15 |
| 12 | March 1, 2028 | 178.21 | 44.19 | 134.02 | 7442.13 |
| 13 | April 1, 2028 | 178.21 | 43.41 | 134.80 | 7307.33 |
| 14 | May 1, 2028 | 178.21 | 42.63 | 135.58 | 7171.75 |
| 15 | June 1, 2028 | 178.21 | 41.84 | 136.37 | 7035.38 |
| 16 | July 1, 2028 | 178.21 | 41.04 | 137.17 | 6898.21 |
| 17 | August 1, 2028 | 178.21 | 40.24 | 137.97 | 6760.24 |
| 18 | September 1, 2028 | 178.21 | 39.43 | 138.78 | 6621.46 |
| 19 | October 1, 2028 | 178.21 | 38.63 | 139.58 | 6481.88 |
| 20 | November 1, 2028 | 178.21 | 37.81 | 140.40 | 6341.48 |
| 21 | December 1, 2028 | 178.21 | 36.99 | 141.22 | 6200.26 |
| 22 | January 1, 2029 | 178.21 | 36.17 | 142.04 | 6058.22 |
| 23 | February 1, 2029 | 178.21 | 35.34 | 142.87 | 5915.35 |
| 24 | March 1, 2029 | 178.21 | 34.51 | 143.70 | 5771.65 |
| 25 | April 1, 2029 | 178.21 | 33.67 | 144.54 | 5627.11 |
| 26 | May 1, 2029 | 178.21 | 32.82 | 145.39 | 5481.72 |
| 27 | June 1, 2029 | 178.21 | 31.98 | 146.23 | 5335.49 |
| 28 | July 1, 2029 | 178.21 | 31.12 | 147.09 | 5188.40 |
| 29 | August 1, 2029 | 178.21 | 30.27 | 147.94 | 5040.46 |
| 30 | September 1, 2029 | 178.21 | 29.40 | 148.81 | 4891.65 |
| 31 | October 1, 2029 | 178.21 | 28.53 | 149.68 | 4741.97 |
| 32 | November 1, 2029 | 178.21 | 27.66 | 150.55 | 4591.42 |
| 33 | December 1, 2029 | 178.21 | 26.78 | 151.43 | 4439.99 |
| 34 | January 1, 2030 | 178.21 | 25.90 | 152.31 | 4287.68 |
| 35 | February 1, 2030 | 178.21 | 25.01 | 153.20 | 4134.48 |
| 36 | March 1, 2030 | 178.21 | 24.12 | 154.09 | 3980.39 |
| 37 | April 1, 2030 | 178.21 | 23.22 | 154.99 | 3825.40 |
| 38 | May 1, 2030 | 178.21 | 22.31 | 155.90 | 3669.50 |
| 39 | June 1, 2030 | 178.21 | 21.41 | 156.80 | 3512.70 |
| 40 | July 1, 2030 | 178.21 | 20.49 | 157.72 | 3354.98 |
| 41 | August 1, 2030 | 178.21 | 19.57 | 158.64 | 3196.34 |
| 42 | September 1, 2030 | 178.21 | 18.65 | 159.56 | 3036.78 |
| 43 | October 1, 2030 | 178.21 | 17.71 | 160.50 | 2876.28 |
| 44 | November 1, 2030 | 178.21 | 16.78 | 161.43 | 2714.85 |
| 45 | December 1, 2030 | 178.21 | 15.84 | 162.37 | 2552.48 |
| 46 | January 1, 2031 | 178.21 | 14.89 | 163.32 | 2389.16 |
| 47 | February 1, 2031 | 178.21 | 13.94 | 164.27 | 2224.89 |
| 48 | March 1, 2031 | 178.21 | 12.98 | 165.23 | 2059.66 |
| 49 | April 1, 2031 | 178.21 | 12.01 | 166.20 | 1893.46 |
| 50 | May 1, 2031 | 178.21 | 11.05 | 167.16 | 1726.30 |
| 51 | June 1, 2031 | 178.21 | 10.07 | 168.14 | 1558.16 |
| 52 | July 1, 2031 | 178.21 | 9.09 | 169.12 | 1389.04 |
| 53 | August 1, 2031 | 178.21 | 8.10 | 170.11 | 1218.93 |
| 54 | September 1, 2031 | 178.21 | 7.11 | 171.10 | 1047.83 |
| 55 | October 1, 2031 | 178.21 | 6.11 | 172.10 | 875.73 |
| 56 | November 1, 2031 | 178.21 | 5.11 | 173.10 | 702.63 |
| 57 | December 1, 2031 | 178.21 | 4.10 | 174.11 | 528.52 |
| 58 | January 1, 2032 | 178.21 | 3.08 | 175.13 | 353.39 |
| 59 | February 1, 2032 | 178.21 | 2.06 | 176.15 | 177.24 |
| 60 | March 1, 2032 | 178.27 | 1.03 | 177.24 | 0.00 |
| Total | | 10692.66 | 1692.66 | 9000.00 | |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Monthly payment | ±0.005 | Money is graded to the cent: 178.21, or the unrounded 178.2108 |
| Total interest, L0 and L1 | ±0.06 | No rounding rule is given, so 60 × 178.21 − 9000 = 1692.60, the unrounded 1692.65 and the schedule's 1692.66 all pass |
| Last payment, L2 | ±0.02 | Both interest conventions give 178.27; two cents allow a schedule that rounds in another order. The unadjusted 178.21 is 6 cents away |
| Total interest, L2 | ±0.02 | Both conventions give 1692.66; the unrounded 1692.65 passes; 1692.60 does not, because it ignores the last payment |
| Balances in the schedule | ±0.02 | The two interest conventions differ by at most 1.5 cents in any month's balance |

The two interest conventions, side by side:

| | Interest rounded each month (reference) | Exact interest, last payment rounded |
| --- | --- | --- |
| Balance after payment 24 | 5771.65 | 5771.64 |
| Balance after payment 59 | 177.24 | 177.23 |
| Last month's interest | 1.03 | 1.0339 |
| Last payment | 178.27 | 178.2663, so 178.27 |
| Total interest | 1692.66 | 1692.66 |

## Alternative accepted

- **Effective annual rate (L0 and L1 only).** If the response says it treats
  7% as an effective annual rate, the monthly rate is 1.07^(1/12) − 1 =
  0.56541%, the payment is 177.30 and the total interest is 1637.95. This is
  a real convention for some loans. It is not accepted at L2, where the brief
  says one twelfth of the annual rate.

## Not accepted

| Value | What went wrong |
| --- | --- |
| Payment 178.22 | Rounded up; 178.2108 rounds to 178.21 |
| Payment 177.18 | Payments taken at the start of each month |
| Payment 202.50 | Simple interest on the full amount for 5 years: (9000 + 3150) / 60 |
| Payment 150.00 | No interest |
| Total interest 3150.00 | Simple interest on the full amount |
| Last payment 178.21 (L2) | Not adjusted, so 0.06 is left owing |
| Last payment 177.92 (L2) | Each month's interest cut down to the cent, not rounded |
| Total interest 1692.60 (L2) | Sixty payments of 178.21 with no adjustment |

## Checks

- The schedule ends at exactly 0.00, and its principal column adds to
  9000.00.
- The interest column adds to 1692.66, and 59 × 178.21 + 178.27 − 9000 gives
  the same.
- With exact arithmetic, a payment of 178.21 leaves 0.0563 owing after 60
  payments and 178.22 overpays by 0.6596, which brackets the exact payment
  178.2108.
- The first row can be checked by hand: 9000 × 0.07 / 12 = 52.50 exactly.
- The last date: payment 1 is April 2027, so payment 60 is 59 months later,
  March 2032.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_loan_amortization`, `loan_schedule`), in decimal arithmetic.

## Note on the prompt

[prompts/math/README.md](../../../prompts/math/README.md) expects the two
interest conventions to differ by a few cents in the last payment and the
total. For this loan they do not: both give 178.27 and 1692.66. Balances in
the middle of the schedule differ by up to 1.5 cents.
