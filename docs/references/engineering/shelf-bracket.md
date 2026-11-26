# Reference solution: shelf bracket with a CAD file

**Study data, not a design.** These values exist to grade answers collected
for a study of model defaults. Do not build from them.

Task: [prompts/engineering/shelf-bracket.yaml](../../../prompts/engineering/shelf-bracket.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/engineering/shelf-bracket.yaml](../../../checker/references/engineering/shelf-bracket.yaml).

## What is checkable

- **L0 and L1: no checkable answer.** The prompt gives no dimension, load or
  unit, so every number is the model's choice, and those choices are what is
  measured. Record them. If a response states a load and its distance from
  the wall, the moment it reports can be checked against its own numbers
  (load × distance); that is a consistency check, not a correctness grade.
- **L2: partly fixed, partly the model's choice.** The moment where the
  bracket meets the wall follows from the brief. The force on each screw and
  the stress in the plywood depend on the outline and the screw positions the
  model chooses, so they are graded against those. The outline and the CAD
  file have pass criteria.

## Givens (L2 only)

| Given | Value |
| --- | --- |
| Shelf | 10 in deep, 3/4 in thick |
| Load | Two brackets; each carries 40 lb spread evenly over the shelf's depth |
| Wall strip | Vertical wood strip, 1 1/2 in square, fixed to the wall stud, running down from the underside of the shelf |
| Fixing | The bracket lies flat against the side of the strip, held by two screws through the plywood, one above the other |
| Material | 1/4 in birch plywood, laser cut, one flat piece |
| Profile | Solid quarter circle: one straight edge against the wall, one under the shelf, a curved edge between |
| Dimensions | Inches, to the nearest 1/16 in |
| Working stress | 1000 psi in bending |

## Assumptions

1. The 40 lb is spread evenly over the 10 in depth of the shelf: 4 lb per
   inch. It acts as one force of 40 lb, 5 in from the wall.
2. The shelf rests on the bracket alone; the wall carries none of the
   shelf's weight directly. The whole 40 lb then reaches the bracket, 5 in
   from the wall, whatever the bracket's size.
3. The bracket is a quarter disc of radius R, with its corner where the wall
   meets the underside of the shelf. At a distance x from the wall its depth
   is sqrt(R² − x²). R is the model's choice, up to the 10 in depth of the
   shelf.
4. The two screws go through the face of the plywood into the side of the
   strip, so they are loaded across their length (in shear), not pulled
   along it. They sit one above the other, a distance e from the bracket's
   wall edge and s apart. Both are the model's choice; the strip is 1 1/2 in
   deep, so e is between 0 and 1 1/2 in, and 3/4 in puts the screws on the
   strip's centerline.
5. The plywood is treated as a plain beam of rectangular section, 1/4 in wide
   and as deep as the bracket at that section: stress = 6 M / (t h²). Screw
   holes, the direction of the plies and the bracket's taper are left out.

## How two screws share the load: two readings

The brief asks for "the force on each screw" and does not say whether the
bracket's wall edge presses on the wall. Two readings are legitimate. Grade
a response against the one it states; the screw-group reading is the
reference and applies when it states none.

**Screw-group reading (reference).** The two screws alone hold the bracket.
Each carries half the load downward. The load also turns the bracket about
the pair of screws with a moment of 40 × (5 − e) lb·in, and the screws
resist it with equal and opposite sideways forces:

    downward on each screw     40 / 2 = 20 lb
    sideways on each screw     40 (5 − e) / s
    total on each screw        sqrt(20² + (40 (5 − e) / s)²)

The upper screw is pulled away from the wall and the lower one is pushed
toward it.

**Bearing reading.** The bottom of the bracket's wall edge presses against
the wall at a depth p below the shelf (p = R if it bears at its tip), and
the screws hold the top in. Taking moments about the bearing point, the load
gives 40 × 5 lb·in and the screws' upward 40 lb, acting e from the wall,
gives 40 × e back, so the sideways forces must supply 40 (5 − e). With the
upper screw a depth a below the shelf:

    upper screw alone holds the top in       40 (5 − e) / (p − a)
    both screws, in proportion to height     upper: 40 (5 − e) (p − a) / ((p − a)² + (p − a − s)²)
                                             lower: 40 (5 − e) (p − a − s) / ((p − a)² + (p − a − s)²)

A response may also work from the moment at the wall, 200 lb·in, in place of
40 (5 − e): 200 / (p − a) for the upper screw alone, or 200 shared between
the two screws in proportion to height. That leaves out the 40 × e term and
is accepted when the response states it. In every bearing reading each screw
still carries 20 lb downward.

**One total or two parts.** The request is met by the two parts on each
screw (sideways and downward) or by one total force on each,
sqrt(sideways² + 20²). In the screw-group reading both screws carry the
same total. In a bearing reading they differ, and where the upper screw
alone holds the top in, the lower screw carries only its 20 lb.

## Steps (L2)

1. Load per inch: 40 / 10 = 4 lb/in. Its resultant acts 5 in from the wall.
2. Moment where the bracket meets the wall: 40 lb × 5 in = **200 lb·in**.
   (By integration: 4 × 10² / 2 = 200.)
3. Reference layout, for the worked numbers: R = 10 in; screw holes 3/4 in
   from the wall edge, 2 in and 8 in below the top edge (e = 3/4 in,
   s = 6 in).
4. Screw forces, screw-group reading: downward **20 lb** each; sideways
   40 × (5 − 0.75) / 6 = 170 / 6 = **28.3 lb** each; total
   sqrt(20² + 28.3²) = **34.7 lb** each.
5. Plywood stress. At a distance x from the wall the moment is
   4 (10 − x)² / 2 and the depth is sqrt(R² − x²). For R = 10 in the stress
   is 6 M / (t h²) = 48 (10 − x) / (10 + x) psi, largest at the wall. So the
   weakest section is at the wall: M = 200 lb·in, h = 10 in,
   section modulus 0.25 × 10² / 6 = 4.167 in³, stress 200 / 4.167 =
   **48 psi**, against the working stress of 1000 psi: about a twentieth of
   it.

For other choices:

| Screw positions | Sideways on each | Total on each |
| --- | --- | --- |
| e = 3/4 in, s = 6 in | 28.3 lb | 34.7 lb |
| e = 3/4 in, s = 5 in | 34.0 lb | 39.4 lb |
| e = 3/4 in, s = 4 in | 42.5 lb | 47.0 lb |
| e = 1 in, s = 6 in | 26.7 lb | 33.3 lb |

| Wall edge R | Section modulus at the wall | Stress at the wall |
| --- | --- | --- |
| 10 in | 4.167 in³ | 48 psi |
| 9 in | 3.375 in³ | 59 psi |
| 8 in | 2.667 in³ | 75 psi |

Bearing readings, for the reference layout (p = 10 in, a = 2 in, s = 6 in):

| Reading | Sideways, upper | Sideways, lower | Total, upper | Total, lower |
| --- | --- | --- | --- | --- |
| Upper screw alone, 40 (5 − e) | 21.3 lb | 0 | 29.2 lb | 20.0 lb |
| Upper screw alone, 200 lb·in | 25.0 lb | 0 | 32.0 lb | 20.0 lb |
| Both share, 40 (5 − e) | 20.0 lb | 5.0 lb | 28.3 lb | 20.6 lb |
| Both share, 200 lb·in | 23.5 lb | 5.9 lb | 30.9 lb | 20.8 lb |

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Moment where the bracket meets the wall | no checkable answer | 200 lb·in |
| Downward force on each screw | | 20 lb |
| Sideways force on each screw | | 40 (5 − e) / s; 28.3 lb for the reference layout |
| Or the total force on each screw | | sqrt(20² + sideways²); 34.7 lb for the reference layout |
| Plywood bending stress at the weakest section | | at the wall, 6 × 200 / (0.25 R²) for the radius stated; 48 psi for R = 10 in |
| Against the working stress | | far below 1000 psi |
| Outline, CAD file | | pass criteria |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Moment at the wall, downward force | ±0.5% | Statics; exact |
| Sideways and total screw force | ±2% of the formula's value | Rounding, and positions given to the nearest 1/16 in |
| Plywood stress | ±2% of the formula's value | The same |

The stress is graded at the wall section, for the radius the response
states, because the brief asks for the weakest section and that is where the
moment is the full 200 lb·in. A response cannot pass by naming a lightly
loaded section: midway along the reference bracket the same formula gives
16 psi, a third of the wall value. A stress the response works at any other
section is still checked against its own moment and depth
(`plywood_bending_stress` in the YAML file), as a check of its arithmetic.

One alternative is accepted when the response states it: the section through
the screw holes, with the holes taken off the depth. It is graded from the
moment and the net depth the response states. For the reference bracket with
3/16 in holes that is 171.1 lb·in on a net depth of 9.60 in, 44.6 psi. Where
the bracket is narrower than the shelf is deep, the simple beam picture
breaks down near the bracket's tip, since the shelf must carry its own
overhang; the wall section is still the one graded.

## Pass criteria (L2)

**Outline.** The radius and hole positions are the model's choice. It passes
when:

1. it is a solid quarter circle: two straight edges of equal length R at a
   right angle, and one arc of radius R centered on that corner (arc length
   π R / 2; for R = 10 in, 15.71 in, and an area of 78.5 in²);
2. R is more than 5 in and at most 10 in, so the bracket reaches past the
   middle of the shelf and not past its front;
3. it has two screw holes, one above the other, over the strip (0 < e <
   1.5 in);
4. every dimension is in inches and a whole number of sixteenths; and
5. it is one flat piece, 1/4 in thick.

**CAD file.** The format is the model's choice; record it. It passes when it
is a flat, two-dimensional outline a laser cutter can take (such as DXF or
SVG), holds one closed outline (two lines and an arc) and two circles for
the holes, and agrees with the dimensioned description.

**Stress.** The response finds a stress at or under 1000 psi and says so.

## Not accepted (L2)

| Value | What went wrong |
| --- | --- |
| Moment 400 lb·in | The load taken at the front edge of the shelf |
| Moment 170 lb·in reported as the moment at the wall | That is the moment about the screws (e = 3/4 in) |
| Moment 2000 lb·in | w L² / 2 with w taken as 40 lb per inch |
| A pull-out force given as the force on each screw | The screws run across the plywood into the side of the strip, so the shelf load bears on them across their length. A response that works the shear forces and adds a remark on a small pull-out effect is not marked down for it |
| 16 psi "at the weakest section" (R = 10 in) | The stress midway along the bracket; the weakest section is at the wall |

## Checks

- The moment at the wall by two routes, a single force (40 × 5) and the
  spread load (4 × 10² / 2), is 200 lb·in both ways.
- Screw-group forces balance the bracket: the two downward forces add to
  40 lb, the sideways forces cancel, and their couple, 28.33 × 6 = 170 lb·in,
  equals the load's moment about the screws, 40 × 4.25.
- Bearing reading with both screws: 20.0 × 8 + 5.0 × 2 = 170 lb·in, the same
  moment; with the 200 lb·in shortcut, 23.53 × 8 + 5.88 × 2 = 200 lb·in.
- The stress formula at the wall, 6 × 200 / (0.25 × R²), was compared with
  the general section formula over the whole bracket; for R = 10 in no
  section is more highly stressed than the wall section.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_shelf_bracket`, `bracket_screw_group`, `bracket_bearing`).

## Notes on the prompt

- "The force on each screw" has more than one defensible answer, as set out
  above. The brief is still well posed for grading, because each reading is
  a formula in the positions the response states.
- The shelf thickness, 3/4 in, does not enter any answer.
- 1/4 in plywood is stressed to about 5% of the working stress, so the
  stress check never decides the size. A bracket this thin is more likely
  to be limited by buckling sideways and by the screws' hold in the plywood,
  which the brief does not ask about.
