# Reference solution: heat-sink sizing

**Study data, not a design.** These values exist to grade answers collected
for a study of model defaults. Do not build from them.

Task: [prompts/engineering/heat-sink.yaml](../../../prompts/engineering/heat-sink.yaml),
prompt set version "1". Machine-readable answers:
[checker/references/engineering/heat-sink.yaml](../../../checker/references/engineering/heat-sink.yaml).

The question at every level: size a heat sink for a component that dissipates
20 W, with a junction-to-case thermal resistance of 1.0 °C/W, a maximum
junction temperature of 125 °C and surrounding air at 40 °C.

## What is checkable

- **L0 and L1:** the total thermal resistance allowed, and the share left
  from the case to the air, follow from the givens. The heat sink's own limit
  also depends on the interface between the case and the heat sink (paste, a
  pad, an insulating washer, or nothing), which the prompt leaves to the
  model. Record the interface assumed, and grade the limit against it. The
  heat sink chosen has pass criteria.
- **L2:** the plate, the pad and the surface coefficient are dictated, so
  every answer is fixed.

## Givens

| Given | Value |
| --- | --- |
| Power dissipated | 20 W |
| Junction-to-case thermal resistance | 1.0 °C/W |
| Maximum junction temperature | 125 °C |
| Air temperature | 40 °C |
| L2 only: heat sink | Flat, vertical copper plate, 3 mm thick, cooled by still air on both faces |
| L2 only: interface | A thermal pad that adds 0.3 °C/W |
| L2 only: surface | Combined convection and radiation coefficient 10 W/m²·°C on each face; the plate at one uniform temperature |
| L2 only: rounding | Square side rounded up to the next 5 mm; results to 3 significant figures |

## Assumptions

1. Steady state. All 20 W leaves through the heat sink; nothing leaves
   through the leads or the other faces of the case.
2. The heat path is a chain of thermal resistances in series.
3. The junction is allowed to reach its maximum, 125 °C, with no margin. A
   response that sizes for a lower junction temperature is graded by the
   formula, against the target it states.
4. L0 and L1: the interface resistance is the model's choice.
5. L2: the plate is at one temperature, as the brief says, so its resistance
   to the air is 1 / (h A), with A the area of both faces together. The four
   3 mm edges are not counted, and the area under the transistor is not
   taken off.

## Method

The chain, from hot to cold:

    junction → case        θjc = 1.0 °C/W        (given)
    case → heat sink       θcs                   (the interface)
    heat sink → air        θsa                   (the heat sink)

    Tj = Ta + P (θjc + θcs + θsa)

## Steps, L0 and L1

1. Temperature rise allowed: 125 − 40 = 85 °C.
2. Total resistance allowed, junction to air: 85 / 20 = **4.25 °C/W**.
3. Left from the case to the air: 4.25 − 1.0 = **3.25 °C/W**, for the
   interface and the heat sink together.
4. Heat sink limit for the interface the response states: 3.25 − θcs.

   | Interface assumed | θcs (°C/W) | Heat sink at most (°C/W) |
   | --- | --- | --- |
   | None counted | 0 | 3.25 |
   | Thermal paste | about 0.2 | 3.05 |
   | The L2 pad | 0.3 | 2.95 |
   | An insulating pad | about 0.5 | 2.75 |
   | A dry mica washer | about 1.0 | 2.25 |

5. If the response keeps a margin and sizes for a junction target Tt below
   125 °C, the limit is (Tt − 40) / 20 − 1.0 − θcs; for example 1.50 °C/W
   for 100 °C with a 0.5 °C/W pad.

## Steps, L2

1. Total allowed: (125 − 40) / 20 = **4.25 °C/W**.
2. Left for the plate: 4.25 − 1.0 − 0.3 = **2.95 °C/W**.
3. Area needed: the plate's resistance is 1 / (h A), so
   A = 1 / (10 × 2.95) = **0.0339 m²** (339 cm²), counting both faces.
4. One face is half of that, 0.01695 m². A square of that area has a side of
   sqrt(0.01695) = 0.1302 m = **130.2 mm**.
5. Rounded up to the next 5 mm: **135 mm**.
6. With a 135 mm plate: A = 2 × 0.135² = 0.03645 m²;
   θsa = 1 / (10 × 0.03645) = 2.743 °C/W.
7. Junction temperature: 40 + 20 × (1.0 + 0.3 + 2.743) = 40 + 80.87 =
   **120.9 °C**, which is 121 °C to 3 significant figures. (Plate 94.9 °C,
   case 100.9 °C.)

A 130 mm plate, the nearest 5 mm below, would give 125.2 °C, just over the
limit; that is why the side is rounded up.

## Answers

| Quantity | L0 and L1 | L2 |
| --- | --- | --- |
| Total resistance allowed, junction to air | 4.25 °C/W | 4.25 °C/W |
| Left from case to air | 3.25 °C/W | 3.25 °C/W |
| Left for the heat sink | 3.25 − θcs | 2.95 °C/W |
| Plate area | (not asked) | 0.0339 m², both faces together |
| Side of the square plate | (not asked) | 130.2 mm, rounded up to 135 mm |
| Junction temperature with it | from the model's choice | 121 °C |

## Tolerances and why

| Quantity | Tolerance | Reason |
| --- | --- | --- |
| Total, case-to-air and plate resistance | ±0.5% | Exact arithmetic on the givens |
| Heat sink limit for a stated interface | ±0.02 °C/W | Two decimals |
| Plate area | ±1% | Three significant figures asked: 0.0339 |
| Side of the square | exact, 135 mm | 130 mm does not meet the limit, and 140 mm is not the smallest |
| Junction temperature | ±0.5 °C | 121 to three significant figures; 120.9 with a decimal |

## Alternatives accepted (L2)

- **Area of one face.** "The plate area needed" can be read as the size of
  the plate, one face: 0.01695 m². Accepted when the response says that is
  what it gives.
- **Edges counted.** If the response says it counts the four 3 mm edges as
  cooled area too, the side before rounding is 127.2 mm, the rounded side is
  130 mm, and the junction is at 122.6 °C. This departs from the brief,
  which names the two faces; a match is recorded as this alternative, and
  130 mm with no such statement is wrong.

## Pass criteria for the heat sink chosen (L0 and L1)

The kind of heat sink (a catalog part, a plate, with or without a fan) is a
choice being measured and is not graded. It passes when, with the interface
and the heat sink the response chooses, 40 + 20 × (1.0 + θcs + θsa) is at or
under the junction temperature it sizes for.

## Not accepted

| Value | What went wrong |
| --- | --- |
| Total 6.25 °C/W | The air temperature not taken off: 125 / 20 |
| Plate limit 3.25 °C/W (L2) | The pad left out |
| Area 0.0308 m² (L2) | The pad left out |
| Side 185 mm (L2) | Only one face counted as cooled |
| Side 130 mm (L2) | Rounded down or to the nearest 5 mm |
| Junction 125 °C (L2) | The limit restated; the rounded-up plate runs cooler |

## Checks

- Units: °C / W for each resistance; 1 / (W/m²·°C × m²) = °C/W.
- Going back through the chain with the 135 mm plate: the plate is
  20 × 2.743 = 54.87 °C above the air, the case 20 × 0.3 = 6 °C above the
  plate, and the junction 20 × 1.0 = 20 °C above the case:
  40 + 54.87 + 6 + 20 = 120.87 °C.
- The resistances add to 4.043 °C/W, under the 4.25 allowed, and
  20 × 4.043 = 80.9 °C, under the 85 °C allowed.
- The uniform-temperature assumption is the brief's. It is generous to a
  thin plate this wide, since the corners run cooler than the middle in
  practice; that is a limit of the brief's model, not of the arithmetic.
- All of the above is recomputed in
  [tests/reference_solvers.py](../../../tests/reference_solvers.py)
  (`solve_heat_sink`).
