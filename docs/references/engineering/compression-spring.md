# Reference solution: compression spring design

**Study data, not a design.** These values exist to grade answers collected
for a study of model defaults. Do not build from them.

Task: [prompts/engineering/compression-spring.yaml](../../../prompts/engineering/compression-spring.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/engineering/compression-spring.yaml](../../../checker/references/engineering/compression-spring.yaml).

## What is checkable

- **L0 and L1: no checkable answer.** The prompt gives no force, size or
  unit, so every number is the model's choice, and those choices are what is
  measured. Record them. The rate formula can check a response's own numbers
  against each other; that is a consistency check, not a correctness grade.
- **L2: partly fixed, partly the model's choice.** The spring rate needed
  and the allowable stress follow from the brief. The wire diameter, coil
  diameter and number of coils are the model's choice: many springs meet the
  brief. The design has pass criteria, and the rate and stresses a response
  states are graded against its own dimensions.

## Givens (L2 only)

| Given | Value |
| --- | --- |
| Free length | 0.75 in |
| Working length and force | 0.55 in, at which it pushes back with 1.2 lbf |
| Space | A hole 0.30 in across; outside diameter at most 0.27 in |
| Wire | Type 302 stainless steel; shear modulus 10.0 million psi; tensile strength 280,000 psi |
| Stress limit | Shear stress at the working length below 45% of the tensile strength |
| Life | 100,000 presses |

## Assumptions

1. A round-wire helical spring of constant pitch and coil diameter, whose
   force grows in proportion to how far it is pressed in.
2. Spring rate: k = G d⁴ / (8 D³ Na), with d the wire diameter, D the mean
   coil diameter and Na the number of active coils.
3. Shear stress: τ = K × 8 F D / (π d³). The reference uses the Wahl factor,
   K = (4C − 1) / (4C − 4) + 0.615 / C with the spring index C = D / d, which
   allows for the curvature of the wire and the direct shear. Other factors
   are accepted when a response states them (see Alternatives).
4. End type sets the total coils and the solid length:

   | Ends | Total coils Nt | Solid length |
   | --- | --- | --- |
   | Squared and ground | Na + 2 | d × Nt |
   | Squared, not ground | Na + 2 | d × (Nt + 1) |
   | Plain, ground | Na + 1 | d × Nt |
   | Plain | Na | d × (Nt + 1) |

5. The outside diameter is D + d.
6. Each press takes the spring from its free length to 0.55 in and back, so
   the stress cycles between zero and the working stress, unless the
   response states a preload.

## Steps (L2)

1. Deflection at the working length: 0.75 − 0.55 = 0.20 in.
2. Spring rate needed: 1.2 lbf / 0.20 in = **6.0 lbf/in**.
3. Allowable shear stress at the working length: 0.45 × 280,000 =
   **126,000 psi**.
4. A design. Choose a wire and a coil diameter that fit the hole, then solve
   the rate formula for the number of coils. The reference design:

   | Design value | Reference design |
   | --- | --- |
   | Wire diameter d | 0.030 in |
   | Mean coil diameter D | 0.235 in |
   | Outside diameter D + d | 0.265 in (limit 0.27 in) |
   | Spring index C = D / d | 7.83 |
   | Active coils Na | 13 (the formula gives 13.003 for exactly 6.0 lbf/in) |
   | Ends | Squared and ground |
   | Total coils Nt | 15 |
   | Solid length d × Nt | 0.450 in (below the 0.55 in working length) |
   | Rate these give | 10.0 × 10^6 × 0.030⁴ / (8 × 0.235³ × 13) = 6.001 lbf/in |
   | Force at 0.55 in | 6.001 × 0.20 = 1.200 lbf |
   | Wahl factor | (31.33 − 1) / (31.33 − 4) + 0.615 / 7.833 = 1.188 |
   | Shear stress at 0.55 in | 1.188 × 8 × 1.200 × 0.235 / (π × 0.030³) = 31,600 psi |
   | Force at solid length | 6.001 × (0.75 − 0.450) = 1.800 lbf |
   | Shear stress at solid length | 47,400 psi |

   Both stresses are far below the allowable 126,000 psi (25% and 38% of
   it).
5. Life. Each press cycles the shear stress between 0 and 31,600 psi, which
   is 11% of the tensile strength. A common guideline for unpeened spring
   wire of this kind allows a largest stress of about 36% of the tensile
   strength, 100,800 psi, for 100,000 cycles. The reference design is at
   less than a third of that, so **it lasts**. A hundred thousand cycles is
   also a short life as springs go.

Other springs pass too. For example d = 0.026 in, D = 0.240 in with 7
active coils gives 5.90 lbf/in and 48,300 psi at 1.2 lbf. A thicker wire
does not always work: d = 0.032 in with D = 0.238 in needs 16 active coils,
and its 18 total coils are 0.576 in solid, so it cannot be pressed to
0.55 in.

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Spring rate needed | no checkable answer | 6.0 lbf/in |
| Allowable shear stress | | 126,000 psi |
| Wire, coil diameter, coils, solid length | | the model's choice, against the pass criteria |
| Rate the design gives | | G d⁴ / (8 D³ Na) from its own dimensions |
| Shear stress at 0.55 in and at solid length | | K × 8 F D / (π d³) from its own dimensions |
| Lasts 100,000 presses | | a verdict with a reason; yes for the reference design |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Spring rate needed, allowable stress | ±0.5% | Exact arithmetic on the givens |
| Rate from the response's own dimensions | ±2% of the formula's value | The rate goes as d⁴ / D³, so dimensions rounded to three decimals move it by a percent |
| Stress from the response's own dimensions | ±3% of the formula's value | The stress goes as D / d³ |
| Solid length | ±1% | Plain arithmetic |

## Pass criteria for the design (L2)

A design passes when:

1. the outside diameter, D + d, is at most 0.27 in;
2. the rate its dimensions give is within 10% of 6.0 lbf/in, so the force at
   0.55 in is from 1.08 to 1.32 lbf;
3. its solid length is less than 0.55 in;
4. its shear stress at 0.55 in is below 126,000 psi;
5. it gives the shear stress at solid length and compares it with the
   allowable. That stress may be over the allowable, which the brief applies
   at the working length; the response must then say so; and
6. its total coils and solid length agree with the end type it states.

The brief sets no tolerance on the force at 0.55 in. The 10% in point 2 is
this reference's judgment, taken from the usual commercial tolerance on a
spring's load at a length; the checker should record how far a design is
from 6.0 lbf/in as well as the pass.

**Life.** There is no single right criterion. It passes when the response
gives a verdict, gives a reason that compares its own stress with a stated
fatigue limit or guideline for spring wire, and the verdict follows from
that comparison. As a yardstick, a design whose stress at 0.55 in is at or
under 100,800 psi (36% of the tensile strength) should be said to last.

## Alternatives accepted (L2)

For the shear stress, when the response states the factor it uses:

| Factor | Formula | Reference design at 0.55 in |
| --- | --- | --- |
| Wahl (reference) | (4C − 1)/(4C − 4) + 0.615/C | 31,610 psi |
| Bergsträsser | (4C + 2)/(4C − 3) | 31,300 psi |
| Direct shear only | 1 + 0.5/C | 28,300 psi |
| None | 1 | 26,600 psi |

For the solid length, ends that are not ground: d × (Nt + 1), which is
0.480 in for the reference wire and 15 total coils.

A response that states no factor is graded against the Wahl value; the 3%
tolerance also accepts Bergsträsser.

## Not accepted (L2)

| Value | What went wrong |
| --- | --- |
| Rate 2.18 lbf/in | Force divided by the working length, 1.2 / 0.55 |
| Rate 1.6 lbf/in | Force divided by the free length |
| A design with D + d over 0.27 in | Does not fit the hole |
| A design solid at 0.55 in or more | Cannot reach the working length |

## Checks

- Units: psi × in⁴ / in³ = lbf/in; lbf × in / in³ = psi.
- The reference design was put back through its own pass criteria: outside
  diameter 0.265 in, rate 6.001 lbf/in, solid length 0.450 in, stress
  31,600 psi.
- The Wahl and Bergsträsser factors agree to 1% at this index (1.188 and
  1.176), as they should.
- Length over mean diameter is 0.75 / 0.235 = 3.2, short enough that the
  spring will not buckle in its hole.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_compression_spring`, `spring_rate`, `spring_stress`).

## Notes on the prompt

- The L2 brief compares the stress at solid length "against the allowable"
  as well, but states the 45% limit for the working length only. A design
  can therefore be over 126,000 psi when fully compressed and still meet the
  brief; the criteria ask only that the response makes the comparison.
- Two figures above are not in the brief and come from general spring
  practice: the 36% guideline for 100,000 cycles and the 10% tolerance on
  load. They are yardsticks for a reader, and no pass depends on a response
  quoting them.
