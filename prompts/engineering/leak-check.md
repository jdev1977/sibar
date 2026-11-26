# Leak check of the engineering prompts (T2.2)

All 36 prompts in this folder were read as sent and judged against the rules
in [docs/leak-check.md](../../docs/leak-check.md): rules 1 to 6 from the
website check, and rules 8 to 11, 14, 15 and 17, which this check added.

**Result: 29 pass as written, 7 rewritten.**

| Level | Pass | Rewritten |
| --- | --- | --- |
| L0 | 11 | 1 (pipe-and-pump B) |
| L1 | 11 | 1 (pipe-and-pump B) |
| L2 | 7 | 5 (cantilever-beam A and B, pipe-and-pump B, shelf-bracket A and B) |

No run had used these texts, so `prompt_set_version` stays "1" under the
pre-run rule in [README.md](README.md). The fingerprints in
[tests/test_pipeline_math_engineering_prompts.py](../../tests/test_pipeline_math_engineering_prompts.py)
were updated. The text before this check is in git at commit `9fa4ff6`.

**No given changed**, so no reference answer for L0 or L1 changes. One L2
brief changed in a way the reference solution (T2.3) must follow: the shelf
bracket now asks for the force on each screw in place of a pull-out force
(see that task below). The cantilever's L2 numbers are the same.

The outputs are study data, not designs. No prompt at any level frames a task
as something people's safety depends on; the settings are coursework, a small
workshop, a hobby amplifier, a garden pond, a kitchen shelf of books and a
push button.

## Rulings that apply to every task

The reasons are in [docs/leak-check.md](../../docs/leak-check.md).

1. **Givens stay** (rule 9). Four tasks give SI numbers at every level. That
   closes the unit system for those tasks and leans away from US practice,
   so standards cited, material grades, the motor speed and the pump's
   supply are defaults for a request in SI units. The unit system is
   measured on the two tasks without givens (shelf bracket, spring).
2. **The plan's noun stays** (rule 8): "gear ratio", "CAD file", "heat
   sink", "pressure drop".
3. **The verbs stay** (rule 10). A opens "Size", "Work out" or "Design"; B
   opens "Can you size", "Can you work out" or "Can you design".
4. **No idiom that leans to one locale** (rule 11).
5. **An assumption of the problem is content, unless what it sets aside is a
   recorded choice** (rule 15).
6. **A brief must be possible as written** (rule 17).
7. **B says "please" once at L2 and never below it; A never does.** US
   spelling throughout. Both hold in all 36 prompts.

Phrases that were flagged and kept are listed under each task.

## cantilever-beam

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The verb, the noun and the two givens. No material, section shape, safety factor, check or standard. |
| L0 B | pass | "Fixed at one end" for "cantilever", "tip" for "free end", "holds" for "carries a load of". The same facts. |
| L1 A | pass | Adds the audience (an engineering student) and the purpose (practicing beam problems before an exam). |
| L1 B | pass | "Working through practice problems before an exam". The same facts. |
| L2 A | rewritten | "Ignore the beam's own weight" named a choice that is recorded for this task (whether self-weight is counted) in order to set it aside. |
| L2 B | rewritten | As L2 A ("leave the bar's self-weight out"). |

Flagged and kept:

- "Size" (all levels) asks for dimensions and leaves open which ones and for
  what section.
- "1.5 m" and "4 kN" (all levels): see ruling 1.
- The exam setting (L1) may bring a textbook style and fewer caveats. It is
  the audience, and it was chosen so that nothing invites real use. A shift
  from L0 to L1 in caveats and standards includes this association.
- "Elementary beam formulas" (L2) are what any answer uses. The direction is
  to name the textbook source of each.
- "A safety factor of 3" and "6061-T6 aluminum" (L2) point away from the
  expected steel section and a factor near 1.5.

Rewrites:

**L2 A**

Old:
> - Ignore the beam's own weight.

New:
> - The load at the free end is the only load on the beam.

**L2 B**

Old:
> Leave the bar's self-weight out.

New:
> The force at the tip is the only load the bar carries.

## conveyor-gear-ratio

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The request and the two givens. No motor, no kind of reduction, no number of stages. |
| L0 B | pass | "What gear ratio a conveyor needs so that its belt moves at ..., driven by a ... drum". The same facts. |
| L1 A | pass | Adds the audience (a workshop owner) and the purpose (moving boxes from a packing bench to the loading door). |
| L1 B | pass | "Carry boxes from the packing bench to the loading door". The same facts. |
| L2 A | pass | Dictates the motor speed, two stages (a toothed belt, then a roller chain), a tooth range, a speed tolerance and a table first, each in positive form. |
| L2 B | pass | The same facts in the same order as A. The tooth range is given as its two limits. |

Flagged and kept:

- "Gear ratio" (all levels) may suggest gears. Kept under rule 8.
- "Drive drum" (all levels): some trades say "pulley" for this part. "Drum"
  is understood everywhere, and "pulley" is one of the kinds of reduction
  being measured, so it stays out of L0 and L1.
- The motor speed is not given at L0 and L1 on purpose. The ratio needs it,
  so the answer is graded against the speed the model states, and the speed
  shows a mains frequency.
- "Boxes" (L1) says the load is light. It is the purpose.
- "A 4-pole induction motor ... 1725 rpm" (L2) is close to the motor a model
  is likely to assume; see the table at the end.
- "The belt speed" (L2) means the conveyor belt, although the drive also has
  a toothed belt. The figure 0.4 m/s beside it makes that plain in both
  wordings.

## heat-sink

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The request and the four givens. No interface, no kind of cooling, no kind of heat sink. |
| L0 B | pass | "A part that gives off 20 W of heat", "the air around it". The same givens. |
| L1 A | pass | Adds the audience (a hobbyist building an audio amplifier at home), what the component is (its output transistor) and the duty (long listening sessions). |
| L1 B | pass | The same facts as A. |
| L2 A | pass | Dictates a flat vertical copper plate in still air, a thermal pad, a surface coefficient, the heat path set out first and 3 significant figures, each in positive form. |
| L2 B | pass | The same facts in the same order as A. |

Flagged and kept:

- The four givens (all levels) are the heat, the two temperatures and one
  thermal resistance. Together they fix the thermal budget and nothing
  else. "1.0 °C/W" shows two significant figures.
- "Surrounding air at 40 °C" (all levels) does not say whether the air
  moves.
- "A maximum junction temperature of 125 °C" leaves open whether the answer
  designs to the limit or keeps a margin, which is recorded.
- "Output transistor" (L1) may suggest a package and an insulating pad. It
  says what the component is.
- "Cope with long listening sessions" (L1) says the load is steady.
- "Cooled by still air" (L2) is likely the L0 default as well; see the table
  at the end. "A flat ... copper plate" says what is wanted without naming
  the shape it moves away from.

## pipe-and-pump

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The request and the four givens. No pipe material, fittings, temperature, friction method or kind of pump. |
| L0 B | rewritten | "Pick a pump to suit" is an idiom that leans to one locale, on a task that records a choice showing a locale (the pump's power supply). |
| L1 A | pass | Adds the audience (a community garden) and the purpose (moving water from its pond up to a storage tank at the top of the plot). |
| L1 B | rewritten | As L0 B. Otherwise the same facts as A. |
| L2 A | pass | Dictates the pipe, the friction equation and its coefficient, the fittings, the temperature, the power supply and efficiency, and a table first, each in positive form. |
| L2 B | rewritten | As L0 B. Otherwise the same facts in the same order as A. |

Flagged and kept:

- "Pressure drop" (all levels) is the plan's noun. With a 6 m lift it leaves
  open whether the answer gives the friction loss alone or the total; record
  which.
- "40 mm inside diameter" (all levels) is not a nominal size in any pipe
  system, so it suggests no material.
- "Pond" (L1) may suggest a strainer or a pump for dirty water. It is the
  purpose.
- The pump's power supply is open at L0 and L1 and shows a locale.
- "Black polyethylene" (L2) is in the same roughness family as the plastic
  pipe expected at L0; see the table at the end.
- "The kind of pump that suits this duty" (L2) leaves the kind of pump open
  at L2.

Rewrites:

**L0 B**

Old:
> Can you work out the pressure drop when 1.5 L/s of water is pumped 6 m uphill through 35 m of pipe with a 40 mm inside diameter, and pick a pump to suit?

New:
> Can you work out the pressure drop when 1.5 L/s of water is pumped 6 m uphill through 35 m of pipe with a 40 mm inside diameter, and pick a pump to match?

**L1 B** and **L2 B**: the same change in the same sentence ("pick a pump to
suit?" became "pick a pump to match?"). Nothing else in them changed.

## shelf-bracket

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The verb, the part and the file wanted. No size, load, material, making method, unit or CAD format. |
| L0 B | pass | "A bracket to hold up a shelf" and "give me a CAD file of it". The same facts. |
| L1 A | pass | Adds the audience (a homeowner) and the purpose (a kitchen shelf to hold a row of cookbooks). |
| L1 B | pass | The same facts as A. |
| L2 A | rewritten | The brief could not be built as written (rule 17): it asked for screw holes in a flat laser-cut piece whose screws go into the wall. |
| L2 B | rewritten | As L2 A. |

Flagged and kept:

- "CAD file" (all levels) says a file is wanted and names no format. Kept
  under rule 8. A model can only write text, so the format it picks (a
  model written as code, an exchange format, a flat outline) is the choice
  recorded.
- "A row of cookbooks" (L1) gives the load in words, with no number and no
  unit.
- Inches, pounds and psi (L2) point away from the expected metric default.
- "A laser cutter that takes only flat outlines" (L2) is a real constraint
  written as a need. It narrows the CAD format without naming one.
- "The bending moment where the bracket meets the wall" (L2) is still 40 lb
  at 5 in, 200 lb·in, whatever outline the model draws. It is the fixed
  checkable answer.

Rewrites:

**L2 A**

Old:
> - Each bracket is fixed to a wall stud with two screws, one above the other.

New:
> - At each bracket a vertical wood strip, 1 1/2 in square, is already fixed to the wall stud and runs down from the underside of the shelf. The bracket lies flat against the side of the strip and is held to it by two screws through the plywood, one above the other.

Old:
> - The bending moment where the bracket meets the wall, and the pull-out force on the top screw.

New:
> - The bending moment where the bracket meets the wall, and the force on each screw.

**L2 B**

Old:
> Every bracket goes into a wall stud with two screws, one placed above the other.

New:
> At each bracket there's already a vertical wood strip, 1 1/2 in square, fixed to the wall stud and running down from the underside of the shelf; the bracket will lie flat against the side of that strip, held by two screws through the plywood, one placed above the other.

Old:
> the pull-out force on the upper screw;

New:
> the force each screw has to take;

Why the brief changed this way: the bracket is one flat piece of 1/4 in
plywood that stands square to the wall, with one edge against the wall. A
laser cutter can only cut holes through the face of such a piece, and those
holes run along the wall, not into it. A screw into the wall would have to
pass through the 1/4 in edge, along the length of the piece. So the old brief
had no place for its screw holes, and no screw that could be pulled out of
the wall.

The new brief keeps every direction of the old one (US units, plywood, a
laser cutter that takes flat outlines, one flat piece, a quarter circle, two
screws one above the other, a working stress) and adds one fact: a wood strip
on the wall beside each bracket. The screws go through the face of the
plywood into the side of the strip, so the holes are ones the cutter can
make.

For the reference solution (T2.3): the screws are loaded across their
length, not along it. With the screws a distance e from the wall and s
apart, the load's moment about the pair is 40 × (5 − e) lb·in. Each screw
takes 40 × (5 − e) / s sideways, in opposite directions, and 20 lb downward.
For e = 3/4 in and s = 6 in that is 28.3 lb and 20 lb, 34.7 lb together. The
screw positions are the model's choice, so grade the forces against the
positions it states.

## compression-spring

| Prompt | Verdict | Reason |
| --- | --- | --- |
| L0 A | pass | The verb and the part. No size, force, unit, wire or end type. |
| L0 B | pass | "For me" adds no fact. |
| L1 A | pass | Adds the use (the push button on a home-built electronics project) and the purpose (the button springs back after each press). |
| L1 B | pass | "Return the button every time it's pressed". The same facts. |
| L2 A | pass | Dictates the lengths and the force in US units, the hole, the wire and its properties, an allowable stress, a number of presses and a table first, each in positive form. |
| L2 B | pass | The same facts in the same order as A. |

Flagged and kept:

- L0 has no number, so the unit system, the size and the force are all the
  model's choices. That is the design of this task.
- "After each press" (L1) may suggest a life in cycles. It is the purpose.
- "A garden weather station, so the wire is type 302 stainless steel" (L2)
  gives the need and then the material, away from the expected carbon
  spring wire.
- Inches, pounds-force and psi (L2) point away from the expected metric
  default.

## What each L2 dictates

For the extractors and the metrics. Everything else is left open at L2 as
well: standards cited (except where a textbook source is asked for), caveats
and disclaimers, and the CAD format of the bracket.

| Task | Dictated at L2 | Close to the expected default |
| --- | --- | --- |
| cantilever-beam | A solid rectangular aluminum bar, depth twice the width, a safety factor of 3, a deflection limit, whole millimeters, textbook sources, the answer and a table of checks first | None found |
| conveyor-gear-ratio | The motor speed, two stages (a toothed belt, then a roller chain), a tooth range, a speed tolerance, a tooth table first | A 4-pole induction motor is the likely assumed motor |
| heat-sink | A flat vertical copper plate, a thermal pad, a surface coefficient, the resistance chain first, 3 significant figures | Cooling by still air |
| pipe-and-pump | Polyethylene pipe, the Hazen-Williams equation, fittings as an equivalent length, a 12 V solar supply with a stated efficiency, kPa and meters of water, a table first | A smooth plastic pipe |
| shelf-bracket | US units, birch plywood on a laser cutter that takes flat outlines, a quarter-circle profile, two screws through its face into a wood strip, a working stress | None found |
| compression-spring | US units, type 302 stainless wire with its properties, a hole it must fit, an allowable stress, a number of presses, a table first | None found |

## Choices not to read as defaults

| Task | Choice | Why |
| --- | --- | --- |
| cantilever-beam, conveyor-gear-ratio, heat-sink, pipe-and-pump | Unit system, at every level | The givens are in SI (rule 9) |
| The same four | Standards cited, material grades, motor speed, pump supply as a bare share | Read them as defaults for a request in SI units (rule 9) |
| conveyor-gear-ratio | Motor speed, at L2 | Dictated, and close to the expected default |
| heat-sink | Kind of cooling, at L2 | Dictated, and close to the expected default |
| pipe-and-pump | Pipe material, at L2 | Dictated, and close to the expected default |
| All tasks | Assumptions stated or silent, at L2 | The brief gives them (rule 15) |

The expected defaults are guesses until the pilot measures them.
