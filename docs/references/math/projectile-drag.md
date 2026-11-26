# Reference solution: projectile with air resistance

Task: [prompts/math/projectile-drag.yaml](../../../prompts/math/projectile-drag.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/math/projectile-drag.yaml](../../../checker/references/math/projectile-drag.yaml).

The question at every level: what is the range of a projectile launched at
25 m/s and 30° above the horizontal, with air resistance taken into account?

## What is checkable

- **L0 and L1: no checkable answer.** The range depends on the drag law and
  on constants (mass, size, drag coefficient, air density) that the prompt
  does not give. They are the model's choices and the thing being measured;
  record them. Two side checks are possible and neither grades the answer:
  the range with no air, if the response gives it, and the fact that a range
  with drag must be shorter than that.
- **L2: checkable.** The drag law, the constants, the scheme, the step and
  the landing rule are all dictated, so the answers are fixed.

## Givens

| Given | Value |
| --- | --- |
| Launch speed | 25 m/s |
| Launch angle | 30° above the horizontal |
| L2 only: mass, diameter | 0.43 kg, 0.22 m |
| L2 only: drag | Force proportional to the square of the speed; drag coefficient 0.25; air density 1.2 kg/m³ |
| L2 only: gravity | g = 9.81 m/s²; no spin, no wind |
| L2 only: method | Heun's method (improved Euler), time step 0.1 s; landing by linear interpolation between the last two steps; answers to 3 significant figures |

## Assumptions

1. Launch and landing are on the same flat ground: the projectile starts at
   y = 0 and lands when y returns to 0.
2. L2: the drag force is ½ ρ Cd A v², opposite to the velocity, with A the
   cross-section of the ball, π d²/4. Air density is constant.
3. L2: Heun's method is applied to the whole state (x, y, vx, vy). An Euler
   step predicts the state at the end of the step; the step is then taken
   with the mean of the slopes at the start and at the predicted state. The
   positions therefore move with the mean of the starting velocity and the
   **predicted** velocity.
4. L2: "the last two steps" are the last row with y above zero and the first
   row with y below it. The landing point is where the straight line between
   them crosses y = 0.
5. L2: the maximum height is the highest y in the table, above the launch
   level. The prompt set leaves the choice between the highest tabulated
   value and an interpolated peak to this reference; the two agree to 3
   significant figures (see Tolerances).

## Method

With no air, the range on flat ground is

    R0 = v² sin(2θ) / g

With drag, the equations of motion are

    dx/dt = vx                dy/dt = vy
    dvx/dt = −k v vx          dvy/dt = −g − k v vy
    v = sqrt(vx² + vy²)       k = ρ Cd A / (2 m)

One Heun step of size h from state s, with f(s) the right-hand sides above:

    s* = s + h f(s)                       (predictor)
    s_next = s + (h / 2) (f(s) + f(s*))   (corrector)

## Steps

1. No air: R0 = 25² × sin 60° / 9.81 = 625 × 0.866025 / 9.81 = **55.17 m**.
   (Time of flight 2 × 25 × sin 30° / 9.81 = 2.548 s; maximum height
   12.5² / (2 × 9.81) = 7.964 m.)
2. Area: A = π × 0.22² / 4 = 0.038013 m².
3. Drag constant: k = 1.2 × 0.25 × 0.038013 / (2 × 0.43) = 0.013260 per
   meter. At launch the drag deceleration is k v² = 0.013260 × 625 =
   8.29 m/s², close to g, so drag matters a great deal. (The terminal speed
   sqrt(g / k) is 27.2 m/s.)
4. Start: x = 0, y = 0, vx = 25 cos 30° = 21.6506 m/s, vy = 25 sin 30° =
   12.5 m/s.
5. First step, by hand. At the start v = 25, so k v = 0.33151 per second,
   and the slopes are f = (21.6506, 12.5, −7.1774, −13.9539). The predictor
   gives x* = 2.16506, y* = 1.25, vx* = 20.9329, vy* = 11.1046. There
   v* = 23.6960 and k v* = 0.31422, so the slopes are (20.9329, 11.1046,
   −6.5775, −13.2993). The corrector gives
   x = 0.05 × (21.6506 + 20.9329) = 2.1292 m,
   y = 0.05 × (12.5 + 11.1046) = 1.1802 m,
   vx = 21.6506 − 0.05 × (7.1774 + 6.5775) = 20.9629 m/s,
   vy = 12.5 − 0.05 × (13.9539 + 13.2993) = 11.1373 m/s.
6. Repeat until y is below zero. That happens at the 23rd step (table below).
7. Landing: between t = 2.2 s (y = 0.7914 m) and t = 2.3 s (y = −0.2199 m).
   The fraction of the step is 0.7914 / (0.7914 + 0.2199) = 0.7826, so
   time of flight = 2.2 + 0.7826 × 0.1 = **2.278 s** and
   range = 36.4359 + 0.7826 × (37.7140 − 36.4359) = **37.44 m**.
8. Maximum height: the highest y in the table is **6.406 m**, at t = 1.1 s
   (the vertical velocity changes sign between 1.0 s and 1.1 s).

## The L2 table

| t (s) | x (m) | y (m) | vx (m/s) | vy (m/s) |
| --- | --- | --- | --- | --- |
| 0.0 | 0.0000 | 0.0000 | 21.6506 | 12.5000 |
| 0.1 | 2.1292 | 1.1802 | 20.9629 | 11.1373 |
| 0.2 | 4.1925 | 2.2274 | 20.3294 | 9.8345 |
| 0.3 | 6.1950 | 3.1471 | 19.7440 | 8.5842 |
| 0.4 | 8.1412 | 3.9442 | 19.2009 | 7.3805 |
| 0.5 | 10.0351 | 4.6231 | 18.6953 | 6.2179 |
| 0.6 | 11.8802 | 5.1877 | 18.2229 | 5.0921 |
| 0.7 | 13.6796 | 5.6415 | 17.7799 | 3.9991 |
| 0.8 | 15.4361 | 5.9875 | 17.3626 | 2.9357 |
| 0.9 | 17.1521 | 6.2286 | 16.9681 | 1.8991 |
| 1.0 | 18.8297 | 6.3673 | 16.5934 | 0.8870 |
| 1.1 | 20.4708 | 6.4060 | 16.2360 | -0.1026 |
| 1.2 | 22.0769 | 6.3468 | 15.8935 | -1.0710 |
| 1.3 | 23.6495 | 6.1918 | 15.5638 | -2.0196 |
| 1.4 | 25.1897 | 5.9429 | 15.2450 | -2.9491 |
| 1.5 | 26.6985 | 5.6020 | 14.9353 | -3.8602 |
| 1.6 | 28.1767 | 5.1708 | 14.6333 | -4.7531 |
| 1.7 | 29.6251 | 4.6513 | 14.3377 | -5.6281 |
| 1.8 | 31.0442 | 4.0452 | 14.0471 | -6.4850 |
| 1.9 | 32.4345 | 3.3543 | 13.7608 | -7.3237 |
| 2.0 | 33.7964 | 2.5805 | 13.4779 | -8.1438 |
| 2.1 | 35.1301 | 1.7255 | 13.1976 | -8.9451 |
| 2.2 | 36.4359 | 0.7914 | 12.9195 | -9.7271 |
| 2.3 | 37.7140 | -0.2199 | 12.6433 | -10.4894 |

## Answers (L2)

| Quantity | Value | To 3 significant figures |
| --- | --- | --- |
| Range | 37.44 m | 37.4 m |
| Time of flight | 2.278 s | 2.28 s |
| Maximum height | 6.406 m | 6.41 m |
| Range with no air | 55.17 m | 55.2 m |

Drag cuts the range by about a third.

## Tolerances and why

Three legitimate ways of working give slightly different numbers:

| | Range (m) | Time (s) | Maximum height (m) |
| --- | --- | --- | --- |
| Heun as dictated (reference) | 37.436 | 2.2783 | 6.4060 tabulated, 6.4066 interpolated |
| Heun with the positions moved by the **corrected** velocity | 37.468 | 2.2799 | 6.4166 |
| The same model with no step error (fourth-order scheme, step 0.0001 s) | 37.465 | 2.2799 | 6.4136 |
| Euler's method at 0.1 s (wrong method) | 38.596 | 2.3543 | 6.9320 |

- **Range ±0.1 m.** To 3 significant figures the dictated scheme gives 37.4
  and the other two give 37.5, so both must pass. Euler's 38.6 fails.
- **Time of flight ±0.01 s.** All three give 2.28. Euler's 2.35 fails.
- **Maximum height ±0.03 m.** Accepts the tabulated value, an interpolated
  peak and the two variants (6.41 to 6.42). Euler's 6.93 fails.
- **Range with no air ±0.1 m.** Accepts 55.2, and g = 9.8 m/s² (55.23) at
  the levels where g is not given.
- **First-step values ±0.01.** Accept hand rounding and the
  corrected-velocity variant (x = 2.1307, y = 1.1819); Euler's first step
  (x = 2.165, y = 1.250, vx = 20.933, vy = 11.105) fails.

## Alternative accepted

- **g = 10 m/s² (L0 and L1 only).** If the response says so, its no-air
  range is 54.13 m. At L2 the brief gives 9.81 m/s².

## Not accepted (L2)

| Value | What went wrong |
| --- | --- |
| Range 38.6 m | Euler's method at the same step |
| Range 37.7 m | x of the first row below ground, with no interpolation |
| Range 55.2 m | No air |
| Time 2.30 s | Time of the first row below ground, with no interpolation |
| Height 7.96 m | No air |
| Area 0.152 m² | The diameter used as the radius |
| k = 0.0265 per meter | The factor ½ left out |

## Checks

- Halving the step moves the answers toward the converged values, as a
  second-order scheme should: at 0.05 s Heun gives 37.457 m, at 0.01 s
  37.465 m.
- The no-air values follow from the closed forms and from each other:
  R0 = vx × T0 = 21.6506 × 2.5484 = 55.17 m.
- With drag, every answer is smaller than its no-air value: 37.4 m against
  55.2 m, 2.28 s against 2.55 s, 6.41 m against 7.96 m. The descent is
  steeper than the climb (the peak is at 1.09 s, before half the flight
  time), as drag requires.
- The first step was worked by hand above and matches the table.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_projectile_drag`, `projectile_heun`), and the test compares this
  document's table with it.

## Note on the prompt

To 3 significant figures the dictated scheme gives a range of 37.4 m and the
exact solution of the same model gives 37.5 m. The tolerance accepts both.
A response that solves the model with a library solver, against the brief's
method, therefore still passes the answer check; whether it followed the
method is read elsewhere.
