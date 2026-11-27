"""Finding answers in a response (T2.10): hand-written responses with known
right and wrong answers, and responses where nothing may be concluded."""

import time

import pytest

from checker.answers import answers_from_dict
from checker.extract import extract
from checker.formulas import load_reference, reference_paths
from checker.grade import grade
from runner.prompts import load_prompts

REFERENCE = {p.stem: load_reference(p) for p in reference_paths()}


def check(task, level, text):
    reference = REFERENCE[task]
    return grade(reference, level, extract(reference, level, text))


def statuses(result, *names):
    return {name: result["quantities"][name]["status"] for name in names}


def one(task, level, text, name):
    return check(task, level, text)["quantities"][name]["status"]


def never_wrong(task, level, line, name, sentence):
    """A mismatch found in text is suspected, never wrong, whatever a sentence
    beside it says: only an answers file gives a final "wrong"."""
    assert one(task, level, line, name) == "suspected_wrong"
    for text in (f"{sentence}\n\n{line}", f"{line}\n\n{sentence}"):
        result = check(task, level, text)
        assert result["quantities"][name]["status"] in (
            "suspected_wrong", "could_not_determine"), (text, result["quantities"][name])
        assert "wrong" not in (result["verdict"], result["answers_verdict"]), text


def reviewed(task, level, text, **data):
    """Grade ``text`` with an answers file's entries put over what was found."""
    reference = REFERENCE[task]
    answers = extract(reference, level, text).merged(answers_from_dict(data))
    return grade(reference, level, answers)


LOAN_L0 = """## Monthly payment

The monthly rate is 7%/12 = 0.0058333.

$$M = P \\cdot \\frac{r}{1 - (1+r)^{-n}} = 9000 \\times \\frac{0.0058333}{0.29498} = 178.21$$

**Monthly payment: $178.21**

- Total paid: 60 × $178.21 = $10,692.60
- Total interest: $10,692.60 − $9,000 = **$1,692.60**
"""

LOAN_L2 = """The monthly payment is $178.21, due on the 1st.

| Item | Value |
|---|---|
| Monthly payment | $178.21 |
| Final payment | $178.27 |
| Total interest | $1,692.66 |
| First payment date | April 1, 2027 |
| Final payment date | March 1, 2032 |
"""


def schedule(rows=60):
    """A cent-rounded schedule, as a response would print it."""
    lines = ["| No. | Date | Payment | Interest | Principal | Balance |",
             "|---|---|---|---|---|---|"]
    cents, year, month = 900000, 2027, 4
    for number in range(1, rows + 1):
        interest = (cents * 7 + 600) // 1200
        paid = cents + interest if number == 60 else 17821
        cents -= paid - interest
        lines.append(f"| {number} | {year}-{month:02d}-01 | {paid / 100:.2f} | "
                     f"{interest / 100:.2f} | {(paid - interest) / 100:.2f} | "
                     f"{cents / 100:,.2f} |")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return "\n".join(lines) + "\n"


def test_a_loan_answer_in_prose_and_a_list():
    result = check("loan-amortization", "L0", LOAN_L0)
    assert result["verdict"] == "correct", result


def test_a_loan_table_and_schedule():
    result = check("loan-amortization", "L2", LOAN_L2 + "\n" + schedule())
    assert result["verdict"] == "correct", result
    assert statuses(result, "schedule_rows", "balance_after_12", "balance_after_60") == {
        "schedule_rows": "correct", "balance_after_12": "correct",
        "balance_after_60": "correct"}


def test_a_cut_schedule_is_not_counted():
    result = check("loan-amortization", "L2", LOAN_L2 + "\n" + schedule(12))
    assert statuses(result, "schedule_rows") == {"schedule_rows": "could_not_determine"}
    assert result["verdict"] == "could_not_determine"


@pytest.mark.parametrize("text", [
    "Monthly payment: $202.50",
    "**Monthly payment:** €202.50 per month.",
    "| Quantity | Value |\n|---|---|\n| Monthly payment | 202.50 |",
    "So the monthly payment is $202.50.",
    "Monthly payment: $202.50\n\nSo you pay 178.21 each month.",  # right one too
])
def test_a_wrong_payment_found_in_text_is_suspected(text):
    assert one("loan-amortization", "L0", text, "monthly_payment") == "suspected_wrong"


@pytest.mark.parametrize("text", [
    "You pay about 180 a month.",                       # no label
    "Monthly payment: see the table below.",            # no number
    "If the rate were 9%, the monthly payment: $186.83",
    "A naive estimate:\nMonthly payment = $202.50",
    "## Sanity check\nMonthly payment: $202.50",
    "Monthly payment: $178.21\n\nMonthly payment: $202.50",   # two values
    "Monthly payment: between $175 and $180",
    "Monthly payment: 178,21",                          # a decimal comma
    "Monthly payment (with insurance fees): $202.50",
    "Monthly payment: $202.50 × 60",
    "```python\nprint('Monthly payment: 202.50')\n```",
])
def test_nothing_is_concluded_from_unclear_text(text):
    assert one("loan-amortization", "L0", text,
               "monthly_payment") == "could_not_determine"


def test_an_effective_rate_answer_is_not_called_wrong():
    text = "Treating 7% as an effective annual rate:\n\nMonthly payment: $177.30"
    assert one("loan-amortization", "L0", text,
               "monthly_payment") == "could_not_determine"


HYPOTHESIS_L0 = """I use a one-sample t-test (H0: mean = 50, H1: mean ≠ 50), α = 0.05.

- Sample mean: x̄ = 409.4 / 8 = 51.175
- Sample standard deviation: s = 0.858
- t = (51.175 − 50) / (0.858/√8) = 3.87
- p-value ≈ 0.0061

Since p < 0.05, we reject the null hypothesis: the mean differs from 50.
"""

HYPOTHESIS_L2 = """**Decision:** At the 1% level we fail to reject H₀, so there is no proof that the batch is off target.

| Measurement | Difference | Rank |
|---|---|---|
| 50.8 | 0.8 | 3 |
| 51.6 | 1.6 | 6 |
| 49.7 | −0.3 | 1 |
| 52.3 | 2.3 | 8 |
| 51.1 | 1.1 | 4 |
| 50.4 | 0.4 | 2 |
| 52.0 | 2.0 | 7 |
| 51.5 | 1.5 | 5 |

W+ = 35
W− = 1

Exact two-sided p-value: p = 4/256 = 1/64 = 0.0156 (Wilcoxon signed-rank test).
"""


def test_a_t_test_answer():
    result = check("hypothesis-test", "L0", HYPOTHESIS_L0)
    assert result["verdict"] == "correct", result


def test_a_wilcoxon_answer_with_its_ranks():
    result = check("hypothesis-test", "L2", HYPOTHESIS_L2)
    assert result["verdict"] == "correct", result
    assert statuses(result, "ranks", "differences") == {
        "ranks": "correct", "differences": "correct"}


def test_the_wrong_decision_is_suspected():
    text = HYPOTHESIS_L2.replace("we fail to reject H₀", "we reject H₀")
    result = check("hypothesis-test", "L2", text)
    assert statuses(result, "decision_l2") == {"decision_l2": "suspected_wrong"}
    assert result["verdict"] == "suspected_wrong"


@pytest.mark.parametrize("text", [
    "We would reject H0 if p were below 0.05.",
    "There is not enough evidence here to reject H0.",
    "We reject H0. On reflection we fail to reject H0.",
    "The result speaks for itself.",
])
def test_an_unclear_decision_is_not_graded(text):
    assert one("hypothesis-test", "L2", text, "decision_l2") == "could_not_determine"


def test_two_tests_with_two_p_values_are_not_graded():
    text = ("One-sample t-test: p = 0.0061. Wilcoxon signed-rank test (exact): "
            "p = 0.0156. We reject H0 at the 5% level.")
    result = check("hypothesis-test", "L0", text)
    assert statuses(result, "p_value", "decision") == {
        "p_value": "could_not_determine", "decision": "correct"}


LSQ_L2 = """## Results

The fitted line is y = 0.2143 + 1.9464x.

| Quantity | Value |
|---|---|
| Standard error of the slope | 0.04469 mm/N |
| Standard error of the intercept | 0.1999 mm |
| R² | 0.9974 |
| Spring constant | 513.8 N/m |

95% confidence interval for the slope: [1.832, 2.061]

| x | y | fitted | residual |
|---|---|---|---|
| 1 | 2.3 | 2.161 | 0.139 |
| 2 | 4.1 | 4.107 | -0.007 |
| 3 | 5.8 | 6.054 | -0.254 |
| 4 | 8.2 | 8.000 | 0.200 |
| 5 | 9.9 | 9.946 | -0.046 |
| 6 | 11.6 | 11.893 | -0.293 |
| 7 | 14.1 | 13.839 | 0.261 |
"""


def test_a_least_squares_answer():
    result = check("least-squares-fit", "L2", LSQ_L2)
    assert result["verdict"] == "correct", result


def test_a_line_through_the_origin_is_suspected():
    text = "Slope: 1.9893\nIntercept: 0"
    result = check("least-squares-fit", "L0", text)
    assert statuses(result, "slope", "intercept") == {"slope": "suspected_wrong",
                                                      "intercept": "suspected_wrong"}


PROJECTILE_L2 = """| Quantity | With drag | No air |
|---|---|---|
| Range (m) | 37.4 | 55.2 |
| Time of flight (s) | 2.28 | 2.55 |
| Maximum height (m) | 6.41 | 7.96 |
"""


def test_a_projectile_comparison_table():
    result = check("projectile-drag", "L2", PROJECTILE_L2)
    assert result["verdict"] == "correct", result


def test_a_range_under_a_no_air_heading():
    text = ("## With drag\nRange: 37.4 m\nFlight time: 2.28 s\nMaximum height: 6.41 m\n\n"
            "## Without air resistance\nRange: 55.2 m\n")
    result = check("projectile-drag", "L2", text)
    assert result["verdict"] == "correct", result


def test_euler_values_are_suspected():
    text = "Range: 38.6 m\nTime of flight: 2.35 s\nMaximum height: 6.93 m"
    result = check("projectile-drag", "L2", text)
    assert statuses(result, "range", "flight_time", "max_height") == dict.fromkeys(
        ["range", "flight_time", "max_height"], "suspected_wrong")


def titration(values):
    rows = "\n".join(f"| {v} | {ph} |" for v, ph in values)
    return f"| Volume of NaOH (mL) | pH |\n|---|---|\n{rows}\n"


PH = [(0, 2.88), (5.0, 4.14), (10.0, 4.57), (12.5, 4.75), (20.0, 5.35), (24.0, 6.13),
      (25.0, 8.72), (26.0, 11.29), (30.0, 11.96), (40.0, 12.36), (50.0, 12.52)]


def test_a_titration_table():
    text = titration(PH) + "\nEquivalence point volume: 25.0 mL\n"
    result = check("titration-curve", "L2", text)
    assert result["verdict"] == "correct", result


def test_a_wrong_ph_in_a_table():
    values = [(v, 7.00 if v == 25.0 else ph) for v, ph in PH]
    result = check("titration-curve", "L2", titration(values))
    assert statuses(result, "ph_25_ml", "ph_26_ml") == {"ph_25_ml": "suspected_wrong",
                                                         "ph_26_ml": "correct"}


def test_a_cantilever_answer():
    text = """Reaction force: R = 4 kN
Maximum bending moment: M = 4 kN × 1.5 m = 6 kN·m
Required section modulus: S = M/σ = 65 217 mm³
Required second moment of area: 4.354 × 10^6 mm⁴
Final width: 51 mm
Final depth: 102 mm
Bending stress: 67.8 MPa
Tip deflection: 14.5 mm

Deflection governs the design.
"""
    result = check("cantilever-beam", "L2", text.replace("65 217", "65,217"))
    assert result["verdict"] == "correct", result
    spaced = check("cantilever-beam", "L2", text)       # a space as separator
    assert spaced["quantities"]["required_section_modulus"]["status"] == \
        "could_not_determine"


def test_self_weight_is_not_called_wrong():
    text = ("Including the self-weight of 0.2 kN/m:\n\n"
            "Maximum bending moment: 6.23 kN·m")
    assert one("cantilever-beam", "L0", text,
               "max_bending_moment") == "could_not_determine"
    assert one("cantilever-beam", "L0", "Maximum bending moment: 3 kN·m",
               "max_bending_moment") == "suspected_wrong"


def test_the_motor_speed_grades_the_ratio():
    text = ("Assume a 1450 rpm motor.\nDrum speed: 50.9 rpm\n"
            "Required overall ratio: 28.5:1")
    result = check("conveyor-gear-ratio", "L0", text)
    assert result["verdict"] == "correct", result
    wrong = check("conveyor-gear-ratio", "L0", text.replace("28.5", "33.9"))
    assert statuses(wrong, "overall_ratio") == {"overall_ratio": "suspected_wrong"}
    two = check("conveyor-gear-ratio", "L0",
                text + "\nA 960 rpm motor would also work.")
    assert statuses(two, "overall_ratio") == {"overall_ratio": "could_not_determine"}


def test_a_heat_sink_answer():
    text = """Maximum total thermal resistance: (125 − 40)/20 = 4.25 °C/W
Maximum plate resistance: 2.95 °C/W
Required plate area: 0.0339 m²
Final side length: 135 mm
Resulting junction temperature: 120.9 °C
"""
    result = check("heat-sink", "L2", text)
    assert result["verdict"] == "correct", result


def test_a_junction_margin_is_not_called_wrong():
    text = ("Keeping a 25 °C margin on the junction:\n\n"
            "Allowable total resistance: 3.0 °C/W")
    assert one("heat-sink", "L0", text, "total_resistance") == "suspected_wrong"


def test_a_pipe_table_in_two_units():
    text = """| Quantity | m of water | kPa |
|---|---|---|
| Friction loss | 1.84 | 18.1 |
| Total head | 7.84 | 76.9 |

| Quantity | Value |
|---|---|
| Flow velocity | 1.19 m/s |
| Hydraulic power | 115 W |
| Electrical power | 288 W |
| Battery current | 24.0 A |
"""
    result = check("pipe-and-pump", "L2", text)
    assert result["answers_verdict"] == "correct", result
    assert result["verdict"] == "could_not_determine"       # the pump's kind


def test_a_shelf_bracket_answer():
    text = """Bracket radius: R = 10 in
Moment at the wall: 40 lb × 5 in = 200 lb·in
Bending stress at the wall: 48 psi
Downward force on each screw: 20 lb
"""
    result = check("shelf-bracket", "L2", text)
    assert statuses(result, "moment_at_wall", "quarter_disc_stress_at_wall",
                    "screw_downward_force") == dict.fromkeys(
        ["moment_at_wall", "quarter_disc_stress_at_wall", "screw_downward_force"],
        "correct")


def test_a_spring_design_from_its_stated_dimensions():
    text = """Wire diameter: 0.030 in
Mean coil diameter: 0.235 in
Active coils: 13
Total coils: 15
Required spring rate: 6.0 lbf/in
Actual spring rate: 6.00 lbf/in
Solid length: 0.450 in
"""
    result = check("compression-spring", "L2", text)
    assert statuses(result, "spring_rate", "rate_from_geometry", "solid_length") == \
        dict.fromkeys(["spring_rate", "rate_from_geometry", "solid_length"], "correct")
    assert result["criteria"]["design_meets_requirements"]["items"][
        "fits_the_hole"]["status"] == "pass"
    assert result["verdict"] != "correct"       # its stress was not found


def test_a_cut_off_response_is_never_wrong():
    reference = REFERENCE["loan-amortization"]
    answers = extract(reference, "L0", "Monthly payment: $202.50", truncated=True)
    result = grade(reference, "L0", answers)
    found = result["quantities"]["monthly_payment"]
    assert found["status"] == "suspected_wrong"
    assert "cut off" in found["reason"]


@pytest.mark.parametrize("task", sorted(REFERENCE))
def test_restating_the_prompt_is_never_correct_or_wrong_by_itself(task):
    kind = REFERENCE[task]["project_type"]
    prompts = {p.task_id: p for p in load_prompts([f"prompts/{kind}"])}
    for level in ("L0", "L1", "L2"):
        for wording in ("A", "B"):
            text = prompts[task].texts[(level, wording)]
            result = check(task, level, text)
            found = {r["status"] for r in result["quantities"].values()}
            assert found <= {"could_not_determine"}, (level, wording, result)


@pytest.mark.parametrize("task", sorted(REFERENCE))
def test_empty_and_wordless_responses(task):
    for text in ("", "I cannot help with that.", "| a |\n|---|\n"):
        result = check(task, "L2", text)
        assert result["verdict"] in ("could_not_determine", "not_checkable")


@pytest.mark.parametrize("text", [
    "Monthly payment " * 20000,
    "Monthly payment: " + "9" * 200000,
    ("Monthly payment: " + "1 = " * 90 + "2\n") * 5000,
    "|" * 100000 + "\n" + "|-" * 50000,
    "| No. | Balance |\n|---|---|\n" + "| 1 | 2 |\n" * 50000,
    "\\frac{" * 20000 + "**" * 20000 + "$" * 20000,
    "motor " * 50000 + "\n" + "(" * 100000,
    "p = 1/0\nMonthly payment: 1/0\nMonthly payment: 9e999",
])
def test_hostile_text_is_bounded(text):
    started = time.monotonic()
    for task in ("loan-amortization", "hypothesis-test", "conveyor-gear-ratio"):
        check(task, "L0", text)
    assert time.monotonic() - started < 20


@pytest.mark.parametrize("task,level,text,name", [
    ("loan-amortization", "L0",
     "## Option B: four years\nMonthly payment: $215.52", "monthly_payment"),
    ("loan-amortization", "L0",
     "| Item | Four-year option |\n|---|---|\n| Monthly payment | 215.52 |",
     "monthly_payment"),
    ("hypothesis-test", "L2",
     "We need W = 0 to reject H0. W = 1, so H0 stands.", "decision_l2"),
    ("hypothesis-test", "L2",
     "A smaller rank sum is required in order to reject H0.", "decision_l2"),
    ("hypothesis-test", "L0",
     "t-test. 95% confidence interval for the mean difference: [0.46, 1.89]",
     "ci95_low"),
    ("hypothesis-test", "L0",
     "t-test. The one-tailed result follows.\n\nOne-tailed:\np = 0.0031", "p_value"),
    ("cantilever-beam", "L2",
     "Next we ask whether stress governs the design.", "governing_limit"),
    ("conveyor-gear-ratio", "L0",
     "Motor: 1450 rpm. A 960 rpm unit is cheaper.\nRequired overall ratio: 18.85",
     "overall_ratio"),
])
def test_other_cases_and_rules_are_not_graded(task, level, text, name):
    assert one(task, level, text, name) == "could_not_determine"


@pytest.mark.parametrize("text,status", [
    ("We therefore reject H0 at the 1% level.", "suspected_wrong"),
    ("**Decision: reject the null hypothesis.**", "suspected_wrong"),
    ("At the 1% level, H0 is not rejected.", "correct"),
    ("So we do not reject the null hypothesis.", "correct"),
])
def test_plain_decisions(text, status):
    assert one("hypothesis-test", "L2", text, "decision_l2") == status


def test_a_no_air_figure_named_in_its_sentence():
    text = ("In a vacuum, range = 55.2 m.\n\nRange: 37.4 m")
    result = check("projectile-drag", "L2", text)
    assert statuses(result, "range", "range_no_air") == {"range": "correct",
                                                         "range_no_air": "correct"}


@pytest.mark.parametrize("text", [
    "Monthly payment: $178.21/month", "Monthly payment ≈ $178.21 per month.",
    r"$$\boxed{\text{Monthly payment} = \$178.21}$$",
])
def test_spellings_of_a_payment(text):
    assert one("loan-amortization", "L0", text, "monthly_payment") == "correct"


def test_labels_with_what_they_cover_in_brackets():
    text = ("| Quantity | Value |\n|---|---|\n"
            "| Required total resistance (junction to air) | 4.25 °C/W |\n"
            "| Required plate area (both faces) | 0.0339 m² |")
    result = check("heat-sink", "L2", text)
    assert statuses(result, "total_resistance", "plate_area") == {
        "total_resistance": "correct", "plate_area": "correct"}
    ph = "pH at half-equivalence (12.5 mL) = pKa = 4.74"
    assert one("titration-curve", "L0", ph, "ph_12_5_ml") == "correct"


def test_a_motor_speed_with_a_thousands_comma():
    text = "A motor at 1,450 rpm.\nRequired gear ratio: i = 1450/50.93 = 28.5:1"
    assert one("conveyor-gear-ratio", "L0", text, "overall_ratio") == "correct"


def test_a_count_of_payments_is_not_the_total_paid():
    assert one("loan-amortization", "L0", "Total payments: 60",
               "total_paid") == "could_not_determine"


def test_a_decision_under_another_case_is_not_graded():
    text = "## If the level were 5%\nWe reject H0."
    assert one("hypothesis-test", "L2", text, "decision_l2") == "could_not_determine"


# --- review round 1 -----------------------------------------------------------

DIFFERENCES = r"""One-sample t-test on the differences d = x - 50.

Mean = 1.175
Standard deviation: s = 0.858
t = 1.175 / (0.858/√8) = 3.87, p = 0.0061, so we reject H0.
95% confidence interval: (0.46, 1.89)
"""


def test_the_mean_of_the_differences_is_not_a_wrong_sample_mean():
    result = check("hypothesis-test", "L0", DIFFERENCES)
    assert statuses(result, "sample_mean", "ci95_low", "ci95_high") == dict.fromkeys(
        ["sample_mean", "ci95_low", "ci95_high"], "suspected_wrong")
    assert result["verdict"] == "suspected_wrong"


# One case for each quantity an assumption of the response's own moves: every
# sentence of rounds 1 to 3 that could lead to a false "wrong" is kept, and
# none may now give a final "wrong" (see never_wrong).
ASSUMED = [
    ("heat-sink", "L2", "With a 10 °C safety margin on the junction:", [
        ("Required plate area: 0.0388 m²", "plate_area"),
        ("Final side length: 140 mm", "square_side"),
        ("Resulting junction temperature: 114 °C", "junction_temperature")]),
    ("pipe-and-pump", "L2", "I add a 10% safety margin to the head.", [
        ("Friction loss: 2.03 m", "friction_loss"),
        ("Total head: 8.63 m", "total_head"),
        ("Hydraulic power: 127 W", "hydraulic_power"),
        ("Electrical power: 317 W", "electrical_power"),
        ("Battery current: 26.4 A", "battery_current")]),
    ("cantilever-beam", "L2", "I keep a 10% margin on the load.", [
        ("Required section modulus: 71,739 mm³", "required_section_modulus"),
        ("Final width: 53 mm", "width"),
        ("Tip deflection: 12.4 mm", "tip_deflection")]),
    ("cantilever-beam", "L0", "A safety factor of 1.5 on the load is applied.", [
        ("Maximum bending moment: 9 kN·m", "max_bending_moment"),
        ("Reaction force: 6 kN", "reaction_force")]),
    ("conveyor-gear-ratio", "L2", "Allowing for 2% belt slip:", [
        ("Drum speed: 52.0 rpm", "drum_speed"),
        ("Required ratio: 33.2", "exact_ratio")]),
    ("shelf-bracket", "L2", "With a safety factor of 2 on the load:", [
        ("Moment at the wall: 400 lb·in", "moment_at_wall"),
        ("Downward force on each screw: 40 lb", "screw_downward_force")]),
    ("compression-spring", "L2", "I include a 10% margin on the force.", [
        ("Required spring rate: 6.6 lbf/in", "spring_rate")]),
    ("loan-amortization", "L0", "This includes a monthly account fee of $5.", [
        ("Monthly payment: $183.21", "monthly_payment")]),
    ("titration-curve", "L0", "Using activity coefficients (Davies):", [
        ("Initial pH: 2.95", "ph_0_ml")]),
    ("least-squares-fit", "L0", "The last point is an outlier and is excluded.", [
        ("Slope: 1.89", "slope")]),
    ("projectile-drag", "L0", "Taking a launch height of 1.5 m.", [
        ("Range without air resistance: 57.6 m", "range_no_air")]),
]


@pytest.mark.parametrize("task,level,assumption,line,name", [
    (task, level, assumption, line, name)
    for task, level, assumption, lines in ASSUMED for line, name in lines])
def test_a_stated_assumption_never_makes_a_mismatch_wrong(task, level, assumption, line,
                                                         name):
    never_wrong(task, level, line, name, assumption)


def test_a_bracket_after_a_value_does_not_replace_it():
    for text in ("Monthly payment: $178.21 (rate = 0.5833)",
                 "Total interest = $1,692.65 (60 payments, total = 10692.65)"):
        result = check("loan-amortization", "L0", text)
        assert "wrong" not in {r["status"] for r in result["quantities"].values()}
        assert "correct" in {r["status"] for r in result["quantities"].values()}, result
    text = "Total head: 7.84 m (static 6 m + friction = 1.84 m)"
    assert one("pipe-and-pump", "L2", text, "total_head") == "correct"
    chain = "Maximum total thermal resistance: (125 - 40)/20 = 4.25 °C/W"
    assert one("heat-sink", "L2", chain, "total_resistance") == "correct"


@pytest.mark.parametrize("text", [
    "t* = 2.365", "t^* = 2.365", "t^{*} = 2.365",
    "| Quantity | Value |\n|---|---|\n| t* | 2.365 |",
])
def test_a_starred_symbol_is_another_quantity(text):
    assert one("hypothesis-test", "L0", text, "t_statistic") == "could_not_determine"


@pytest.mark.parametrize("heading", [
    "## Option B: 4 years", "**Scenario 2: 4 years**", "### Check at r = 9%",
])
def test_a_heading_with_a_number_still_covers_what_follows(heading):
    text = f"{heading}\nMonthly payment: $215.52"
    assert one("loan-amortization", "L0", text,
               "monthly_payment") == "could_not_determine"


@pytest.mark.parametrize("after", [
    "Correction: the payment is actually 181.00.",
    "Final answer: you pay 181 a month.",
    "## Summary\nExpect to pay about $181 each month.",
    "On reflection, it comes to 181.",
])
def test_an_unread_correction_puts_found_values_in_doubt(after):
    text = f"Monthly payment: $178.21\n\n{after}"
    assert one("loan-amortization", "L0", text,
               "monthly_payment") == "could_not_determine"


@pytest.mark.parametrize("after", [
    "Final answer: $178.21.",
    "## Summary\nYou repay 9000 over 5 years at 178.21 a month.",
    "In summary, the loan is affordable.",
    "## Summary\n- You pay $178.21 for 60 months\n- On $9,000 over 5 years",
])
def test_a_summary_that_repeats_the_values_changes_nothing(after):
    text = f"Monthly payment: $178.21\n\n{after}"
    assert one("loan-amortization", "L0", text, "monthly_payment") == "correct"


# --- review round 2 -----------------------------------------------------------

# Phrases once taken as harmless: a mismatch beside one is still only suspected.
NOT_ASSUMED = [
    ("hypothesis-test", "L0", "Sample mean: 52.4", "sample_mean", (
        "The 95% interval excludes 50.",
        "The 95% confidence interval (50.46, 51.89) excludes 50.0.",
        "The confidence interval excludes the target value.",
        "The interval excludes the value 50.",
        "There is a significant difference.",
        "There is no statistically significant difference.",
        "The mean differs from 50.",
        "The difference from 50 is significant.",
    )),
    ("hypothesis-test", "L0", "t = 2.11", "t_statistic", (
        "The 95% interval excludes 50.",
    )),
    ("loan-amortization", "L0", "Monthly payment: $202.50", "monthly_payment", (
        "Note: this excludes taxes and insurance.",
        "This figure does not include insurance, taxes or fees.",
    )),
    ("pipe-and-pump", "L2", "Total head: 9.9 m", "total_head", (
        "For safety, use a check valve.",
        "Fuse the battery lead with a margin above the current.",
    )),
    ("heat-sink", "L2", "Required plate area: 0.0500 m²", "plate_area", (
        "For safety, insulate the plate from the chassis.",
    )),
    ("projectile-drag", "L2", "Range: 45.0 m", "range", (
        "Assuming launch from ground level (initial height 0).",
        "Initial height: 0 m.",
        "Ignore spin and wind.",
    )),
    ("cantilever-beam", "L0", "Maximum bending moment: 3 kN·m", "max_bending_moment", (
        "A safety factor of 3 is used on the yield strength.",
        "The factor of safety of 3.0 is as given.",
    )),
    ("titration-curve", "L0", "Initial pH: 3.40", "ph_0_ml", (
        "All values are at 25 °C.",
    )),
    ("least-squares-fit", "L0", "Slope: 1.50", "slope", (
        "The 95% interval excludes zero.",
    )),
]


@pytest.mark.parametrize("task,level,line,name,sentence", [
    (task, level, line, name, sentence)
    for task, level, line, name, sentences in NOT_ASSUMED for sentence in sentences])
def test_a_sentence_that_states_no_assumption_changes_nothing(
        task, level, line, name, sentence):
    never_wrong(task, level, line, name, sentence)


@pytest.mark.parametrize("task,level,assumption,line,name", [
    ("hypothesis-test", "L0", "I work with d = x - 50.", "Mean = 1.175", "sample_mean"),
    ("hypothesis-test", "L0", "Differences from 50: 0.8, 1.6, -0.3.", "Mean = 1.175",
     "sample_mean"),
    ("hypothesis-test", "L0", "I excluded the value 49.7.", "Mean = 51.4", "sample_mean"),
    ("least-squares-fit", "L0", "Excluding the last point:", "Slope: 1.89", "slope"),
    ("least-squares-fit", "L0", "A weighted least-squares fit is used.", "Slope: 1.89",
     "slope"),
    ("loan-amortization", "L0", "A $1,000 down payment comes off first.",
     "Monthly payment: $158.42", "monthly_payment"),
    ("pipe-and-pump", "L2", "Safety factor: 1.2 on the head.", "Total head: 9.4 m",
     "total_head"),
    ("pipe-and-pump", "L2", "With a **10%** margin:", "Total head: 8.6 m", "total_head"),
    ("projectile-drag", "L0", "Initial height h0 = 1.5 m.",
     "Range without air resistance: 57.6 m", "range_no_air"),
    ("projectile-drag", "L0", "I include a headwind.",
     "Range without air resistance: 50.0 m", "range_no_air"),
    ("heat-sink", "L2", "I design for a junction temperature of 100 °C.",
     "Required plate area: 0.0600 m²", "plate_area"),
    ("cantilever-beam", "L0", "Using a load factor of 1.5:",
     "Maximum bending moment: 9 kN·m", "max_bending_moment"),
    ("cantilever-beam", "L0", "The self-weight is included.",
     "Maximum bending moment: 6.4 kN·m", "max_bending_moment"),
    ("shelf-bracket", "L2", "I apply a factor of safety of 2.",
     "Moment at the wall: 400 lb·in", "moment_at_wall"),
    ("compression-spring", "L2", "With a preload of 0.5 lbf:",
     "Required spring rate: 5.1 lbf/in", "spring_rate"),
    ("titration-curve", "L0", "All values are at 37 °C.", "Initial pH: 2.95", "ph_0_ml"),
    ("shelf-bracket", "L2", "With a safety factor of 2:", "Moment at the wall: 400 lb·in",
     "moment_at_wall"),
    ("heat-sink", "L2", "For margin, I size it up.", "Required plate area: 0.0600 m²",
     "plate_area"),
    ("hypothesis-test", "L0", "Differences: 0.8, 1.6, -0.3.", "x̄ = 1.175",
     "sample_mean"),
])
def test_other_wordings_of_an_assumption(task, level, assumption, line, name):
    never_wrong(task, level, line, name, assumption)


@pytest.mark.parametrize("task,level,line,name,after", [
    ("hypothesis-test", "L0", "A t-test.\n\np = 0.0061", "p_value",
     "## Summary\ndf = 9, critical value 2.262"),
    ("hypothesis-test", "L0", "A t-test.\n\np = 0.0061", "p_value",
     "In summary, compare with a critical value of 2.262."),
    ("conveyor-gear-ratio", "L2", "Drum speed: 50.9 rpm", "drum_speed",
     "In conclusion, use 12/68 and 12/72 teeth."),
    ("loan-amortization", "L0", "Monthly payment: $178.21", "monthly_payment",
     "In summary, keep the loan under 48 %."),
    ("loan-amortization", "L0", "Monthly payment: $178.21", "monthly_payment",
     "Update your budget by 2028."),
])
def test_an_unrelated_number_in_a_summary_changes_nothing(task, level, line, name, after):
    assert one(task, level, line, name) == "correct"
    assert one(task, level, f"{line}\n\n{after}", name) == "correct"


@pytest.mark.parametrize("task,level,line,name,after", [
    ("hypothesis-test", "L0", "A t-test.\n\np = 0.0061", "p_value",
     "In summary, p comes to 0.02."),
    ("hypothesis-test", "L0", "A t-test.\n\np = 0.0061", "p_value", "In summary: 0.02."),
    ("conveyor-gear-ratio", "L2", "Drum speed: 50.9 rpm", "drum_speed",
     "In conclusion, run the drum at 55 rpm."),
    ("loan-amortization", "L0", "Monthly payment: $178.21", "monthly_payment",
     "Updated answer: you pay 181 each month."),
    ("pipe-and-pump", "L2", "Total head: 7.84 m", "total_head",
     "Summary: allow for 9.2 m in all."),
    ("loan-amortization", "L0", "Monthly payment: $178.21", "monthly_payment",
     "In short, 181/month."),
    ("loan-amortization", "L0", "Monthly payment: $178.21", "monthly_payment",
     "In short, 181 pounds each time."),
    ("loan-amortization", "L0", "Monthly payment: $178.21", "monthly_payment",
     "Correction: the monthly payment is 181."),
    ("hypothesis-test", "L0", "A t-test.\n\np = 0.0061", "p_value",
     "Actually it's 0.02."),
    ("heat-sink", "L2", "Required total resistance: 4.25 °C/W", "total_resistance",
     "In short, stay under 3.9 °C per watt."),
])
def test_a_number_that_could_replace_a_value_puts_it_in_doubt(
        task, level, line, name, after):
    assert one(task, level, line, name) == "correct"
    assert one(task, level, f"{line}\n\n{after}", name) == "could_not_determine"


# --- review round 3 -----------------------------------------------------------

WRONG_LINES = {
    "heat-sink": ("L2", "Required plate area: 0.0600 m²", "plate_area"),
    "pipe-and-pump": ("L2", "Total head: 9.4 m", "total_head"),
    "cantilever-beam": ("L0", "Maximum bending moment: 9 kN·m", "max_bending_moment"),
    "conveyor-gear-ratio": ("L2", "Drum speed: 60.0 rpm", "drum_speed"),
    "shelf-bracket": ("L2", "Moment at the wall: 400 lb·in", "moment_at_wall"),
    "compression-spring": ("L2", "Required spring rate: 9.9 lbf/in", "spring_rate"),
    "loan-amortization": ("L0", "Monthly payment: $202.50", "monthly_payment"),
    "titration-curve": ("L0", "Initial pH: 3.40", "ph_0_ml"),
    "least-squares-fit": ("L0", "Slope: 1.50", "slope"),
    "hypothesis-test": ("L0", "Sample mean: 1.175", "sample_mean"),
    "projectile-drag": ("L2", "Range: 45.0 m", "range"),
}
SIZING = ("heat-sink", "pipe-and-pump", "cantilever-beam", "conveyor-gear-ratio",
          "shelf-bracket", "compression-spring")
STATED_ASSUMPTIONS = [
    *((task, sentence) for task in SIZING for sentence in (
        "I use a factor of safety 1.2.",
        "I include a factor of safety of 1.2.",
        "Factor of safety: 1.2",
        "SF = 1.2",
        "I add 10%, giving a safety margin.",
        "To be conservative I added 10%.",
        "To be conservative, I added 10%.",
        "Includes 10% for safety.",
        "With margin:",
        "For safety, use 10% more.",
        "For safety, add a factor of 1.2.",
    )),
    ("heat-sink", "I limit Tj to 110 °C."),
    ("heat-sink", "I limit $T_j$ to 110 °C."),
    ("heat-sink", "I keep the junction at 100 °C."),
    ("pipe-and-pump", "Fuse margin aside, I add 10% to the head as a margin above the current."),
    ("conveyor-gear-ratio", "The belt slips about 2%."),
    ("hypothesis-test", "These are differences from the target."),
    ("hypothesis-test", "The differences are 0.8, 1.6, -0.3."),
    ("hypothesis-test", "Compute each difference from the target:"),
    ("hypothesis-test", "49.7 looks like an outlier, so I remove it."),
    ("hypothesis-test", "I remove it."),
    ("least-squares-fit", "I remove it."),
    ("least-squares-fit", "The fit excludes (8, 30)."),
    ("loan-amortization", "With an origination fee (2%):"),
    ("loan-amortization", "An origination fee is added."),
    ("loan-amortization", "Insurance is added to each payment."),
    ("loan-amortization", "This excludes taxes but includes insurance of $30."),
    ("titration-curve", "I assume 37 °C."),
    ("titration-curve", "Correcting for activity:"),
    ("projectile-drag", "No wind, but a launch height of 1.5 m."),
]


@pytest.mark.parametrize("task,sentence", STATED_ASSUMPTIONS)
def test_a_naturally_worded_assumption_is_never_called_wrong(task, sentence):
    level, line, name = WRONG_LINES[task]
    never_wrong(task, level, line, name, sentence)


# --- fix round 4: text extraction never gives a final "wrong" -----------------

# Sentences that earlier rounds took as harmless or left as blind spots.
HARMLESS = [
    ("cantilever-beam", "No safety factor is applied."),
    ("hypothesis-test", "No outliers were removed."),
    ("loan-amortization", "There are no fees."),
    ("conveyor-gear-ratio", "Assume no slip."),
    ("heat-sink", "This leaves some margin."),
    ("heat-sink", "The design junction temperature is 125 °C."),
    ("projectile-drag", "The ball returns to its launch height."),
    ("hypothesis-test", "There are significant differences."),
    ("projectile-drag", "Initial height = 0,5 m."),
    ("projectile-drag", "Initial height = 0.5 m."),
]


@pytest.mark.parametrize("task,sentence", HARMLESS)
def test_a_harmless_sentence_leaves_a_mismatch_suspected(task, sentence):
    level, line, name = WRONG_LINES[task]
    never_wrong(task, level, line, name, sentence)


def test_a_reader_confirms_or_rejects_a_suspected_value():
    task, text = "loan-amortization", "Monthly payment: $202.50\nTotal interest: $1,692.65"
    confirmed = reviewed(task, "L0", text, review={"monthly_payment": "confirmed"})
    assert confirmed["quantities"]["monthly_payment"]["status"] == "wrong"
    assert confirmed["quantities"]["monthly_payment"]["review"] == "confirmed"
    assert confirmed["verdict"] == "wrong"
    rejected = reviewed(task, "L0", text, review={"monthly_payment": "rejected"})
    assert rejected["quantities"]["monthly_payment"]["status"] == "could_not_determine"
    assert rejected["verdict"] == "could_not_determine"
    supplied = reviewed(task, "L0", text,
                        quantities={"monthly_payment": {"value": 178.21, "unit": "$"}})
    assert supplied["verdict"] == "correct"
    right = reviewed(task, "L0", "Monthly payment: $178.21\nTotal interest: $1,692.65",
                     review={"monthly_payment": "confirmed"})
    assert right["quantities"]["monthly_payment"]["status"] == "correct"
    assert right["quantities"]["monthly_payment"]["review"] == "not_applied"


SPRING_TOO_WIDE = """Wire diameter: 0.040 in
Mean coil diameter: 0.250 in
Active coils: 13
Total coils: 15
"""


def test_a_criterion_failed_on_found_inputs_is_suspected():
    result = check("compression-spring", "L2", SPRING_TOO_WIDE)
    criterion = result["criteria"]["design_meets_requirements"]
    assert criterion["items"]["fits_the_hole"]["status"] == "suspected_fail"
    assert criterion["status"] == "suspected_fail"
    assert result["verdict"] == "suspected_wrong"
    judged = reviewed("compression-spring", "L2", SPRING_TOO_WIDE, criteria={
        "design_meets_requirements": {"fits_the_hole": "fail"}})
    assert judged["criteria"]["design_meets_requirements"]["items"][
        "fits_the_hole"]["status"] == "fail"
    assert judged["verdict"] == "wrong"


def test_a_keyed_list_mismatch_in_text_is_suspected():
    text = LSQ_L2.replace("| 7 | 14.1 | 13.839 | 0.261 |", "| 7 | 14.1 | 13.839 | 0.961 |")
    result = check("least-squares-fit", "L2", text)
    assert statuses(result, "residuals") == {"residuals": "suspected_wrong"}
    assert result["verdict"] == "suspected_wrong"


def test_a_level_in_words_is_not_taken_as_five_percent():
    text = ("We use the exact Wilcoxon signed-rank test at the one percent level.\n\n"
            "We reject the null hypothesis.")
    assert one("hypothesis-test", "L0", text, "decision") == "could_not_determine"


def test_the_reference_value_beside_a_replacing_assumption_is_not_correct():
    text = "Using the effective annual rate of 7%:\n\nMonthly payment: $178.21"
    assert one("loan-amortization", "L0", text, "monthly_payment") == "could_not_determine"


@pytest.mark.parametrize("extra,truncated", [
    ("Total paid: $10,000.00", True),                      # cut off
    ("Total paid: $10,000.00\nYou pay 60 × 178.21 = 10692.60 in all.", False),
    ("Total paid: $10,000.00\n\nTotal paid: $11,000.00", False),  # two values
])
def test_an_extra_mismatch_keeps_the_level_from_correct(extra, truncated):
    reference = REFERENCE["loan-amortization"]
    text = f"Monthly payment: $178.21\nTotal interest: $1,692.65\n{extra}"
    result = grade(reference, "L0", extract(reference, "L0", text, truncated=truncated))
    assert result["quantities"]["total_paid"]["status"] == "suspected_wrong"
    assert result["verdict"] == "suspected_wrong"
