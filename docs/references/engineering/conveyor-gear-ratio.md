# Reference solution: gear ratio for a conveyor

**Study data, not a design.** These values exist to grade answers collected
for a study of model defaults. Do not build from them.

Task: [prompts/engineering/conveyor-gear-ratio.yaml](../../../prompts/engineering/conveyor-gear-ratio.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/engineering/conveyor-gear-ratio.yaml](../../../checker/references/engineering/conveyor-gear-ratio.yaml).

The question at every level: what gear ratio does a conveyor need, if its
belt runs at 0.4 m/s on a drive drum 150 mm in diameter?

## What is checkable

- **L0 and L1:** the drum speed follows from the givens. The ratio also
  needs a motor speed, which the prompt leaves to the model. Record the
  speed assumed (about 1450 rpm suggests 50 Hz mains, about 1750 rpm 60 Hz),
  and grade the ratio against it.
- **L2:** the motor speed is given, so the exact ratio is fixed. The tooth
  counts are a choice with pass criteria.

## Givens

| Given | Value |
| --- | --- |
| Belt speed | 0.4 m/s |
| Drive drum diameter | 150 mm |
| L2 only: motor | 4-pole induction motor, 1725 rpm under load |
| L2 only: reduction | Two stages: a toothed belt from the motor, then a roller chain to the drum shaft |
| L2 only: teeth | Each pulley and sprocket has between 12 and 72 teeth |
| L2 only: tolerance | Belt speed within 2% of 0.4 m/s |

## Assumptions

1. The belt does not slip on the drum, and the belt speed is the speed of
   the drum's surface. The 150 mm is the diameter the belt runs on; the
   belt's thickness is left out.
2. "Gear ratio" is the reduction: motor speed divided by drum speed.
3. L0 and L1: the motor speed is the model's choice.
4. L2: a toothed belt and a roller chain do not slip, so each stage's ratio
   is its driven tooth count over its driving tooth count. Tooth counts are
   whole numbers from 12 to 72, both ends included.
5. L2: "at most 2%" includes 2% itself: the belt speed may be from 0.392 to
   0.408 m/s.

## Method

    drum speed       n = v / (π D)                 (revolutions per second)
    overall ratio    i = motor speed / drum speed
    two stages       i = (z2 / z1) × (z4 / z3)
    belt speed       v = π D × motor speed / i

z1 is the motor pulley, z2 the driven pulley, z3 the driving sprocket on the
same shaft, and z4 the sprocket on the drum shaft.

## Steps, L0 and L1

1. Drum circumference: π × 0.150 m = 0.47124 m.
2. Drum speed: 0.4 / 0.47124 = 0.84883 rev/s = **50.93 rpm** (5.333 rad/s).
3. Ratio for the motor speed the response states: motor rpm / 50.93.

   | Motor speed | Ratio | Typical source of the speed |
   | --- | --- | --- |
   | 1450 rpm | 28.47 | 4-pole motor on 50 Hz mains, under load |
   | 1500 rpm | 29.45 | 4-pole, 50 Hz, synchronous speed |
   | 1725 rpm | 33.87 | 4-pole on 60 Hz, under load (the L2 motor) |
   | 1750 rpm | 34.36 | 4-pole on 60 Hz, under load |
   | 1800 rpm | 35.34 | 4-pole, 60 Hz, synchronous speed |
   | 3000 rpm | 58.90 | 2-pole, 50 Hz, synchronous speed |

4. If the response then settles on a standard ratio (say 30:1 with a
   1450 rpm motor), the belt speed it gives is π × 0.150 × motor rpm /
   (60 × ratio): 0.380 m/s in that case.

## Steps, L2

1. Drum speed: **50.93 rpm**, as above.
2. Exact overall ratio: 1725 / 50.93 = **33.87**.
3. Ratios that keep the belt within 2%: from 33.87 / 1.02 = 33.21 to
   33.87 / 0.98 = 34.56.
4. The largest ratio one stage can give is 72 / 12 = 6. Two stages give at
   most 36, so the target is reachable, but only just: each stage must give
   at least 33.21 / 6 = 5.535. A stage ratio of 5.535 or more with at most
   72 teeth on the large wheel needs at most 72 / 5.535 = 13.01 teeth on the
   small one. So **each driving wheel has 12 or 13 teeth, and each stage
   reduces by between 5.54 and 6.00.** The split between the stages is close
   to even whatever the response prefers.
5. Trying every set of four tooth counts from 12 to 72 finds 17 that pass:

   | Motor pulley | Driven pulley | Driving sprocket | Drum sprocket | Ratio | Belt speed (m/s) | Off target |
   | --- | --- | --- | --- | --- | --- | --- |
   | 12 | 68 | 12 | 72 | 34.000 | 0.3985 | −0.38% |
   | 12 | 72 | 12 | 68 | 34.000 | 0.3985 | −0.38% |
   | 12 | 69 | 12 | 71 | 34.021 | 0.3982 | −0.44% |
   | 12 | 71 | 12 | 69 | 34.021 | 0.3982 | −0.44% |
   | 12 | 70 | 12 | 70 | 34.028 | 0.3981 | −0.46% |
   | 12 | 69 | 12 | 70 | 33.542 | 0.4039 | +0.98% |
   | 12 | 70 | 12 | 69 | 33.542 | 0.4039 | +0.98% |
   | 12 | 68 | 12 | 71 | 33.528 | 0.4041 | +1.02% |
   | 12 | 71 | 12 | 68 | 33.528 | 0.4041 | +1.02% |
   | 12 | 67 | 12 | 72 | 33.500 | 0.4044 | +1.11% |
   | 12 | 72 | 12 | 67 | 33.500 | 0.4044 | +1.11% |
   | 12 | 69 | 12 | 72 | 34.500 | 0.3927 | −1.83% |
   | 12 | 72 | 12 | 69 | 34.500 | 0.3927 | −1.83% |
   | 12 | 70 | 12 | 71 | 34.514 | 0.3925 | −1.86% |
   | 12 | 71 | 12 | 70 | 34.514 | 0.3925 | −1.86% |
   | 12 | 72 | 13 | 72 | 33.231 | 0.4077 | +1.92% |
   | 13 | 72 | 12 | 72 | 33.231 | 0.4077 | +1.92% |

   The closest is 12 and 68 on one stage with 12 and 72 on the other:
   ratio 34.00, belt speed 0.3985 m/s, 0.4% slow. The exact 33.87 cannot be
   reached.

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Drum speed | 50.93 rpm | 50.93 rpm |
| Overall ratio | motor rpm / 50.93 | 33.87 exactly |
| Tooth counts | (not asked) | any of the 17 sets; for example 12:68 and 12:72 |
| Actual ratio and belt speed | (not asked) | from the counts; 34.00 and 0.3985 m/s for the example |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Drum speed | ±0.5% | Accepts 50.9 and 51; π taken as 3.14 moves it 0.05% |
| Exact ratio at L2 | ±0.5% | Accepts 33.9 and a ratio worked from 50.9 rpm (33.89). A 1750 rpm motor (34.36) fails |
| Ratio at L0 and L1 | ±1% of the formula's value | Accepts a ratio worked from a drum speed rounded to 51 rpm |
| Ratio and belt speed from stated tooth counts | ±0.5% | Plain arithmetic on whole numbers |

## Pass criteria for the tooth counts (L2)

Any set passes when:

1. all four counts are whole numbers from 12 to 72;
2. the belt speed they give at 1725 rpm is from 0.392 to 0.408 m/s;
3. the ratio the response states equals the product of its stage ratios; and
4. the belt speed the response states is the speed its counts give.

How the response explains the split between the stages is not graded here.

## Alternative accepted

- **Belt thickness.** If the response adds a stated belt thickness t to the
  drum diameter (taking the belt speed at the middle of the belt), the drum
  speed is 0.4 × 60 / (π (0.150 + t)): 49.93 rpm for 3 mm.

## Not accepted

| Value | What went wrong |
| --- | --- |
| Drum speed 25.46 rpm | The diameter used as the radius |
| Drum speed 0.849 or 5.333 "rpm" | Revolutions or radians per second reported as rpm |
| Exact ratio 67.74 (L2) | The diameter used as the radius |
| Tooth counts 15:72 and 15:72 (L2) | Ratio 23.04, belt speed 0.588 m/s |
| Tooth counts 12:67 and 12:71 (L2) | Ratio 33.03, belt speed 0.4102 m/s, 2.5% fast |

## Checks

- Going back from the answer: 1725 rpm / 33.87 = 50.93 rpm, and
  50.93 / 60 × 0.47124 m = 0.400 m/s.
- The search over tooth counts covers every choice of the first three
  wheels and, for each, every drum sprocket that could bring the belt within
  3% of its speed. A search of all 61⁴ sets with no shortcut gave the same
  17. They are the sets the argument in step 4 predicts: both small wheels
  have 12 teeth, or one has 13 and both large wheels have 72.
- The YAML file's two checks pass these 17 sets and fail their near
  neighbors.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_conveyor_gear_ratio`, `conveyor_tooth_sets`).

## Note on the prompt

The L2 tooth range leaves very little room: only 17 sets of counts out of
about 14 million meet the 2% limit, all with 12 or 13 teeth on the small
wheels and 67 to 72 on the large ones. A response that picks larger small
wheels for smoother running (chain makers commonly advise 17 teeth or more)
cannot meet the limit. The brief is well posed, and it is a tighter problem than it
looks.
