# Reference solution: titration pH curve

Task: [prompts/math/titration-curve.yaml](../../../prompts/math/titration-curve.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/math/titration-curve.yaml](../../../checker/references/math/titration-curve.yaml).

The question at every level: what is the pH curve for titrating 25.0 mL of
0.100 M acetic acid with 0.100 M sodium hydroxide?

## Givens

| Given | Value |
| --- | --- |
| Acid | 25.0 mL of 0.100 M acetic acid |
| Base | 0.100 M sodium hydroxide |
| L2 only: constants | 25 °C; Ka = 1.8 × 10^-5; Kw = 1.0 × 10^-14 |
| L2 only: simplifications | Activities equal concentrations; volumes add |
| L2 only: points | 0, 5.0, 10.0, 12.5, 20.0, 24.0, 25.0, 26.0, 30.0, 40.0 and 50.0 mL; pH to 2 decimals |
| L2 only: method | One exact charge-balance equation, solved numerically, for every point |

## Assumptions

1. 25 °C, Ka = 1.8 × 10^-5 (pKa = 4.745) and Kw = 1.0 × 10^-14. The L2 brief
   gives them. At L0 and L1 they are the textbook values; some books use
   Ka = 1.75 × 10^-5 or 1.76 × 10^-5 (pKa 4.76 or 4.75), and the L0 and L1
   tolerance accepts those.
2. Activities equal concentrations, and volumes add.
3. Sodium hydroxide is fully dissociated. Acetic acid gives up one proton.
4. Dissolved carbon dioxide and the like are left out.

## Method

After V mL of base the total volume is 25.0 + V mL, so

    C  = 0.100 × 25.0 / (25.0 + V)      total acetic acid plus acetate
    Na = 0.100 × V / (25.0 + V)         sodium ion

The solution has no net charge:

    [H+] + [Na+] = [OH−] + [A−]

With [OH−] = Kw / [H+] and, from the acid equilibrium, [A−] = C Ka / (Ka + [H+]),
writing h for [H+]:

    h + Na − Kw / h − C Ka / (Ka + h) = 0

The left side rises steadily with h, so the equation has one positive root.
It is found by bisection between 10^-15 and 1 mol/L, and pH = −log10(h). The
same equation serves every point: before, at and after the equivalence
point.

## Steps

1. Equivalence: the acid holds 25.0 mL × 0.100 M = 2.50 mmol, which needs
   2.50 mmol of base, that is **25.0 mL**. Half-equivalence is at 12.5 mL.
2. Solve the charge balance at each listed volume:

   | V (mL) | C (M) | Na (M) | h (M) | pH | pH to 2 decimals |
   | --- | --- | --- | --- | --- | --- |
   | 0 | 0.10000 | 0 | 1.333 × 10^-3 | 2.8753 | 2.88 |
   | 5.0 | 0.08333 | 0.01667 | 7.161 × 10^-5 | 4.1450 | 4.14 |
   | 10.0 | 0.07143 | 0.02857 | 2.696 × 10^-5 | 4.5693 | 4.57 |
   | 12.5 | 0.06667 | 0.03333 | 1.798 × 10^-5 | 4.7452 | 4.75 |
   | 20.0 | 0.05556 | 0.04444 | 4.498 × 10^-6 | 5.3470 | 5.35 |
   | 24.0 | 0.05102 | 0.04898 | 7.497 × 10^-7 | 6.1251 | 6.13 |
   | 25.0 | 0.05000 | 0.05000 | 1.897 × 10^-9 | 8.7219 | 8.72 |
   | 26.0 | 0.04902 | 0.05098 | 5.100 × 10^-12 | 11.2924 | 11.29 |
   | 30.0 | 0.04545 | 0.05455 | 1.100 × 10^-12 | 11.9586 | 11.96 |
   | 40.0 | 0.03846 | 0.06154 | 4.333 × 10^-13 | 12.3632 | 12.36 |
   | 50.0 | 0.03333 | 0.06667 | 3.000 × 10^-13 | 12.5229 | 12.52 |

3. The pH at the equivalence point is the 25.0 mL row, **8.72**. The pH at
   half-equivalence is the 12.5 mL row, **4.75**.

The curve starts at 2.88, rises quickly over the first milliliter or two,
then is nearly flat through the buffer region around pH 4.75, where the
solution holds both the acid and its salt and resists change. Near 25 mL the
buffer is used up and the pH jumps from about 6 to about 11 within 2 mL,
through 8.72 at the equivalence point, which lies above 7 because acetate is
a weak base. Past the equivalence point the curve flattens again, set by the
excess hydroxide, and creeps toward the pH of the base itself.

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Equivalence volume | 25.0 mL | 25.0 mL |
| Initial pH (0 mL) | 2.88 | 2.88 |
| pH at half-equivalence (12.5 mL) | 4.75 | 4.75 |
| pH at equivalence (25.0 mL) | 8.72 | 8.72 |
| Other listed volumes | graded if given | the table above |

## Tolerances and why

The shortcut formulas for each region, with the same constants, agree with
the charge balance to 0.003 at the listed volumes:

| Point | Charge balance | Shortcut | Shortcut value |
| --- | --- | --- | --- |
| 0 mL | 2.8753 | sqrt(Ka C) | 2.8724 |
| 5.0 mL | 4.1450 | pKa + log(V / (25 − V)) | 4.1427 |
| 12.5 mL | 4.7452 | pH = pKa | 4.7447 |
| 24.0 mL | 6.1251 | pKa + log(V / (25 − V)) | 6.1249 |
| 25.0 mL | 8.7219 | weak base, sqrt(Kb C) | 8.7218 |
| 26.0 mL and beyond | 11.2924 | excess hydroxide | 11.2924 |

Rounded to 2 decimals the two routes can differ by one unit in the last place
(2.88 against 2.87 at the start, 4.75 against 4.74 at half-equivalence, 6.13
against 6.12 at 24 mL), so the tolerance has to span that.

- **L2: ±0.015 on every pH.** Half a unit in the second decimal for the
  rounding asked, plus 0.01 for the shortcut routes and for pKa rounded to
  4.74 or 4.75.
- **L0 and L1: ±0.03 on every pH.** No constants are given. Ka = 1.74 × 10^-5
  moves the buffer-region points up by 0.015 and the equivalence point by
  0.007; the tolerance accepts Ka from 1.74 × 10^-5 to 1.8 × 10^-5 with either
  route. Points past the equivalence do not depend on Ka.
- **Equivalence volume ±0.05 mL.** The givens have three significant figures.

A point within about 0.2 mL of the equivalence point is not a fair check: the
pH there moves by more than 0.01 for each 0.001 mL (7.14 at 24.9 mL, 10.30 at
25.1 mL).

## Alternative accepted

- **Other constants.** A response that states its own Ka and Kw is graded by
  the same charge balance with those constants (`ph_at_volume` in the YAML
  file), with the L2 tolerance.

## Not accepted

| Value | What went wrong |
| --- | --- |
| Initial pH 1.00 | Acetic acid treated as a strong acid |
| Initial pH 2.37 | pKa / 2, with the concentration left out |
| Equivalence pH 7.00 | Treated as a strong acid with a strong base |
| Equivalence pH 8.87 | Dilution left out: acetate taken as 0.100 M, not 0.0500 M |
| Equivalence pH 5.28 | pOH reported as pH |
| pH at 26.0 mL 11.59 | Dilution left out: the excess base divided by 26 mL, not 51 mL |

## Checks

- The pH rises at every step of the table, and jumps by more than 5 between
  24.0 and 26.0 mL.
- At 12.5 mL the charge balance gives 4.7452, within 0.0005 of pKa = 4.7447,
  as the buffer equation predicts.
- Putting each root back into the charge balance leaves no residual: for
  example at 25.0 mL, h = 1.897 × 10^-9 gives [OH−] = 5.271 × 10^-6 and
  [A−] = 0.05 × Ka / (Ka + h) = 0.0499947, and
  h + 0.05 = 5.271 × 10^-6 + 0.0499947 to seven figures.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_titration_curve`, `titration_ph`).

## Note on the prompt

At 5.0 mL the exact pH is 4.14500 to five decimals (4.1449964), so "4.14" and
"4.15" are both reasonable roundings. The tolerance accepts both.
