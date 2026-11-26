# Reference solutions for the math and engineering tasks

One worked solution per task, written for T2.3 in [tasks.md](../../tasks.md).
Each one states its assumptions, the method, the steps with units, the
checks made, and the tolerance set on every answer. The answers themselves,
in the form the answer checker (T2.10) reads, are in
[checker/references/](../../checker/references/README.md), one YAML file per
task; that README describes the file format.

**The engineering answers are study data, not designs.** They exist to grade
answers collected for a study of what models do by default (plan.md,
"Engineering answers"). Nobody should build from them, and anything published
from them carries that note.

## The documents

| Task | L0 and L1 | L2 |
| --- | --- | --- |
| [math/loan-amortization](math/loan-amortization.md) | Payment 178.21; total interest 1692.65 | Last payment 178.27; total interest 1692.66; 60-row schedule |
| [math/projectile-drag](math/projectile-drag.md) | No checkable answer (the drag law is the model's choice) | Range 37.4 m; flight 2.28 s; height 6.41 m; no-air range 55.2 m |
| [math/hypothesis-test](math/hypothesis-test.md) | t = 3.87 on 7 degrees of freedom, p = 0.0061; reject at 5% | Rank sums 35 and 1; p = 1/64 = 0.0156; not rejected at 1% |
| [math/titration-curve](math/titration-curve.md) | Equivalence at 25.0 mL; pH 2.88, 4.75 and 8.72 at the start, half-way and equivalence | pH at eleven volumes |
| [math/least-squares-fit](math/least-squares-fit.md) | Slope 1.946; intercept 0.2143 | Standard errors, interval, residuals, R² 0.9974, 513.8 N/m |
| [math/entropy-explanation](math/entropy-explanation.md) | No checkable answer (rubric only) | No checkable answer; the brief's three counts are right |
| [engineering/cantilever-beam](engineering/cantilever-beam.md) | Reaction 4 kN; moment 6 kN·m; the section against the model's own limits | 51 mm by 102 mm; deflection governs; 67.8 MPa; 14.5 mm |
| [engineering/conveyor-gear-ratio](engineering/conveyor-gear-ratio.md) | Drum 50.93 rpm; ratio against the stated motor speed | Ratio 33.87; 17 sets of tooth counts pass |
| [engineering/heat-sink](engineering/heat-sink.md) | 4.25 °C/W in all; 3.25 °C/W case to air; the sink against the stated interface | Plate 2.95 °C/W; 0.0339 m²; 135 mm square; 121 °C |
| [engineering/pipe-and-pump](engineering/pipe-and-pump.md) | 1.19 m/s; 6 m static; friction against the stated roughness and temperature | Friction 1.84 m; head 7.84 m; 115 W; 288 W; 24.0 A |
| [engineering/shelf-bracket](engineering/shelf-bracket.md) | No checkable answer (nothing is given) | Moment 200 lb·in; screw forces and stress against the model's own outline |
| [engineering/compression-spring](engineering/compression-spring.md) | No checkable answer (nothing is given) | Rate 6.0 lbf/in; allowable 126 000 psi; the design against pass criteria |

## How they were made and checked

- Each task was solved from the prompt texts in
  [prompts/math/](../../prompts/math/README.md) and
  [prompts/engineering/](../../prompts/engineering/README.md). The rough
  values in those folders' comments and READMEs were compared only afterward.
- Every number is recomputed by
  [tests/reference_solvers.py](../../tests/reference_solvers.py), plain Python
  with no third-party package, and
  `python -m pytest tests/test_reference_solutions.py` compares the YAML
  files, and the long tables in these documents, with it.
- tasks.md asks for each solution to be re-solved independently by another
  model, with any disagreement resolved, and for the Human to spot-check two.
  Those steps are separate from this writing.

## What a tolerance is for

A tolerance accepts every answer that is right for the question asked, and
no answer that comes from a known mistake. Each document lists, for its
answers, the legitimate readings the tolerance was set to accept (a rounding
convention, a textbook constant, a shortcut formula that agrees to the
precision asked) and the wrong answers it was checked to reject. Where a
different, stated assumption gives a different answer that is still right
(another gravity value, an effective interest rate, a different reading of
how two screws share a load), the answer is an **alternative**: accepted
only when the response states that assumption, and recorded as the
alternative.

The files grade final answers. Whether a model used the method an L2 brief
dictates is read by the extractors and the rubric, not here: a shortcut that
reaches the same number passes.

## Partly checkable levels

At some levels the reference values cover only part of what the prompt asks:
the statics of the beam but not its size, the velocity in the pipe but not
its pressure drop, the resistance budget but not the heat sink. The YAML
files mark these levels `partial`. A correct result there means that part
is right, and the analysis should not read it as "the sizing is correct".

## Open-ended parts

Where the prompt leaves a choice to the model (a section, a heat sink, a
pump, tooth counts, a spring, a bracket outline), there is no single right
value. The documents give **pass criteria** for the choice, and formulas
that grade the numbers a response derives from its own choice.
