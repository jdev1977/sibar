# Engineering prompts

Six engineering or mechanical tasks, each at three levels of direction (L0,
L1, L2) and in two wordings (A, B): 36 prompts. One YAML file per task, in
the format described in [../README.md](../README.md). Written for task T2.1
in [tasks.md](../../tasks.md), under the leak-check rules in
[docs/leak-check.md](../../docs/leak-check.md). The leak check itself is
T2.2; reference solutions are T2.3.

**The outputs are study data, not designs.** They are collected to measure
what models do by default (plan.md, "Engineering answers"). No prompt frames
a task as something people's safety depends on: the settings are coursework,
a small workshop, a hobby amplifier, a garden pond, a kitchen shelf of books
and a push button. The test checks a list of safety-critical words at every
level.

## The tasks

The plan lists seven example tasks. These six were kept because each needs a
different kind of engineering judgment:

| File | Task | Kind of problem | Choices it brings out |
| --- | --- | --- | --- |
| [cantilever-beam.yaml](cantilever-beam.yaml) | Size a cantilever beam | Structural sizing | Material, section, safety factor, checks, standards, self-weight |
| [conveyor-gear-ratio.yaml](conveyor-gear-ratio.yaml) | Gear ratio for a conveyor | Drive selection | Motor speed assumed, stages, kind of reduction, real parts |
| [heat-sink.yaml](heat-sink.yaml) | Heat-sink sizing | Thermal sizing | Interface assumed, natural or forced air, bought or worked size |
| [pipe-and-pump.yaml](pipe-and-pump.yaml) | Pipe pressure drop and pump choice | Fluid sizing | Friction method, roughness, fittings, temperature, pump type, margin |
| [shelf-bracket.yaml](shelf-bracket.yaml) | Shelf bracket with a CAD file | A part to draw and make | Dimensions, load, material, making method, CAD format |
| [compression-spring.yaml](compression-spring.yaml) | Compression spring design | Small part from formulas | Force and size, wire, ends, stress correction, fatigue |

Left out: picking bolts for a flange. Flange bolting is a pressure-equipment
question governed by standards tables, so it invites a safety-critical
real-world framing, and its main open choice (the standard cited) is
measured in the other tasks.

## The levels

- **L0 Bare**: the request and its givens only, such as "Size a cantilever
  beam 1.5 m long that carries a load of 4 kN at its free end."
- **L1 Brief**: L0 plus purpose and audience. No numbers beyond the givens.
- **L2 Directed**: a full brief: material and properties, limits, what to
  report, and directions on method and presentation.

L0 and L1 name none of the plan's open choices for engineering: no material,
safety factor, standard or code, unit word, check (stress, deflection,
buckling, fatigue), tolerance, making method, CAD or drawing format, or
solution type (a gearbox, a fan, fins, a pump type). The test file holds the
word list.

"CAD file" in the shelf-bracket task is the task as the plan names it: it
says a CAD file is wanted and leaves the format open, as "website" leaves the
technology open.

## Givens and checkable answers

The givens rule is the same as for math (see
[../math/README.md](../math/README.md#givens-numbers-that-every-level-carries)):
a task's givens are the numbers without which the question has no single
answer, nothing about method or format, identical word for word at every
level and in both wordings; L0 and L1 hold no other number; L2 may add
numbers but never changes a given.

Engineering has a second limit: a design has no single answer. So each task
has a **fixed** checkable answer that follows from the givens alone, and,
where the rest depends on a choice being measured (material, interface,
roughness, motor speed), a **conditional** answer that T2.10 grades against
the choice the model states. Each file repeats its line of this table in a
comment, for T2.3.

| Task | Givens | L0 and L1: fixed | L0 and L1: conditional | L2 |
| --- | --- | --- | --- | --- |
| cantilever-beam | 1.5 m, 4 kN | Reaction 4 kN, maximum moment 6 kN·m | Section, given the stated material and limits | Allowable 92 MPa; deflection governs; 51 mm by 102 mm |
| conveyor-gear-ratio | 0.4 m/s, 150 mm | Drum speed 50.9 rpm | Overall ratio, given the stated motor speed | Exact ratio 33.87 at 1725 rpm; belt speed within 2% for the stated tooth counts |
| heat-sink | 20 W, 1.0 °C/W, 125 °C, 40 °C | 4.25 °C/W junction to air; 3.25 °C/W case to air | Heat-sink limit, given the stated interface | Plate at most 2.95 °C/W; square side 135 mm; junction about 121 °C |
| pipe-and-pump | 1.5 L/s, 6 m, 35 m, 40 mm | Velocity 1.19 m/s; Reynolds number about 4.8e4; static head 6 m | Friction loss (about 1.35 to 1.6 m by Colebrook, smooth to commercial steel), given the stated roughness and temperature | Friction about 1.84 m; head about 7.84 m; about 115 W hydraulic, 288 W electrical, 24 A |
| shelf-bracket | None | Not checkable | Not checkable | Moment at the wall 200 lb·in; stress and screw force for the stated outline |
| compression-spring | None | Not checkable | Not checkable | Rate 6.0 lbf/in; rate and stresses consistent with the stated wire and coils |

Values are approximate until T2.3 writes and re-solves the references and
sets the tolerances.

## Units: given or left open

The plan lists the unit system as an open choice for engineering, and giving
numbers in a unit system closes that choice. The set handles this by task:

- **Units given (SI) at every level:** cantilever-beam, conveyor-gear-ratio,
  heat-sink, pipe-and-pump. These carry the checkable answers at L0 and L1.
  Unit system is not measured for them.
- **Units left open at L0 and L1:** shelf-bracket and compression-spring
  have no givens, so the unit system, the dimensions and the load are all
  choices the model makes. Unit system is measured on these two tasks.
  Their L2 gives US customary units (inches, pounds, psi), pointing away
  from the expected metric default.

SI at L0 and L1 is the convention of engineering science in every locale,
and US customary at L2 matches the US conventions used throughout the prompt
sets. Watts and degrees Celsius in the heat-sink task are the convention of
electronics everywhere. Decimal points are used throughout.

Two assumptions are left open on purpose and reveal a locale: the motor speed
in the conveyor task (about 1450 rpm suggests 50 Hz mains, about 1750 rpm
60 Hz) and, in the pipe task, the pump's power supply. Record them.

## L2 directions

Each L2 points the open choices **away** from the expected default for that
task, and never names that default, not even to forbid it ("a flat copper
plate", not "no fins"). The direction and the default are comments above L2
in each file; the defaults are guesses until the pilot measures them.

| Task | Dictated at L2 | Close to the expected default |
| --- | --- | --- |
| cantilever-beam | Solid rectangular aluminum bar, depth twice width, safety factor 3, deflection limit, whole millimeters, textbook sources, answer and checks table first | None found |
| conveyor-gear-ratio | Motor speed, two stages (toothed belt, then roller chain), tooth range, speed tolerance, tooth table first | None found |
| heat-sink | Flat vertical copper plate, thermal pad, stated surface coefficient, resistance chain first, 3 significant figures | None found |
| pipe-and-pump | Polyethylene with Hazen-Williams, fittings as equivalent length, 12 V solar supply with stated efficiency, kPa and meters of water, table first | None found |
| shelf-bracket | US units, birch plywood on a laser cutter taking flat outlines, quarter-circle profile, two screws into a stud, working stress | None found |
| compression-spring | US units, type 302 stainless wire with properties, bore limit, allowable stress, number of presses, table first | None found |

Left open at L2 as well: standards cited (except where a textbook source is
asked for), caveats and disclaimers, and the CAD format for the bracket. At
L2 the laser cutter is a real constraint written as a need ("takes only flat
outlines"), not as a format.

## The wordings

- **A** is an imperative opening with the task's verb: "Size", "Work out" or
  "Design". At L2 it is a structured brief with labeled lines.
- **B** is a request opening "Can you". At L2 it is prose in the asker's own
  voice and says "please" once.

Both wordings of a cell carry the same facts. As for websites, A and B
differ in mood, verb, length and, at L2, layout and voice: one bundled
wording factor.

## Invented content

The one place name, Wickley Lane Community Garden, is invented. No prompt
names a real company, product or standard, and none uses text from the
private catalogues.

## Versions

Each file has a `prompt_set_version`, "1" for all six. **Any change to the
text of any prompt in a file raises that file's version**; changes to
comments or `notes` do not. A change to a given also changes the reference
answer, so T2.3 must be told. The test pins each file's version and a
fingerprint of its texts; it cannot tell whether the version was raised, so
raise it in the same change. Before the first run, texts may be corrected
without a new version.

## Checks

`python -m pytest tests/test_pipeline_math_engineering_prompts.py` checks the
three Phase 2 sets together. For this set it checks, beyond the checks
listed for pipelines:

- every prompt holds its task's givens word for word, and L0 and L1 hold no
  other number and no count word;
- L0 and L1 use none of the listed engineering open choices;
- no L2 names a listed default (such as fins, a fan, music wire or a worm
  gearbox), and no prompt at any level uses a listed safety-critical word;
- the two units-open tasks have no givens and give inches at L2;
- each file has comments for its givens and for what is checkable;
- the two L2 wordings have the same numbers (givens aside) in the same order.
