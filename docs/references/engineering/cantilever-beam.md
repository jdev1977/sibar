# Reference solution: size a cantilever beam

**Study data, not a design.** These values exist to grade answers collected
for a study of model defaults. Do not build from them.

Task: [prompts/engineering/cantilever-beam.yaml](../../../prompts/engineering/cantilever-beam.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/engineering/cantilever-beam.yaml](../../../checker/references/engineering/cantilever-beam.yaml).

The question at every level: size a cantilever beam 1.5 m long that carries
4 kN at its free end.

## What is checkable

- **L0 and L1:** the reaction and the largest bending moment follow from
  statics alone. The section itself has no single answer: it depends on the
  material, the shape, the safety factor and the limits the model chooses.
  Those choices are what is measured; record them. The section is checked
  against the response's own numbers, with the formulas below.
- **L2:** material, shape, safety factor and deflection limit are dictated,
  so the section and its stress and deflection are fixed.

## Givens

| Given | Value |
| --- | --- |
| Length | 1.5 m, fixed at one end |
| Load | 4 kN at the free end |
| L2 only: material | 6061-T6 aluminum; Young's modulus 68.9 GPa; yield strength 276 MPa |
| L2 only: section | Solid rectangle, depth twice the width, load along the depth |
| L2 only: limits | Safety factor of 3 on yield for bending stress; tip deflection at most 15 mm |
| L2 only: loads | The tip load is the only load |
| L2 only: sizes | Smallest width and depth in whole millimeters |

## Assumptions

1. The beam is straight, of constant section, fully fixed at one end and
   free at the other.
2. The 4 kN acts at the free end, across the beam. It is a static working
   load; no load factor is applied.
3. The beam's own weight is left out. At L2 the brief says the tip load is
   the only load. At L0 and L1 a response that adds its own weight is graded
   by the alternative below.
4. Small deflections of a slender elastic beam (Euler-Bernoulli theory).
   Shear deflection is left out; for the L2 bar it would add 0.05 mm.
5. L2: with width b and depth 2b, bending about the axis that uses the
   depth, the section modulus is S = b (2b)² / 6 = 2b³/3 and the second
   moment of area is I = b (2b)³ / 12 = 2b⁴/3. The depth is exactly twice
   the width, and both are whole millimeters.

## Method

Statics of a cantilever with a load P at the tip, length L:

    reaction R = P            largest shear V = P (constant along the beam)
    largest moment M = P L    at the fixed end

Elementary beam formulas, found in any mechanics of materials textbook:

    bending stress   σ = M / S
    tip deflection   δ = P L³ / (3 E I)

## Steps, L0 and L1

1. Reaction at the fixed end: R = **4 kN**. Shear: 4 kN along the whole beam.
2. Largest bending moment: M = 4 kN × 1.5 m = **6 kN·m**, at the fixed end.
   The fixed end also supplies a moment reaction of 6 kN·m.
3. For the section a response chooses, with section modulus S, second moment
   of area I and modulus E:

       σ = 6 × 10^6 N·mm / S        (S in mm³ gives MPa)
       δ = 4000 × 1500³ / (3 E I)   (E in MPa, I in mm⁴ gives mm)

   and the section modulus it needs for its own allowable stress is
   6 × 10^6 / allowable.

## Steps, L2

1. Allowable bending stress: 276 / 3 = **92 MPa**.
2. Required section modulus: S = M / σ = 6 × 10^6 N·mm / 92 MPa =
   **65 217 mm³** (65.2 × 10³ mm³).
3. Required second moment of area: I = P L³ / (3 E δ) =
   4000 × 1500³ / (3 × 68 900 × 15) = 1.35 × 10^13 / 3.1005 × 10^6 =
   **4.354 × 10^6 mm⁴**.
4. Width for stress: 2b³/3 ≥ 65 217, so b ≥ (97 826)^(1/3) = 46.08 mm.
5. Width for deflection: 2b⁴/3 ≥ 4.354 × 10^6, so
   b ≥ (6.531 × 10^6)^(1/4) = 50.55 mm.
6. Deflection needs the larger width, so **deflection governs**. The
   smallest whole millimeter that meets both is b = **51 mm**, with depth
   **102 mm**.
7. For 51 mm by 102 mm: S = 51 × 102² / 6 = 88 434 mm³ and
   I = 51 × 102³ / 12 = 4 510 134 mm⁴.
8. Bending stress: 6 × 10^6 / 88 434 = **67.85 MPa** (limit 92 MPa; 26%
   below it).
9. Tip deflection: 1.35 × 10^13 / (3 × 68 900 × 4 510 134) = **14.48 mm**
   (limit 15 mm; 3.5% below it).

The size below fails: 50 mm by 100 mm gives 72.0 MPa, which passes, but
15.67 mm, which does not.

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Reaction at the fixed end | 4 kN | 4 kN |
| Largest bending moment | 6 kN·m | 6 kN·m |
| Allowable stress | the model's choice | 92 MPa |
| Required section modulus | from the model's allowable | 65.2 × 10³ mm³ |
| Required second moment of area | from the model's limit | 4.35 × 10^6 mm⁴ |
| Section | the model's choice | 51 mm wide, 102 mm deep |
| Governing limit | the model's choice | deflection |
| Bending stress | from the model's section | 67.8 MPa |
| Tip deflection | from the model's section | 14.5 mm |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Reaction, moment | ±0.5% | Statics; exact |
| Required S and I | ±1% | Accepts three significant figures |
| Width, depth | exact | Whole millimeters; 50 fails the deflection limit and 52 is not the smallest |
| Stress, deflection at L2 | ±1% | Accepts 67.8 and 14.5 |
| Stress and deflection of a model's own section (L0, L1) | ±2% | Section tables round their properties |

## Alternatives accepted (L0 and L1)

- **Self-weight.** If the response adds the beam's own weight w (kN/m), the
  reaction is 4 + 1.5 w and the largest moment is 6 + w × 1.5² / 2. For
  scale: the L2 bar weighs 0.138 kN/m, which adds 0.155 kN·m (2.6%).
- **Load factor.** If the response applies a stated factor γ to the load
  before sizing, the design reaction is 4 γ and the design moment 6 γ
  (9 kN·m for 1.5).

Neither is accepted at L2, where the brief gives the load and the safety
factor.

## Pass criteria for the section (L0 and L1)

The choice of material, shape and safety factor is not graded. The section
passes when:

1. the bending stress it gives, M / S, is at or under the allowable stress
   the response states; and
2. if the response states a deflection limit, P L³ / (3 E I) is at or under
   it.

## Not accepted

| Value | What went wrong |
| --- | --- |
| Moment 3 kN·m | The load taken at mid-length, or spread along the beam |
| Required S 21 739 mm³ (L2) | Yield strength used with no safety factor |
| Required I 1.633 × 10^6 mm⁴ (L2) | The formula for an evenly spread load, w L⁴ / (8 E I) |
| Width 47 mm (L2) | Sized for stress alone |
| Width 50 mm (L2) | Deflects 15.67 mm |
| Stress 135.7 MPa (L2) | Bent the weak way: S taken as 102 × 51² / 6 |

## Checks

- Units: N·mm / mm³ = N/mm² = MPa; N × mm³ / (N/mm² × mm⁴) = mm.
- The chosen width is the first whole number above 50.55, and a search over
  whole widths confirms that 51 passes both limits and 50 does not.
- Stress scales as 1/b³ and deflection as 1/b⁴: (46.08 / 51)³ × 92 = 67.85 MPa
  and (50.55 / 51)⁴ × 15 = 14.48 mm, the same values.
- Largest shear stress in the bar is 1.5 × 4000 / (51 × 102) = 1.15 MPa,
  negligible beside the bending stress, so bending alone sizes the section.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_cantilever_beam`).
