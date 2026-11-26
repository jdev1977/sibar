# Reference solution: pipe pressure drop and pump choice

**Study data, not a design.** These values exist to grade answers collected
for a study of model defaults. Do not build from them.

Task: [prompts/engineering/pipe-and-pump.yaml](../../../prompts/engineering/pipe-and-pump.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/engineering/pipe-and-pump.yaml](../../../checker/references/engineering/pipe-and-pump.yaml).

The question at every level: what is the pressure drop in a pipe that carries
1.5 L/s of water up 6 m over a length of 35 m, with an inside diameter of
40 mm, and what pump suits it?

## What is checkable

- **L0 and L1:** the velocity and the static head follow from the givens,
  and the Reynolds number from the givens and a water temperature. The
  friction loss also depends on the pipe's roughness, the temperature and
  any fittings, which the prompt leaves to the model. Record them, and grade
  the friction against them. The pump is a choice with pass criteria.
- **L2:** the friction method, its coefficient, the fittings, the supply and
  the efficiency are dictated, so six numbers are fixed. The kind of pump is
  a choice with pass criteria.

"Pressure drop" is read by some as the friction loss alone and by others as
friction plus the lift. Both are graded, whichever the response gives.

## Givens

| Given | Value |
| --- | --- |
| Flow | 1.5 L/s of water |
| Lift | 6 m |
| Pipe length | 35 m |
| Inside diameter | 40 mm |
| L2 only: pipe | Black polyethylene; Hazen-Williams equation with C = 140 |
| L2 only: fittings | A strainer, 4 elbows and a check valve: 8 m of extra pipe |
| L2 only: water | 15 °C; pond and tank both open to the air |
| L2 only: supply | 12 V battery; wire-to-water efficiency 40% |

## Assumptions

1. Steady flow of fresh water in a full, round pipe of constant bore.
   g = 9.81 m/s².
2. The 6 m is the difference in water level between the source and the
   outlet, both open to the air. The static head is then 6 m whatever route
   the pipe takes.
3. Water properties, from standard tables:

   | Temperature (°C) | Kinematic viscosity (mm²/s) | Density (kg/m³) |
   | --- | --- | --- |
   | 5 | 1.519 | 1000.0 |
   | 10 | 1.307 | 999.7 |
   | 15 | 1.139 | 999.1 |
   | 20 | 1.004 | 998.2 |
   | 25 | 0.893 | 997.0 |
   | 30 | 0.801 | 995.7 |

4. L0 and L1: the reference friction figures are for the 35 m of straight
   pipe alone, by the Darcy-Weisbach equation with the Colebrook friction
   factor. Fittings, if a response counts them, are graded from its own loss
   coefficients or equivalent length.
5. L2: the Hazen-Williams equation in its SI form,
   h = 10.67 L Q^1.852 / (C^1.852 d^4.8704), with h and L in meters, Q in
   m³/s and d in meters, and L = 35 + 8 = 43 m.
6. L2: the velocity head at the pipe outlet (0.07 m) is not added to the
   pump head. A response that adds it is graded by the alternative.
7. L2: the wire-to-water efficiency is hydraulic power over electrical
   power. The current is electrical power over 12 V; the battery voltage is
   taken as constant.

## Steps, L0 and L1

1. Flow: Q = 1.5 L/s = 0.0015 m³/s. Pipe area: π × 0.040² / 4 =
   1.2566 × 10^-3 m².
2. Velocity: v = 0.0015 / 1.2566 × 10^-3 = **1.194 m/s**. Velocity head:
   v² / (2 g) = 0.0726 m.
3. Static head: **6 m**, which is 58.8 kPa.
4. Reynolds number: Re = v d / ν = 1.194 × 0.040 / ν. At 20 °C that is
   **47 560**; at 10, 15 and 25 °C it is 36 530, 41 920 and 53 470. The flow
   is turbulent at any water temperature.
5. Friction in 35 m of straight pipe: h = f (L / d) v² / (2 g) =
   f × 875 × 0.0726 = 63.54 f, with f from the Colebrook equation
   1/sqrt(f) = −2 log10((ε / d) / 3.7 + 2.51 / (Re sqrt(f))):

   | Roughness ε (mm) | Typical of | 10 °C | 15 °C | 20 °C | 25 °C |
   | --- | --- | --- | --- | --- | --- |
   | 0 | a smooth pipe | 1.425 m | 1.381 m | 1.342 m | 1.308 m |
   | 0.0015 | plastic, drawn tubing | 1.433 m | 1.389 m | 1.351 m | 1.317 m |
   | 0.007 | plastic (a figure often quoted) | 1.459 m | 1.417 m | 1.381 m | 1.348 m |
   | 0.045 | commercial steel | 1.618 m | 1.585 m | 1.558 m | 1.535 m |
   | 0.15 | galvanized steel | 1.953 m | 1.932 m | 1.915 m | 1.901 m |

   At 20 °C the friction factor is 0.0211 for a smooth pipe and 0.0245 for
   commercial steel. One meter of water is 9.79 kPa, so the friction
   pressure drop is about 13 to 16 kPa for smooth pipe to steel.
6. For a response's own numbers: the total head is 6 m plus its losses; the
   hydraulic power is ρ g Q H = 998.2 × 9.81 × 0.0015 × H = 14.69 H watts
   (about 108 W at 7.34 m); the input power is that over its efficiency.

## Steps, L2

1. Velocity: **1.194 m/s**, as above.
2. Friction length: 35 + 8 = 43 m.
3. Friction loss, Hazen-Williams:
   Q^1.852 = 0.0015^1.852 = 5.888 × 10^-6;
   C^1.852 = 140^1.852 = 9432;
   d^4.8704 = 0.040^4.8704 = 1.5545 × 10^-7;
   h = 10.67 × 43 × 5.888 × 10^-6 / (9432 × 1.5545 × 10^-7) = **1.844 m**.
4. Total head: 6 + 1.844 = **7.844 m**.
5. In pressure, with water at 15 °C (999.1 kg/m³, so 9.801 kPa per meter):
   friction 18.07 kPa, static 58.81 kPa, total **76.88 kPa**.
6. Hydraulic power: ρ g Q H = 999.1 × 9.81 × 0.0015 × 7.844 = **115.3 W**.
7. Electrical power: 115.3 / 0.40 = **288.3 W**.
8. Current: 288.3 / 12 = **24.0 A**.
9. Kind of pump: the duty is a moderate flow (1.5 L/s, which is 90 L/min or
   5.4 m³/h) at a low head (7.8 m). That is the home ground of a
   **centrifugal pump**. The reference's choice is a 12 V DC centrifugal
   pump, either a surface pump set at or below pond level so that it stays
   primed, or a submersible one in the pond. A positive-displacement pump
   (diaphragm, piston, helical rotor) suits a small flow at a high head and
   would be large for this flow.

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Flow velocity | 1.19 m/s | 1.19 m/s |
| Static head | 6 m (58.8 kPa) | 6 m (58.8 kPa) |
| Reynolds number | 47 560 at 20 °C; from the stated temperature | (not needed) |
| Friction loss | from the stated roughness and temperature; 1.31 to 1.59 m for smooth pipe to steel at 15 to 25 °C | 1.84 m (18.1 kPa) |
| Total head | 6 m + the response's losses | 7.84 m (76.9 kPa) |
| Hydraulic power | 14.69 W per meter of head | 115 W |
| Electrical power | from the response's efficiency | 288 W |
| Current | (not asked) | 24.0 A |
| Pump | pass criteria | pass criteria; a 12 V DC centrifugal pump |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Velocity | ±1% | Accepts 1.19 and 1.2 |
| Static head | ±0.5% | A given; in kPa the density and g used move it 0.2% |
| Reynolds number | ±5% of the value for the stated viscosity | Property tables differ, and responses round the viscosity |
| Friction in straight pipe, L0 and L1 | ±6% of the Colebrook value | Explicit friction-factor formulas (Swamee-Jain, Haaland, Blasius) are within 2% here; a factor read from a chart to two figures is within about 5% |
| Friction loss, L2 | ±2% | Printed forms of the Hazen-Williams equation give 1.826 to 1.864 m (table below) |
| Total head, L2 | ±0.05 m | Follows the friction spread: 7.83 to 7.86 m |
| Powers and current, L2 | ±1.5% | Follows the friction spread; a density of 1000 kg/m³ gives 115.4 W |

If a response at L0 or L1 states neither roughness nor temperature, a
friction loss from 1.23 to 1.68 m passes: the smooth-to-steel span at 15 to
25 °C with the 6% already added at each end. Likewise a Reynolds number from
34 700 to 56 100 passes when no temperature is stated.

The Hazen-Williams equation as different sources print it, for the L2 case:

| Form | Friction loss (m) |
| --- | --- |
| 10.67 L Q^1.852 / (C^1.852 d^4.8704), the reference | 1.844 |
| The same with the constant 10.654 | 1.841 |
| 10.583 L Q^1.852 / (C^1.852 d^4.87) | 1.826 |
| The velocity form, v = 0.849 C R^0.63 S^0.54 | 1.847 |
| US form, 0.2083 (100/C)^1.852 q^1.852 / d^4.8655 feet per 100 feet | 1.864 |
| US form, 4.52 q^1.852 / (C^1.852 d^4.8704) psi per foot | 1.842 |

## Alternatives accepted

- **Hazen-Williams at L0 and L1.** If the response uses it with a stated C,
  the friction in 35 m is 10.67 × 35 × Q^1.852 / (C^1.852 d^4.8704): 1.321 m
  for C = 150, 1.501 m for 140, 1.721 m for 130, 1.996 m for 120.
- **Velocity head added at L2.** If the response adds the outlet velocity
  head to the pump head: 7.916 m, 116.4 W, 291.0 W and 24.25 A.

## Pass criteria for the pump

At L0 and L1 the kind of pump, its supply and any margin are choices being
measured; record them. The choice passes when:

1. the response states the duty, 1.5 L/s (90 L/min, 5.4 m³/h, 23.8 US
   gal/min) at a head or pressure;
2. that head is its own total head (6 m plus its losses), or more if it
   says it adds a margin;
3. any pump rating it names covers 1.5 L/s at that head; and
4. the kind of pump suits a moderate flow at a low head. A centrifugal pump
   does. A positive-displacement pump passes only with a stated reason, and
   is marked for a reader.

At L2 the kind of pump passes when the response names it, gives a reason
that refers to the duty or to the 12 V supply, the kind suits the duty as in
point 4, and it runs from 12 V DC (directly or through a stated converter).

## Not accepted

| Value | What went wrong |
| --- | --- |
| Velocity 0.298 m/s | The diameter used as the radius |
| Friction 1.50 m (L2) | Fittings left out: 35 m, not 43 m |
| Friction 1.71 m (L2) | Darcy-Weisbach with the Colebrook factor, not the dictated equation |
| Total head 14.0 m (L2) | The 8 m of equivalent length added to the head |
| Total head 1.84 m (L2) | The lift left out |
| Hydraulic power 27.1 W (L2) | The lift left out |
| Electrical power 46.1 W (L2) | Multiplied by the efficiency in place of divided |
| Current 9.61 A (L2) | Efficiency left out |

## Checks

- Units of the hydraulic power: kg/m³ × m/s² × m³/s × m = W.
- The two friction methods can be compared at L2: Darcy-Weisbach with the
  Colebrook factor for a smooth plastic pipe (ε = 0.0015 mm) at 15 °C over
  43 m gives 1.71 m, against 1.84 m by Hazen-Williams with C = 140. They
  agree to 8%, which is as close as the two methods usually are.
- Energy check on the answer: 1.5 kg/s lifted through 7.84 m at 9.81 m/s²
  is 1.5 × 9.81 × 7.84 = 115 W.
- 24 A from a 12 V battery is a large current: 288 W for one hour takes
  24 Ah. That is a fact about the brief's numbers and may deserve a remark
  in a response; it is not graded.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_pipe_and_pump`, `darcy_friction_head`, `hazen_williams_head`,
  `hazen_williams_variants`).
