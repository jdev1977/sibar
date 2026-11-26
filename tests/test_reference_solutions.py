"""The math and engineering reference answers (T2.3). No network.

Every number in checker/references/ is recomputed here from the givens, by
the plain-Python solvers in tests/reference_solvers.py, and every file is
checked against the format in checker/references/README.md. The worked
solutions are in docs/references/. A changed given, a mistyped value or a
tolerance that no longer does what its reason says fails a test.

These are study data, not designs.
"""

import inspect
import math
from functools import cache

import pytest

from reference_checks import (DOCUMENTS, LEVELS, REFERENCES, ROOT, TYPES,
                              ReferenceFileError, evaluate, levels_using,
                              load_reference, paired, reference_paths,
                              tolerance_for, validate, within)
from reference_solvers import (CONDITIONAL, SOLVERS, TITRATION_VOLUMES,
                               bracket_section_stress, conveyor_tooth_sets,
                               hazen_williams_variants,
                               loan_payment_dates, loan_schedule,
                               projectile_heun, student_t_two_sided_p,
                               student_t_two_sided_p_closed_form, titration_ph)
from runner.prompts import load_prompts

# A reference value is written to four or more significant figures, so it
# must agree with the recomputed value to half a unit in the fourth.
CLOSE = 5e-4


@cache
def prompts():
    tasks = load_prompts([ROOT / "prompts" / name for name in TYPES])
    return {(task.project_type, task.task_id): task for task in tasks}


@cache
def references():
    found = {}
    for path in reference_paths():
        reference = load_reference(path)
        found[(path.parent.name, path.stem)] = (path, reference)
    return found


@cache
def solved(key):
    return SOLVERS[key]()


KEYS = sorted(SOLVERS)


def quantities(key):
    return references()[key][1]["quantities"]


def all_quantities():
    return [(key, name) for key in KEYS for name in quantities(key)]


def close(written, computed):
    return math.isclose(written, computed, rel_tol=CLOSE, abs_tol=1e-9)


# --- the set of files ---------------------------------------------------------


def test_every_math_and_engineering_task_has_one_reference_file():
    assert set(references()) == set(prompts()) == set(SOLVERS)
    assert len(references()) == 12


@pytest.mark.parametrize("key", KEYS)
def test_every_task_has_a_worked_solution_document(key):
    path, reference = references()[key]
    document = DOCUMENTS / key[0] / f"{key[1]}.md"
    text = document.read_text(encoding="utf-8")
    assert f"checker/references/{key[0]}/{key[1]}.yaml" in text
    for heading in ("## Assumptions", "## Checks"):
        assert heading in text, heading
    if key[0] == "engineering":
        assert "Study data, not a design" in text


@pytest.mark.parametrize("key", KEYS)
def test_file_follows_the_format(key):
    path, reference = references()[key]
    validate(reference, path)


@pytest.mark.parametrize("key", KEYS)
def test_file_names_the_prompt_version_it_was_solved_from(key):
    assert references()[key][1]["prompt_set_version"] == prompts()[key].prompt_set_version


@pytest.mark.parametrize("key", KEYS)
def test_givens_are_in_the_prompts_word_for_word(key):
    reference = references()[key][1]
    texts = prompts()[key].texts
    for given in reference["givens"]:
        for cell, text in texts.items():
            assert given["text"] in text, (given["id"], cell)
    for given in reference.get("l2_givens", []):
        for wording in ("A", "B"):
            assert given["text"] in texts[("L2", wording)], (given["id"], wording)


def test_levels_without_a_checkable_answer_are_the_expected_ones():
    """What is checkable at which level, as the prompt READMEs set it."""
    not_checkable = {(key, level) for key in KEYS for level in LEVELS
                     if not references()[key][1]["levels"][level]["checkable"]}
    assert not_checkable == {
        (("math", "projectile-drag"), "L0"), (("math", "projectile-drag"), "L1"),
        (("math", "entropy-explanation"), "L0"), (("math", "entropy-explanation"), "L1"),
        (("math", "entropy-explanation"), "L2"),
        (("engineering", "shelf-bracket"), "L0"), (("engineering", "shelf-bracket"), "L1"),
        (("engineering", "compression-spring"), "L0"),
        (("engineering", "compression-spring"), "L1"),
    }


# --- every number, recomputed -------------------------------------------------


def compare(written, computed, where):
    if isinstance(written, list):
        assert len(written) == len(computed), where
        for a, b in zip(written, computed):
            compare(a, b, where)
    elif isinstance(written, (str, bool)) or type(computed) is int:
        # Text, and anything the solver finds as a whole number, is exact.
        assert written == computed and type(written) is type(computed), where
    else:
        assert close(written, computed), (where, written, computed)


@pytest.mark.parametrize("key,name", all_quantities())
def test_reference_value_is_what_the_solver_computes(key, name):
    quantity = quantities(key)[name]
    answers = solved(key)
    if quantity["kind"] == "fixed":
        assert name in answers, f"{name}: no solver value"
    if name in answers:
        assert "value" in quantity
        compare(quantity["value"], answers[name], name)
    for alternative in quantity.get("alternatives", ()):
        if "value" not in alternative or quantity.get("type") == "choice":
            continue
        label = f"{name}@{alternative['id']}"
        if isinstance(alternative["value"], list):
            compare(alternative["value"], [-r for r in answers[name]], label)
        elif label in answers:
            compare(alternative["value"], answers[label], label)
        else:
            assert label in EXTRA_ALTERNATIVES, f"{label}: no solver value"
            compare(alternative["value"], EXTRA_ALTERNATIVES[label](answers), label)


# Alternatives that follow from other solved values by one line of arithmetic.
EXTRA_ALTERNATIVES = {
    "spring_constant_ci95_low@symmetric_interval":
        lambda a: a["spring_constant"] - a["t_critical_95"] * a["spring_constant_se"],
    "spring_constant_ci95_high@symmetric_interval":
        lambda a: a["spring_constant"] + a["t_critical_95"] * a["spring_constant_se"],
    "hydraulic_power@with_velocity_head":
        lambda a: a["hydraulic_power"] * a["total_head@with_velocity_head"] / a["total_head"],
    "electrical_power@with_velocity_head":
        lambda a: a["electrical_power"] * a["total_head@with_velocity_head"] / a["total_head"],
    "battery_current@with_velocity_head":
        lambda a: a["battery_current"] * a["total_head@with_velocity_head"] / a["total_head"],
}


def computed_holders():
    """Every conditional quantity, and every alternative with a formula."""
    found = []
    for key in KEYS:
        for name, quantity in quantities(key).items():
            if quantity["kind"] == "conditional":
                found.append((key, name))
            for alternative in quantity.get("alternatives", ()):
                if "formula" in alternative:
                    found.append((key, f"{name}@{alternative['id']}"))
    return found


def holder(key, label):
    name, _, alternative_id = label.partition("@")
    quantity = quantities(key)[name]
    if not alternative_id:
        return quantity
    return next(a for a in quantity["alternatives"] if a["id"] == alternative_id)


def test_every_conditional_answer_has_an_independent_solver():
    assert {(key[0], key[1], label) for key, label in computed_holders()} == set(CONDITIONAL)


@pytest.mark.parametrize("key,label", computed_holders())
def test_conditional_formula_examples_and_solver_agree(key, label):
    """Three things written separately must give one number: the formula
    text in the file, its worked examples, and the solver function."""
    entry = holder(key, label)
    function = CONDITIONAL[(key[0], key[1], label)]
    assert set(inspect.signature(function).parameters) == set(entry["inputs"])
    for example in entry["examples"]:
        computed = function(**example["inputs"])
        assert close(example["value"], computed), (label, example, computed)
        if "formula" in entry:
            assert close(evaluate(entry["formula"], example["inputs"]), computed), label
    if "value" in entry and "formula" in entry:
        standard = [e for e in entry["examples"] if close(e["value"], entry["value"])]
        assert standard, f"{label}: no example gives the standard value"


# --- tolerances do what their reasons say -------------------------------------


def numeric_examples(group):
    return [(key, name, entry["value"])
            for key in KEYS for name, quantity in quantities(key).items()
            for entry in quantity.get(group, ())]


@pytest.mark.parametrize("key,name,value", numeric_examples("accepted_examples"))
def test_values_meant_to_pass_are_inside_the_tolerance(key, name, value):
    reference = references()[key][1]
    quantity = reference["quantities"][name]
    for level in levels_using(reference, name):
        assert within(tolerance_for(quantity, level), quantity["value"], value), level


@pytest.mark.parametrize("key,name,value", numeric_examples("not_accepted"))
def test_known_wrong_values_are_outside_the_tolerance(key, name, value):
    """Against the reference value at every level. An alternative needs its
    stated condition, so it is not consulted here."""
    reference = references()[key][1]
    quantity = reference["quantities"][name]
    for level in levels_using(reference, name):
        assert not within(tolerance_for(quantity, level), quantity["value"], value), level


def passes(key, name, value, level="L2"):
    quantity = quantities(key)[name]
    return within(tolerance_for(quantity, level), quantity["value"], value)


def test_loan_tolerances_cover_both_interest_conventions():
    key = ("math", "loan-amortization")
    rounded = loan_schedule(round_interest=True)
    exact = loan_schedule(round_interest=False)
    assert passes(key, "final_payment", float(exact[-1][1]))
    assert passes(key, "total_interest_l2", float(sum(r[1] for r in exact)) - 9000)
    for month in (1, 12, 24, 36, 48, 59, 60):
        assert passes(key, f"balance_after_{month}", float(exact[month - 1][4]))
        assert passes(key, f"balance_after_{month}", float(rounded[month - 1][4]))
    # L0 and L1 have no rounding rule: three ways of totalling the interest.
    for total in (60 * 178.21 - 9000, solved(key)["total_interest"],
                  solved(key)["total_interest_l2"]):
        assert passes(key, "total_interest", total, "L0")
    assert not passes(key, "total_interest_l2", 60 * 178.21 - 9000)
    assert not passes(key, "final_payment", 178.21)


def test_loan_schedule_dates_and_closing_balance():
    dates = loan_payment_dates()
    answers = solved(("math", "loan-amortization"))
    assert len(dates) == answers["schedule_rows"] == 60
    assert dates[0] == answers["first_payment_date"] == "2027-04-01"
    assert dates[-1] == answers["final_payment_date"] == "2032-03-01"
    assert len(set(dates)) == 60 and dates == sorted(dates)
    assert loan_schedule(round_interest=True)[-1][4] == 0


def test_projectile_tolerances_cover_the_readings_of_the_method():
    key = ("math", "projectile-drag")
    answers = solved(key)
    for name, variants in {
        "range": ("_range_variant", "_range_converged"),
        "flight_time": ("_flight_variant", "_flight_converged"),
        "max_height": ("_height_variant", "_height_interpolated", "_height_converged"),
        "step1_x": ("_step1_x_variant",),
        "step1_y": ("_step1_y_variant",),
    }.items():
        for variant in variants:
            assert passes(key, name, answers[variant]), (name, variant)
    # The table ends with the first row below ground.
    rows = projectile_heun()
    assert rows[-2][2] > 0 > rows[-1][2] and len(rows) - 1 == answers["landing_step_count"]
    assert max(rows, key=lambda row: row[2])[0] == pytest.approx(1.1)


def test_titration_tolerances_cover_constants_and_shortcuts():
    key = ("math", "titration-curve")
    answers = solved(key)
    for level in ("L0", "L1"):
        assert passes(key, "ph_0_ml", answers["_initial_ph_ka_175"], level)
        assert passes(key, "ph_12_5_ml", answers["_half_ph_ka_174"], level)
        assert passes(key, "ph_25_ml", answers["_equivalence_ph_ka_174"], level)
    assert passes(key, "ph_0_ml", answers["_initial_ph_shortcut"])
    assert passes(key, "ph_12_5_ml", answers["pka"])
    assert passes(key, "ph_25_ml", answers["_equivalence_ph_shortcut"])
    # The curve rises all the way, and jumps at the equivalence point.
    table = [answers[name] for name in ("ph_0_ml", "ph_5_ml", "ph_10_ml", "ph_12_5_ml",
                                        "ph_20_ml", "ph_24_ml", "ph_25_ml", "ph_26_ml",
                                        "ph_30_ml", "ph_40_ml", "ph_50_ml")]
    assert table == sorted(table)
    assert answers["ph_26_ml"] - answers["ph_24_ml"] > 5


def test_hypothesis_test_decisions_follow_from_the_p_values():
    key = ("math", "hypothesis-test")
    answers = solved(key)

    def decide(p, level):
        return "reject" if p < level else "do_not_reject"

    decision = quantities(key)["decision"]
    alternatives = {a["id"]: a["value"] for a in decision["alternatives"]}
    assert decision["value"] == decide(answers["p_value"], 0.05)
    assert alternatives["t_test_at_1_percent"] == decide(answers["p_value"], 0.01)
    for method in ("wilcoxon_exact", "wilcoxon_normal", "wilcoxon_normal_corrected",
                   "sign_flip_permutation"):
        p = answers[f"p_value@{method}"]
        assert alternatives["wilcoxon_at_5_percent"] == decide(p, 0.05)
        assert alternatives["wilcoxon_at_1_percent"] == decide(p, 0.01)
    assert alternatives["sign_test"] == decide(answers["p_value@sign_test"], 0.05)
    assert quantities(key)["decision_l2"]["value"] == decide(answers["p_value_exact"], 0.01)
    assert str(answers["_p_value_exact_fraction"]) == "1/64"
    assert answers["_p_at_critical"] < 0.01 < answers["p_value_exact"]


def test_least_squares_exact_forms():
    answers = solved(("math", "least-squares-fit"))
    assert str(answers["_slope_fraction"]) == "109/56"
    assert str(answers["_intercept_fraction"]) == "3/14"
    assert sum(answers["residuals"]) == pytest.approx(0, abs=1e-12)


def test_hazen_williams_tolerance_covers_the_printed_forms():
    key = ("engineering", "pipe-and-pump")
    for name, head in hazen_williams_variants(43.0, 140).items():
        assert passes(key, "friction_loss", head), name
        assert passes(key, "total_head", 6.0 + head), name
    answers = solved(key)
    assert passes(key, "hydraulic_power", answers["_hydraulic_power_density_1000"])
    friction = quantities(key)["friction_head_straight_pipe"]
    assert friction["range"]["low"] == pytest.approx(answers["friction_head_low"] * 0.94, abs=0.005)
    assert friction["range"]["high"] == pytest.approx(answers["friction_head_high"] * 1.06, abs=0.005)
    reynolds = quantities(key)["reynolds_number"]
    examples = {e["note"][:5]: e["value"] for e in reynolds["examples"]}
    assert reynolds["range"]["low"] == pytest.approx(examples["10 °C"] * 0.95, rel=0.002)
    assert reynolds["range"]["high"] == pytest.approx(examples["25 °C"] * 1.05, rel=0.002)


def test_cantilever_section_is_the_smallest_that_meets_both_limits():
    answers = solved(("engineering", "cantilever-beam"))

    def checks(width, depth=None):
        depth = 2 * width if depth is None else depth
        stress = 6e6 / (width * depth ** 2 / 6)
        deflection = 4000 * 1500 ** 3 / (3 * 68900 * width * depth ** 3 / 12)
        return stress <= 92 and deflection <= 15

    assert checks(answers["width"]) and not checks(answers["width"] - 1)
    # With the depth held at exactly twice the width there is one smallest
    # section. Let the ratio go and there is none: each of these meets both
    # limits with less material than the one before, so 50 by 102 is an
    # alternative only when the answer states the departure.
    assert checks(50, 102) and checks(51, 101) and checks(49, 103) and checks(48, 104)
    assert 48 * 104 < 49 * 103 < 50 * 102 < 51 * 101 < 51 * 102
    assert not checks(50, 100) and not checks(50, 101)
    assert answers["width"] == math.ceil(answers["min_width_for_deflection"])
    width = quantities(("engineering", "cantilever-beam"))["width"]
    assert within(width["tolerance"], width["value"], 0.051 / 0.001)     # given in meters
    assert not within(width["tolerance"], width["value"], 50)
    assert answers["min_width_for_stress"] < answers["min_width_for_deflection"]


def test_t_distribution_p_value_agrees_with_its_closed_form():
    """The p-values come from numerical integration; for odd degrees of
    freedom a closed form exists, and known table values pin both."""
    for t, df in ((3.8727329, 7), (2.5705818, 5), (1.0, 3), (4.5, 9)):
        assert student_t_two_sided_p(t, df) == pytest.approx(
            student_t_two_sided_p_closed_form(t, df), abs=1e-9)
    assert student_t_two_sided_p(2.365, 7) == pytest.approx(0.05, abs=1e-4)
    assert student_t_two_sided_p(3.499, 7) == pytest.approx(0.01, abs=1e-4)
    assert student_t_two_sided_p(2.228, 10) == pytest.approx(0.05, abs=1e-4)


# --- the long tables in the documents -----------------------------------------


def table_rows(key, first_cell):
    """Rows of the Markdown table whose header starts with ``first_cell``,
    as lists of cell texts."""
    lines = (DOCUMENTS / key[0] / f"{key[1]}.md").read_text(encoding="utf-8").splitlines()
    cells = [[cell.strip() for cell in line.strip().strip("|").split("|")]
             for line in lines]
    start = next(j for j, row in enumerate(cells) if row[0] == first_cell)
    rows = []
    for row in cells[start + 2:]:
        if len(row) != len(cells[start]):
            break
        rows.append(row)
    return rows


def number(text):
    return float(text.replace("−", "-").replace(" ", ""))


def test_loan_schedule_in_the_document_is_the_solver_schedule():
    rows = table_rows(("math", "loan-amortization"), "No.")
    schedule = loan_schedule(round_interest=True)
    dates = loan_payment_dates()
    months = ("January February March April May June July August September "
              "October November December").split()
    assert len(rows) == 61 and rows[-1][0] == "Total"
    for row, (month, paid, interest, principal, balance), date in zip(rows, schedule, dates):
        year, month_number, _ = date.split("-")
        assert row[0] == str(month)
        assert row[1] == f"{months[int(month_number) - 1]} 1, {year}"
        assert [number(cell) for cell in row[2:]] == [float(paid), float(interest),
                                                      float(principal), float(balance)]
    totals = [number(cell) for cell in rows[-1][2:5]]
    assert totals == [10692.66, 1692.66, 9000.00]


def test_projectile_table_in_the_document_is_the_solver_table():
    rows = table_rows(("math", "projectile-drag"), "t (s)")
    computed = projectile_heun()
    assert len(rows) == len(computed) == 24
    for row, state in zip(rows, computed):
        assert [number(cell) for cell in row] == pytest.approx(list(state), abs=6e-5)


def test_titration_table_in_the_document_is_the_solver_table():
    rows = table_rows(("math", "titration-curve"), "V (mL)")
    assert [number(row[0]) for row in rows] == list(TITRATION_VOLUMES)
    for row in rows:
        ph = titration_ph(number(row[0]))
        assert number(row[4]) == pytest.approx(ph, abs=6e-5)
        assert number(row[5]) == pytest.approx(ph, abs=0.0051)
        mantissa, exponent = row[3].split(" × 10^")
        assert float(mantissa) * 10 ** int(exponent) == pytest.approx(10 ** -ph, rel=2e-3)


def test_conveyor_table_in_the_document_lists_the_passing_sets():
    rows = table_rows(("engineering", "conveyor-gear-ratio"), "Motor pulley")
    listed = {tuple(int(cell) for cell in row[:4]) for row in rows}
    assert listed == set(conveyor_tooth_sets()) and len(rows) == 17
    for row in rows:
        z1, z2, z3, z4 = (int(cell) for cell in row[:4])
        ratio = (z2 / z1) * (z4 / z3)
        speed = math.pi * 0.150 * 1725 / ratio / 60
        assert number(row[4]) == pytest.approx(ratio, abs=6e-4)
        assert number(row[5]) == pytest.approx(speed, abs=6e-5)
        assert number(row[6].rstrip("%")) == pytest.approx((speed / 0.4 - 1) * 100, abs=6e-3)


# --- criteria -----------------------------------------------------------------


def checks_of(key, criterion):
    items = references()[key][1]["criteria"][criterion]["pass_when"]
    return {item["id"]: item for item in items if "check" in item}


def all_checks():
    return [(key, name, item["id"])
            for key in KEYS
            for name, criterion in references()[key][1].get("criteria", {}).items()
            for item in criterion["pass_when"] if "check" in item]


@pytest.mark.parametrize("key,criterion,item", all_checks())
def test_every_check_can_be_evaluated(key, criterion, item):
    entry = checks_of(key, criterion)[item]
    result = evaluate(entry["check"], dict.fromkeys(entry["inputs"], 1.0), allow_logic=True)
    assert type(result) is bool


def test_conveyor_criteria_pass_exactly_the_listed_tooth_sets():
    key = ("engineering", "conveyor-gear-ratio")
    checks = checks_of(key, "tooth_counts")
    criterion = references()[key][1]["criteria"]["tooth_counts"]
    assert criterion["all_passing"]["inputs"] == ["z1", "z2", "z3", "z4"]
    listed = {tuple(teeth) for teeth in criterion["all_passing"]["sets"]}
    assert listed == set(conveyor_tooth_sets()) and len(listed) == 17

    def passes_criteria(teeth):
        inputs = dict(zip(("z1", "z2", "z3", "z4"), teeth))
        return all(evaluate(item["check"], inputs, allow_logic=True)
                   for item in checks.values())

    assert all(passes_criteria(teeth) for teeth in listed)
    for near_miss in ((12, 67, 12, 71), (13, 72, 13, 72), (12, 73, 12, 67),
                      (11, 66, 12, 68), (14, 72, 12, 72), (15, 72, 15, 72)):
        assert not passes_criteria(near_miss), near_miss
    # What the criterion's text says about the stages and the small wheels.
    answers = solved(key)
    assert round(answers["stage_ratio_low"], 2) == 5.54 and answers["stage_ratio_high"] == 6
    assert {teeth[0] for teeth in listed} | {teeth[2] for teeth in listed} == {12, 13}


def test_spring_reference_design_meets_its_own_criteria():
    key = ("engineering", "compression-spring")
    answers = solved(key)
    checks = checks_of(key, "design_meets_requirements")
    design = dict(d=answers["reference_wire"], D=answers["reference_mean_diameter"],
                  Na=answers["reference_active_coils"])
    assert evaluate(checks["fits_the_hole"]["check"],
                    {k: design[k] for k in ("d", "D")}, allow_logic=True)
    assert evaluate(checks["rate_is_met"]["check"], design, allow_logic=True)
    assert evaluate(checks["reaches_working_length"]["check"],
                    {"solid_length_in": answers["reference_solid_length"]}, allow_logic=True)
    assert evaluate(checks["stress_within_allowable"]["check"],
                    {"working_stress_psi": answers["reference_working_stress"]},
                    allow_logic=True)
    assert evaluate(checks["clearance_before_solid"]["check"],
                    {"solid_length_in": answers["reference_solid_length"]}, allow_logic=True)
    # A wire too thick to reach the working length, and a coil too wide.
    assert not evaluate(checks["reaches_working_length"]["check"],
                        {"solid_length_in": 0.032 * 18}, allow_logic=True)
    assert not evaluate(checks["fits_the_hole"]["check"], {"d": 0.030, "D": 0.245},
                        allow_logic=True)


def test_spring_rate_criterion_in_the_disputed_band():
    """Within 5% passes. From 5% to 10% passes only when the coil count is
    the exact count rounded by at most half a coil. Beyond 10% fails."""
    key = ("engineering", "compression-spring")
    check = checks_of(key, "design_meets_requirements")["rate_is_met"]["check"]
    exact = CONDITIONAL[("engineering", "compression-spring", "active_coils_for_exact_rate")]
    rate = CONDITIONAL[("engineering", "compression-spring", "rate_from_geometry")]

    def verdict(d, D, Na):
        return evaluate(check, {"d": d, "D": D, "Na": Na}, allow_logic=True)

    def off(d, D, Na):
        return rate(d=d, D=D, Na=Na) / 6.0 - 1

    # The reference design, and its coil count rounded to a half coil.
    assert verdict(0.030, 0.235, 13) and verdict(0.030, 0.235, 13.5)
    assert abs(off(0.030, 0.235, 13.5)) < 0.05
    # 7.1% low with 14 coils where 13.0 are needed: a full coil out. It
    # passed the old 10% rule and fails now.
    assert 0.05 < -off(0.030, 0.235, 14) < 0.10
    assert abs(14 - exact(d=0.030, D=0.235)) > 0.5
    assert not verdict(0.030, 0.235, 14)
    # 7.1% low with 5 coils where 4.64 are needed: the count was rounded.
    assert 0.05 < -off(0.024, 0.246, 5) < 0.10
    assert abs(5 - exact(d=0.024, D=0.246)) <= 0.5
    assert verdict(0.024, 0.246, 5)
    # 6.7% high with 3 coils where 3.2 are needed: rounded, passes.
    assert 0.05 < off(0.022, 0.248, 3) < 0.10 and verdict(0.022, 0.248, 3)
    # 14% low with 2 coils where 1.72 are needed: within half a coil, but
    # the spring gives 1.03 lbf, not 1.2. The 10% cap fails it.
    assert abs(2 - exact(d=0.019, D=0.251)) <= 0.5
    assert -off(0.019, 0.251, 2) > 0.10
    assert not verdict(0.019, 0.251, 2)
    # Far off either way.
    assert not verdict(0.030, 0.235, 10) and not verdict(0.030, 0.235, 16)


def test_spring_life_criterion_follows_the_stated_limit():
    """The verdict must agree with the answer's own comparison, both ways,
    and the plausibility of its limit is recorded apart from the pass."""
    key = ("engineering", "compression-spring")
    items = checks_of(key, "life")
    follows, plausible = items["verdict_follows"], items["limit_is_plausible"]
    assert plausible.get("record_only") is True and "record_only" not in follows

    def verdict(stress, limit, lasts):
        return evaluate(follows["check"], {"compared_stress_psi": stress,
                                           "stated_limit_psi": limit, "lasts": lasts},
                        allow_logic=True)

    def in_band(limit):
        return evaluate(plausible["check"], {"stated_limit_psi": limit}, allow_logic=True)

    default = 0.36 * 280000
    stress = solved(key)["reference_working_stress"]
    # The reference design against the default limit: it lasts, and saying
    # it does not is wrong.
    assert verdict(stress, default, 1) and not verdict(stress, default, 0)
    # A design over its stated limit: "lasts" is wrong and "does not last"
    # is right. The old check passed either answer here.
    assert not verdict(110000, default, 1) and verdict(110000, default, 0)
    # The disputed band, 100.8 to 126 ksi: a design at 115 ksi meets the
    # brief's 45% but not the 36% default; with a stated limit of 42%
    # (shot-peened wire) it lasts.
    assert verdict(115000, 0.42 * 280000, 1) and not verdict(115000, default, 1)
    assert verdict(default, default, 1)
    # Plausibility of the limit: 25% to 42% of the tensile strength.
    assert in_band(default) and in_band(70000) and in_band(0.42 * 280000)
    assert not in_band(0.45 * 280000) and not in_band(35000) and not in_band(60000)
    # An implausible limit still gets a consistent verdict graded.
    assert verdict(120000, 126000, 1) and not in_band(126000)


def test_record_only_items_do_not_decide_a_pass():
    """Record-only items exist only where the brief sets no requirement."""
    found = {(key[1], name, item["id"])
             for key in KEYS
             for name, criterion in references()[key][1].get("criteria", {}).items()
             for item in criterion["pass_when"] if item.get("record_only")}
    assert found == {
        ("compression-spring", "design_meets_requirements", "clearance_before_solid"),
        ("compression-spring", "life", "limit_is_plausible"),
    }


def test_heat_sink_and_bracket_criteria():
    sink = checks_of(("engineering", "heat-sink"), "chosen_sink_is_adequate")
    check = sink["junction_within_target"]["check"]
    good = {"junction_target_c": 125, "interface_resistance": 0.5, "sink_resistance": 2.5}
    assert evaluate(check, good, allow_logic=True)
    assert not evaluate(check, dict(good, sink_resistance=3.0), allow_logic=True)
    bracket = ("engineering", "shelf-bracket")
    outline = checks_of(bracket, "outline")
    assert evaluate(outline["fits_under_shelf"]["check"], {"radius_in": 10}, allow_logic=True)
    assert not evaluate(outline["fits_under_shelf"]["check"], {"radius_in": 10.5},
                        allow_logic=True)
    assert evaluate(outline["two_holes_over_the_strip"]["check"], {"e": 0.75}, allow_logic=True)
    stress = checks_of(bracket, "stress_within_working_stress")["below_working_stress"]
    answers = solved(bracket)
    assert evaluate(stress["check"], {"stress_psi": answers["reference_stress"]},
                    allow_logic=True)


# --- answers with more than one complete form ---------------------------------


def test_one_of_groups():
    """Where a request can be met in more than one form, the level lists
    the forms, and every quantity in them is still defined and graded."""
    found = {(key[1], level): references()[key][1]["levels"][level]["one_of"]
             for key in KEYS for level in LEVELS
             if "one_of" in references()[key][1]["levels"][level]}
    assert found == {
        ("shelf-bracket", "L2"): [["screw_downward_force", "screw_sideways_force"],
                                  ["screw_resultant_force"]],
        ("hypothesis-test", "L0"): [["p_value"], ["ci95_low", "ci95_high"],
                                    ["t_statistic", "t_critical_95"]],
        ("hypothesis-test", "L1"): [["p_value"], ["ci95_low", "ci95_high"],
                                    ["t_statistic", "t_critical_95"]],
    }
    # The three hypothesis-test routes give one decision at the 5% level.
    answers = solved(("math", "hypothesis-test"))
    by_p = answers["p_value"] < 0.05
    by_interval = not answers["ci95_low"] <= 50 <= answers["ci95_high"]
    by_statistic = answers["t_statistic"] > answers["t_critical_95"]
    assert by_p and by_interval and by_statistic


def test_bracket_screw_total_is_available_for_every_reading():
    """An answer that gives one total force per screw can be graded in the
    screw-group reading and in each bearing reading."""
    key = ("engineering", "shelf-bracket")
    sideways = quantities(key)["screw_sideways_force"]
    total = quantities(key)["screw_resultant_force"]
    assert ({a["id"] for a in sideways["alternatives"]}
            == {a["id"] for a in total["alternatives"]}
            == {"bearing_upper_screw", "bearing_upper_screw_wall_moment",
                "bearing_both_screws", "bearing_both_screws_wall_moment"})
    layout = {"e": 0.75, "a": 2, "s": 6, "p": 10}

    def value(entry):
        return evaluate(entry["formula"], {k: layout[k] for k in entry["inputs"]})

    for part, whole in zip([sideways] + sideways["alternatives"],
                           [total] + total["alternatives"]):
        assert value(whole) == pytest.approx(math.hypot(value(part), 20.0))
    # Both screws sharing: the two sideways forces balance the moment used.
    both = holder(key, "screw_sideways_force@bearing_both_screws")
    lower = quantities(key)["lower_screw_sideways_force_bearing"]
    assert value(both) * 8 + value(lower) * 2 == pytest.approx(40 * 4.25)
    both_wall = holder(key, "screw_sideways_force@bearing_both_screws_wall_moment")
    lower_wall = holder(key, "lower_screw_sideways_force_bearing@wall_moment")
    assert value(both_wall) * 8 + value(lower_wall) * 2 == pytest.approx(200)


def test_bracket_stress_is_graded_at_the_wall():
    key = ("engineering", "shelf-bracket")
    level = references()[key][1]["levels"]["L2"]
    assert "quarter_disc_stress_at_wall" in level["quantities"]
    assert "plywood_bending_stress" in level["if_reported"]
    # Naming a lightly stressed section does not answer the question: for
    # the reference bracket the mid-depth section carries a third of the
    # wall stress.
    at_wall = bracket_section_stress(10.0)[2]
    midway = bracket_section_stress(10.0, 5.0)[2]
    wall = quantities(key)["quarter_disc_stress_at_wall"]
    assert evaluate(wall["formula"], {"radius_in": 10}) == pytest.approx(at_wall)
    assert not within(wall["tolerance"], at_wall, midway)


def test_list_quantities_are_paired_by_key_not_by_position():
    lists = [(("math", "hypothesis-test"), "differences"),
             (("math", "hypothesis-test"), "ranks"),
             (("math", "least-squares-fit"), "residuals")]
    assert sorted(lists) == sorted((key, name) for key, name in all_quantities()
                                   if quantities(key)[name].get("type") == "list")
    for key, name in lists:
        quantity = quantities(key)[name]
        keys = quantity["keyed_by"]["values"]
        stated = dict(zip(keys, quantity["value"]))
        # The same answer listed in another order (here sorted by key, as
        # a response that ranks its table would) pairs up the same way.
        shuffled = {k: stated[k] for k in sorted(stated, reverse=True)}
        assert paired(quantity, shuffled) == list(zip(quantity["value"], quantity["value"]))
        assert all(within(quantity["tolerance"], r, s) for r, s in paired(quantity, shuffled))
        # A key missing or foreign cannot be paired.
        assert paired(quantity, {k: stated[k] for k in keys[1:]}) is None
    # Measurements and x values are distinct, so the pairing is unambiguous.
    ranks = quantities(("math", "hypothesis-test"))["ranks"]
    assert ranks["keyed_by"]["values"] == [float(v) for v in
                                           "50.8 51.6 49.7 52.3 51.1 50.4 52.0 51.5".split()]
    by_value = dict(zip(ranks["keyed_by"]["values"], ranks["value"]))
    assert by_value[49.7] == 1 and by_value[52.3] == 8


def test_partial_levels_are_the_expected_ones():
    partial = {(key[1], level) for key in KEYS for level in LEVELS
               if references()[key][1]["levels"][level].get("partial")}
    assert partial == {
        ("cantilever-beam", "L0"), ("cantilever-beam", "L1"),
        ("heat-sink", "L0"), ("heat-sink", "L1"),
        ("pipe-and-pump", "L0"), ("pipe-and-pump", "L1"),
        ("shelf-bracket", "L2"), ("compression-spring", "L2"),
    }


def test_loan_amounts_use_one_unit():
    units = {q["unit"] for name, q in quantities(("math", "loan-amortization")).items()
             if name not in ("payment_count", "schedule_rows", "monthly_rate_percent",
                             "first_payment_date", "final_payment_date")}
    assert units == {"currency"}


def test_heat_sink_side_passes_in_any_listed_unit():
    side = quantities(("engineering", "heat-sink"))["square_side"]
    for unit in [{"unit": "mm", "factor": 1}] + side["other_units"]:
        stated = round(135 * unit["factor"], 6)          # 135 mm, 0.135 m, 13.5 cm
        assert within(side["tolerance"], side["value"], stated / unit["factor"]), unit
    assert not within(side["tolerance"], side["value"], 130)
    assert not within(side["tolerance"], side["value"], 135.2)


# --- the reader itself --------------------------------------------------------


def test_formula_language_refuses_anything_else():
    assert evaluate("2 * (x + 1) ** 2 / sqrt(4)", {"x": 2}) == 9
    assert evaluate("0 < x <= 3 and not x == 2", {"x": 3}, allow_logic=True) is True
    for bad in ("__import__('os')", "x.real", "x if x else 1", "[x]", "x < 2",
                "open('f')", "lambda: 1", "y + 1", "'a'"):
        with pytest.raises(ReferenceFileError):
            evaluate(bad, {"x": 1})


def test_validator_rejects_broken_files():
    path, good = references()[("engineering", "heat-sink")]
    validate(good, path)

    def broken(change):
        copy = load_reference(path)
        change(copy)
        with pytest.raises(ReferenceFileError):
            validate(copy, path)

    broken(lambda r: r.pop("study_data_note"))
    broken(lambda r: r["levels"].pop("L1"))
    broken(lambda r: r["levels"]["L0"]["quantities"].append("no_such_quantity"))
    broken(lambda r: r["quantities"]["total_resistance"].pop("tolerance"))
    broken(lambda r: r["quantities"]["total_resistance"]["tolerance"].pop("why"))
    broken(lambda r: r["quantities"]["total_resistance"].update(kind="guess"))
    broken(lambda r: r["quantities"]["heat_sink_resistance_limit"].update(
        formula="(junction_target_c - 40) / 20 - 1.0"))
    broken(lambda r: r["quantities"].update(orphan=dict(
        description="x", kind="fixed", unit="1", value=1,
        tolerance={"abs": 0, "why": "x"})))
    broken(lambda r: r["levels"]["L2"].update(checkable=False))
    broken(lambda r: r.update(task_id="other"))
    broken(lambda r: r["levels"]["L2"].update(one_of=[["plate_resistance"]]))
    broken(lambda r: r["levels"]["L2"].update(one_of=[["square_side"], ["no_such"]]))
    broken(lambda r: r["levels"]["L0"].update(partial=False))
    broken(lambda r: r["criteria"]["chosen_sink_is_adequate"]["pass_when"].append(
        {"id": "x", "text": "x", "record_only": True}))
    path, good = references()[("math", "hypothesis-test")]

    def broken_list(change):
        copy = load_reference(path)
        change(copy)
        with pytest.raises(ReferenceFileError):
            validate(copy, path)

    broken_list(lambda r: r["quantities"]["ranks"].pop("keyed_by"))
    broken_list(lambda r: r["quantities"]["ranks"]["keyed_by"]["values"].pop())
    broken_list(lambda r: r["quantities"]["w_plus"].update(
        keyed_by={"description": "x", "values": [1]}))


def test_tolerance_rule():
    assert within({"abs": 0.005}, 178.21, 178.2108)
    assert not within({"abs": 0.005}, 178.21, 178.22)
    assert within({"rel": 0.01}, 100.0, 101.0) and not within({"rel": 0.01}, 100.0, 101.1)
    assert within({"abs": 0.5, "rel": 0.001}, 100.0, 100.4)
    assert within({"abs": 0}, 51, 51) and not within({"abs": 0}, 51, 50)


def test_references_folder_holds_only_the_reference_files():
    names = {path.relative_to(REFERENCES).as_posix() for path in REFERENCES.rglob("*")
             if path.is_file()}
    assert names == {"README.md"} | {f"{key[0]}/{key[1]}.yaml" for key in KEYS}
