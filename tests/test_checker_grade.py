"""Grading of the answer checker (T2.10), on answers supplied as data.

For every checkable task and level: a hand-written right answer, hand-written
wrong ones, every accepted alternative and every "not accepted" value of the
references. Extraction from response text is tested in
tests/test_checker_extract.py.
"""

import pytest

from checker.answers import AnswersError, answers_from_dict
from checker.formulas import (LEVELS, evaluate, level_quantities, load_reference,
                              reference_paths, within)
from checker.grade import grade

REFERENCE = {f"{p.parent.name}/{p.stem}": load_reference(p) for p in reference_paths()}


def q(value, unit=None, **inputs):
    entry = {"value": value}
    if unit is not None:
        entry["unit"] = unit
    if inputs:
        entry["inputs"] = inputs
    return entry


def run(task, level, quantities=None, complete=True, **rest):
    data = {"quantities": quantities or {}, "complete": complete, **rest}
    return grade(REFERENCE[task], level, answers_from_dict(data))


PASS = "pass"
TEETH = {"z1": 12, "z2": 68, "z3": 12, "z4": 72}
TEETH_READ = {"tooth_counts": {"stated_ratio_matches_counts": PASS,
                               "stated_speed_matches_counts": PASS}}
PUMP_READ = {"pump_kind": dict.fromkeys(
    ["kind_named", "reason_uses_duty", "kind_suits_duty", "runs_from_supply"], PASS)}
SPRING_INPUTS = {"d": 0.030, "D": 0.235, "Na": 13, "solid_length_in": 0.45,
                 "working_stress_psi": 31600, "compared_stress_psi": 31600,
                 "stated_limit_psi": 100800, "lasts": 1}
SPRING_READ = {
    "design_meets_requirements": {"solid_stress_compared": PASS,
                                  "coils_match_end_type": PASS},
    "life": {"verdict_given": PASS, "reason_uses_its_stress": PASS},
}
BRACKET_INPUTS = {"radius_in": 10, "e": 0.75, "s": 6, "stress_psi": 48}
BRACKET_READ = {
    "outline": dict.fromkeys(["quarter_disc", "sixteenths", "one_flat_piece"], PASS),
    "cad_file": dict.fromkeys(["flat_outline_format", "closed_outline_with_holes",
                               "matches_description"], PASS),
}

# A complete right answer for each checkable task and level, as a response
# would give it (other roundings and units than the reference's among them).
RIGHT = {
    ("math/loan-amortization", "L0"): dict(quantities={
        "monthly_payment": q(178.21, "$"), "total_interest": q(1692.60, "USD"),
        "payment_count": q(60), "total_paid": q(10692.60, "$")}),
    ("math/loan-amortization", "L2"): dict(quantities={
        "monthly_payment": q(178.21, "USD"), "final_payment": q(178.27, "$"),
        "total_interest_l2": q(1692.66, "$"), "schedule_rows": q(60),
        "first_payment_date": q("2027-04-01"), "final_payment_date": q("2032-03-01"),
        "balance_after_12": q(7442.13, "$"), "monthly_rate_percent": q(0.5833, "%")}),
    ("math/projectile-drag", "L2"): dict(quantities={
        "range": q(37.4, "m"), "flight_time": q(2.28, "s"), "max_height": q(6.41, "m"),
        "range_no_air": q(55.2, "m")}),
    ("math/hypothesis-test", "L0"): dict(quantities={
        "sample_mean": q(51.18), "decision": q("reject"), "p_value": q(0.0061),
        "t_statistic": q(3.87), "degrees_of_freedom": q(7)}),
    ("math/hypothesis-test", "L2"): dict(quantities={
        "w_plus": q(35), "w_minus": q(1), "p_value_exact": q(1.5625, "%"),
        "decision_l2": q("do not reject"),
        "ranks": q(dict(zip([50.8, 51.6, 49.7, 52.3, 51.1, 50.4, 52.0, 51.5],
                            [3, 6, 1, 8, 4, 2, 7, 5])))}),
    ("math/least-squares-fit", "L0"): dict(quantities={
        "slope": q(1.95), "intercept": q(0.21), "r_squared": q(0.997)}),
    ("math/least-squares-fit", "L2"): dict(quantities={
        "slope": q(1.946, "mm/N"), "intercept": q(0.2143, "mm"),
        "se_slope": q(0.04469), "se_intercept": q(0.1999),
        "slope_ci95_low": q(1.832), "slope_ci95_high": q(2.061),
        "residuals": q({7: 0.2607, 1: 0.1393, 2: -0.0071, 3: -0.2536, 4: 0.2,
                        5: -0.0464, 6: -0.2929}),
        "r_squared": q(0.9974), "spring_constant": q(0.5138, "N/mm")}),
    ("math/titration-curve", "L0"): dict(quantities={
        "equivalence_volume": q(25, "mL"), "ph_0_ml": q(2.9), "ph_12_5_ml": q(4.76),
        "ph_25_ml": q(8.73)}),
    ("math/titration-curve", "L2"): dict(quantities={
        "equivalence_volume": q(25.0, "mL"), "ph_0_ml": q(2.88), "ph_5_ml": q(4.14),
        "ph_10_ml": q(4.57), "ph_12_5_ml": q(4.75), "ph_20_ml": q(5.35),
        "ph_24_ml": q(6.13), "ph_25_ml": q(8.72), "ph_26_ml": q(11.29),
        "ph_30_ml": q(11.96), "ph_40_ml": q(12.36), "ph_50_ml": q(12.52)}),
    ("engineering/cantilever-beam", "L0"): dict(
        quantities={"reaction_force": q(4000, "N"), "max_bending_moment": q(6, "kNm")},
        inputs={"moment_knm": 6.0, "section_modulus_mm3": 88434, "allowable_mpa": 92,
                "modulus_gpa": 68.9, "second_moment_mm4": 4510134, "limit_mm": 15}),
    ("engineering/cantilever-beam", "L2"): dict(quantities={
        "required_section_modulus": q(65.2, "cm^3"),
        "required_second_moment": q(4.354e6, "mm^4"), "width": q(5.1, "cm"),
        "depth": q(102, "mm"), "governing_limit": q("deflection"),
        "bending_stress": q(67.8, "N/mm^2"), "tip_deflection": q(14.5, "mm")}),
    ("engineering/conveyor-gear-ratio", "L0"): dict(quantities={
        "drum_speed": q(50.9, "rpm"), "overall_ratio": q(28.5, motor_rpm=1450)}),
    ("engineering/conveyor-gear-ratio", "L2"): dict(
        quantities={"drum_speed": q(50.93, "r/min"), "exact_ratio": q(33.87)},
        inputs=TEETH, criteria=TEETH_READ),
    ("engineering/heat-sink", "L0"): dict(
        quantities={"total_resistance": q(4.25, "°C/W"),
                    "case_to_air_resistance": q(3.25, "K/W")},
        inputs={"junction_target_c": 125, "interface_resistance": 0.5,
                "sink_resistance": 2.5}),
    ("engineering/heat-sink", "L2"): dict(quantities={
        "total_resistance": q(4.25, "C/W"), "plate_resistance_limit": q(2.95, "°C/W"),
        "plate_area": q(339, "cm^2"), "square_side": q(135, "mm"),
        "junction_temperature": q(121, "°C")}),
    ("engineering/pipe-and-pump", "L0"): dict(
        quantities={"flow_velocity": q(1.19, "m/s"), "static_head": q(6, "m")},
        inputs={"duty_head_m": 7.5, "losses_m": 1.4, "rated_flow_l_per_s": 1.8},
        criteria={"pump_choice": {"duty_point_stated": PASS, "kind_suits_duty": PASS}}),
    ("engineering/pipe-and-pump", "L2"): dict(
        quantities={"flow_velocity": q(1.19, "m/s"), "friction_loss": q(18.1, "kPa"),
                    "total_head": q(7.84, "m"), "hydraulic_power": q(115, "W"),
                    "electrical_power": q(0.288, "kW"), "battery_current": q(24.0, "A")},
        criteria=PUMP_READ),
    ("engineering/shelf-bracket", "L2"): dict(
        quantities={"moment_at_wall": q(200, "lbf-in"),
                    "quarter_disc_stress_at_wall": q(48, "psi", radius_in=10),
                    "screw_downward_force": q(20, "lb"),
                    "screw_sideways_force": q(28.3, "lb", e=0.75, s=6)},
        inputs=BRACKET_INPUTS, criteria=BRACKET_READ),
    ("engineering/compression-spring", "L2"): dict(
        quantities={"spring_rate": q(6.0, "lbf/in"),
                    "rate_from_geometry": q(6.0, "lb/in"),
                    "shear_stress": q(31.6, "ksi", F=1.2),
                    "solid_length": q(0.450, "in", Nt=15)},
        inputs=SPRING_INPUTS, criteria=SPRING_READ),
}
# L1 asks the same things as L0, with the same references.
for (task, level), answer in list(RIGHT.items()):
    if level == "L0" and REFERENCE[task]["levels"]["L1"]["checkable"]:
        RIGHT[(task, "L1")] = answer

CHECKABLE = sorted((task, level) for task, reference in REFERENCE.items()
                   for level in LEVELS if reference["levels"][level]["checkable"])


def test_every_checkable_task_and_level_has_a_right_answer():
    assert sorted(RIGHT) == CHECKABLE


@pytest.mark.parametrize("task,level", CHECKABLE)
def test_a_known_right_answer_is_correct(task, level):
    result = run(task, level, **RIGHT[(task, level)])
    assert result["verdict"] == "correct", result
    assert result["partial"] is bool(REFERENCE[task]["levels"][level].get("partial"))
    for name in RIGHT[(task, level)]["quantities"]:
        assert result["quantities"][name]["status"] == "correct", name


# Hand-written wrong answers: one quantity of the right answer replaced.
WRONG = [
    ("math/loan-amortization", "L0", "monthly_payment", q(188.21, "$")),
    ("math/loan-amortization", "L1", "total_interest", q(3150, "$")),
    ("math/loan-amortization", "L2", "final_payment", q(178.21, "$")),
    ("math/loan-amortization", "L2", "schedule_rows", q(59)),
    ("math/loan-amortization", "L2", "first_payment_date", q("2027-03-01")),
    ("math/projectile-drag", "L2", "range", q(55.2, "m")),
    ("math/projectile-drag", "L2", "flight_time", q(2.55, "s")),
    ("math/hypothesis-test", "L0", "decision", q("do_not_reject")),
    ("math/hypothesis-test", "L1", "p_value", q(0.0031)),
    ("math/hypothesis-test", "L2", "decision_l2", q("reject")),
    ("math/hypothesis-test", "L2", "w_plus", q(36)),
    ("math/hypothesis-test", "L2", "ranks",
     q({50.8: 3, 51.6: 6, 49.7: 1, 52.3: 8, 51.1: 4, 50.4: 2, 52.0: 7})),
    ("math/least-squares-fit", "L0", "slope", q(1.99)),
    ("math/least-squares-fit", "L1", "intercept", q(0.0)),
    ("math/least-squares-fit", "L2", "residuals",
     q({1: 0.2607, 7: 0.1393, 2: -0.0071, 3: -0.2536, 4: 0.2, 5: -0.0464,
        6: -0.2929})),
    ("math/least-squares-fit", "L2", "spring_constant", q(0.5138, "N/m")),
    ("math/titration-curve", "L0", "ph_25_ml", q(7.00)),
    ("math/titration-curve", "L1", "equivalence_volume", q(12.5, "mL")),
    ("math/titration-curve", "L2", "ph_26_ml", q(11.59)),
    ("engineering/cantilever-beam", "L0", "reaction_force", q(2, "kN")),
    ("engineering/cantilever-beam", "L1", "max_bending_moment", q(3, "kN·m")),
    ("engineering/cantilever-beam", "L2", "width", q(50, "mm")),
    ("engineering/cantilever-beam", "L2", "governing_limit", q("stress")),
    ("engineering/conveyor-gear-ratio", "L0", "overall_ratio",
     q(33.9, motor_rpm=1450)),
    ("engineering/conveyor-gear-ratio", "L1", "drum_speed", q(25.5, "rpm")),
    ("engineering/conveyor-gear-ratio", "L2", "exact_ratio", q(34.36)),
    ("engineering/heat-sink", "L0", "total_resistance", q(6.25, "°C/W")),
    ("engineering/heat-sink", "L1", "case_to_air_resistance", q(4.25, "°C/W")),
    ("engineering/heat-sink", "L2", "square_side", q(130, "mm")),
    ("engineering/pipe-and-pump", "L0", "flow_velocity", q(0.30, "m/s")),
    ("engineering/pipe-and-pump", "L1", "static_head", q(60, "m")),
    ("engineering/pipe-and-pump", "L2", "battery_current", q(9.61, "A")),
    ("engineering/shelf-bracket", "L2", "moment_at_wall", q(400, "lb·in")),
    ("engineering/shelf-bracket", "L2", "screw_sideways_force",
     q(34.0, "lb", e=0.75, s=6)),
    ("engineering/compression-spring", "L2", "spring_rate", q(2.18, "lbf/in")),
    ("engineering/compression-spring", "L2", "shear_stress", q(26602, "psi", F=1.2)),
]


@pytest.mark.parametrize("task,level,name,wrong", WRONG)
def test_a_known_wrong_answer_is_wrong(task, level, name, wrong):
    answer = dict(RIGHT[(task, level)])
    answer["quantities"] = dict(answer["quantities"], **{name: wrong})
    result = run(task, level, **answer)
    assert result["quantities"][name]["status"] == "wrong", result["quantities"][name]
    assert result["verdict"] == "wrong"


def numeric(task, name):
    return REFERENCE[task]["quantities"][name]


def listed_levels(task, name):
    return [level for level in LEVELS
            if name in level_quantities(REFERENCE[task]["levels"][level])]


def examples(group):
    return [(task, level, name, entry["value"])
            for task, reference in REFERENCE.items()
            for name, quantity in reference["quantities"].items()
            for entry in quantity.get(group, ())
            for level in listed_levels(task, name)]


def one(task, level, name, value, **rest):
    unit = numeric(task, name)["unit"]
    return run(task, level, {name: q(value, unit)}, **rest)["quantities"][name]


@pytest.mark.parametrize("task,level,name,value", examples("not_accepted"))
def test_every_not_accepted_value_is_wrong(task, level, name, value):
    assert one(task, level, name, value)["status"] == "wrong"


@pytest.mark.parametrize("task,level,name,value", examples("accepted_examples"))
def test_every_accepted_example_is_correct(task, level, name, value):
    assert one(task, level, name, value)["status"] == "correct"


def alternatives():
    for task, reference in REFERENCE.items():
        for name, quantity in reference["quantities"].items():
            for alternative in quantity.get("alternatives", ()):
                for level in listed_levels(task, name):
                    if level in alternative.get("levels", LEVELS):
                        yield task, level, name, alternative["id"]


def alternative_case(task, name, identifier):
    quantity = numeric(task, name)
    alternative = next(a for a in quantity["alternatives"] if a["id"] == identifier)
    facts = {}
    if task == "math/hypothesis-test":
        if name == "p_value":
            facts = {"test": identifier}
        else:
            facts = {"t_test_at_1_percent": {"test": "t", "level_percent": 1},
                     "wilcoxon_at_5_percent": {"test": "wilcoxon_exact",
                                               "level_percent": 5},
                     "wilcoxon_at_1_percent": {"test": "wilcoxon_exact",
                                               "level_percent": 1},
                     "sign_test": {"test": "sign_test", "level_percent": 5}}[identifier]
    if "value" in alternative:
        value, inputs = alternative["value"], {}
    else:
        example = alternative["examples"][0]
        value, inputs = example["value"], example["inputs"]
    unit = None if quantity.get("type") == "choice" else quantity["unit"]
    if isinstance(value, list):
        value = dict(zip(quantity["keyed_by"]["values"], value))
    return q(value, unit, **inputs), facts


@pytest.mark.parametrize("task,level,name,identifier", sorted(alternatives()))
def test_every_alternative_is_accepted_and_named(task, level, name, identifier):
    entry, facts = alternative_case(task, name, identifier)
    result = run(task, level, {name: entry}, conditions={identifier: True},
                 facts=facts)["quantities"][name]
    quantity = numeric(task, name)
    reference_too = quantity.get("value") == entry["value"] and not facts
    if reference_too:
        assert result["status"] == "correct", result
    else:
        assert result["status"] == "correct_alternative", result
        assert result["alternative"] == identifier


# Fixed alternatives whose value differs from the reference's.
DIFFERING = sorted(
    (task, level, name, identifier)
    for task, level, name, identifier in alternatives()
    if task != "math/hypothesis-test"
    for a in numeric(task, name)["alternatives"]
    if a["id"] == identifier and "value" in a
    and numeric(task, name).get("type", "number") == "number"
    and not within(numeric(task, name)["tolerance"], numeric(task, name)["value"],
                   a["value"]))


@pytest.mark.parametrize("task,level,name,identifier", DIFFERING)
def test_an_alternative_needs_its_condition(task, level, name, identifier):
    entry, _ = alternative_case(task, name, identifier)
    absent = run(task, level, {name: entry}, conditions={identifier: False})
    assert absent["quantities"][name]["status"] == "wrong"
    unknown = run(task, level, {name: entry}, complete=False)
    assert unknown["quantities"][name]["status"] == "could_not_determine"


@pytest.mark.parametrize("task,name,identifier", [
    ("math/loan-amortization", "monthly_payment", "effective_annual_rate"),
])
def test_an_alternative_is_refused_at_other_levels(task, name, identifier):
    result = run(task, "L2", {name: q(177.30, "$")}, conditions={identifier: True})
    assert result["quantities"][name]["status"] == "wrong"


def conditional_examples():
    for task, reference in REFERENCE.items():
        for name, quantity in reference["quantities"].items():
            if quantity["kind"] == "conditional":
                for level in listed_levels(task, name):
                    for index in range(len(quantity["examples"])):
                        yield task, level, name, index


@pytest.mark.parametrize("task,level,name,index", sorted(conditional_examples()))
def test_conditional_answers_follow_the_stated_inputs(task, level, name, index):
    quantity = numeric(task, name)
    example = quantity["examples"][index]
    unit = None if quantity["unit"].startswith("the answer") else quantity["unit"]
    for value, status in ((example["value"], "correct"),
                          (example["value"] * 1.25 + 1, "wrong")):
        result = run(task, level, {name: q(value, unit, **example["inputs"])},
                     conditions={a["id"]: False
                                 for a in quantity.get("alternatives", ())})
        assert result["quantities"][name]["status"] == status, (value, result)


def test_a_conditional_answer_without_its_inputs_is_not_graded():
    result = run("engineering/conveyor-gear-ratio", "L0",
                 {"overall_ratio": q(28.47), "drum_speed": q(50.9, "rpm")},
                 complete=False)
    assert result["quantities"]["overall_ratio"]["status"] == "could_not_determine"
    assert result["verdict"] == "could_not_determine"


def test_a_range_is_used_only_when_the_choice_is_known_to_be_unstated():
    entry = {"reynolds_number": q(47000)}
    task = "engineering/pipe-and-pump"
    assert run(task, "L0", entry)["quantities"]["reynolds_number"]["status"] == "correct"
    unknown = run(task, "L0", entry, complete=False)
    assert unknown["quantities"]["reynolds_number"]["status"] == "could_not_determine"
    outside = run(task, "L0", {"reynolds_number": q(90000)})
    assert outside["quantities"]["reynolds_number"]["status"] == "wrong"
    warm = run(task, "L0", {"reynolds_number": q(53468, temperature_c=25)})
    assert warm["quantities"]["reynolds_number"]["status"] == "correct"


def test_friction_by_the_stated_roughness_and_temperature():
    task, name = "engineering/pipe-and-pump", "friction_head_straight_pipe"
    for example in numeric(task, name)["examples"]:
        for value, status in ((example["value"], "correct"),
                              (example["value"] * 1.2, "wrong")):
            result = run(task, "L0", {name: q(value, "m", **example["inputs"])},
                         conditions={"hazen_williams": False})
            assert result["quantities"][name]["status"] == status, example
    odd = run(task, "L0", {name: q(1.4, "m", roughness_mm=0, temperature_c=18)})
    assert odd["quantities"][name]["status"] == "could_not_determine"


def test_ph_at_any_volume_for_stated_constants():
    task, name = "math/titration-curve", "ph_at_volume"
    entries = [q(e["value"], "pH", **e["inputs"]) for e in numeric(task, name)["examples"]]
    result = run(task, "L2", {name: entries})["quantities"][name]
    assert result["status"] == "correct", result
    entries.append(q(9.9, "pH", base_ml=15, ka=1.8e-5, kw=1e-14))
    assert run(task, "L2", {name: entries})["quantities"][name]["status"] == "wrong"


@pytest.mark.parametrize("value,unit,status", [
    (178.21, None, "correct"), (178.21, "EUR", "correct"),
    (178.21, "kg", "could_not_determine"),
])
def test_currency_units(value, unit, status):
    result = run("math/loan-amortization", "L0", {"monthly_payment": q(value, unit)})
    assert result["quantities"]["monthly_payment"]["status"] == status


@pytest.mark.parametrize("unit", [None, "mm", "furlong"])
def test_a_dimensional_value_without_a_usable_unit_is_not_graded(unit):
    result = run("engineering/cantilever-beam", "L2",
                 {"bending_stress": q(67.85, unit)})
    assert result["quantities"]["bending_stress"]["status"] == "could_not_determine"


def test_missing_quantities():
    complete = run("math/projectile-drag", "L2", {"range": q(37.4, "m")})
    assert complete["quantities"]["flight_time"]["status"] == "not_stated"
    assert complete["verdict"] == "incomplete"
    partial = run("math/projectile-drag", "L2", {"range": q(37.4, "m")}, complete=False)
    assert partial["quantities"]["flight_time"]["status"] == "could_not_determine"
    assert partial["verdict"] == "could_not_determine"
    said = run("math/projectile-drag", "L2", {"flight_time": "not_stated"},
               complete=False)
    assert said["quantities"]["flight_time"]["status"] == "not_stated"


def test_one_of_groups_and_if_reported():
    base = {"sample_mean": q(51.175), "decision": q("reject")}
    task = "math/hypothesis-test"
    assert run(task, "L0", base)["verdict"] == "incomplete"
    interval = dict(base, ci95_low=q(50.46), ci95_high=q(51.89))
    assert run(task, "L0", interval)["verdict"] == "correct"
    half = dict(base, ci95_low=q(50.46))
    assert run(task, "L0", half)["verdict"] == "incomplete"
    spoiled = dict(interval, p_value=q(0.2))
    assert run(task, "L0", spoiled)["verdict"] == "wrong"
    side = dict(interval, sample_sd=q(0.80))
    assert run(task, "L0", side)["verdict"] == "wrong"


def test_the_level_verdict_names_an_alternative():
    answer = {"sample_mean": q(51.175), "decision": q("reject"), "p_value": q(0.0156)}
    result = run("math/hypothesis-test", "L0", answer,
                 facts={"test": "wilcoxon_exact"})
    assert result["verdict"] == "correct_alternative"
    assert result["alternatives"] == ["wilcoxon_at_5_percent", "wilcoxon_exact"]


def test_a_p_value_is_graded_against_the_test_used():
    task = "math/hypothesis-test"

    def status(value, **facts):
        return run(task, "L0", {"p_value": q(value)}, complete=False,
                   facts=facts)["quantities"]["p_value"]["status"]

    assert status(0.0061, test="wilcoxon_exact") == "wrong"
    assert status(0.0061) == "could_not_determine"
    assert status(0.0001, test="z") == "wrong"
    assert status(0.0173, test="wilcoxon") == "could_not_determine"


@pytest.mark.parametrize("task,level", [
    (task, level) for task, reference in REFERENCE.items() for level in LEVELS
    if not reference["levels"][level]["checkable"]])
def test_levels_without_a_reference_get_no_correctness_result(task, level):
    assert run(task, level)["verdict"] == "not_checkable"


def test_side_checks_at_an_uncheckable_level():
    result = run("math/projectile-drag", "L0", {"range_no_air": q(55.2, "m")},
                 inputs={"range_m": 40})
    assert result["verdict"] == "not_checkable"
    assert result["quantities"]["range_no_air"]["status"] == "correct"
    assert result["criteria"]["range_is_shorter_than_with_no_air"]["status"] == "pass"


def test_criteria_decide_with_the_answers():
    right = RIGHT[("engineering/conveyor-gear-ratio", "L2")]
    task = "engineering/conveyor-gear-ratio"
    bad = dict(right, inputs=dict(TEETH, z2=40))
    assert run(task, "L2", **bad)["verdict"] == "wrong"
    unread = dict(right, criteria={}, complete=False)
    result = run(task, "L2", **unread)
    assert result["verdict"] == "could_not_determine"
    assert result["answers_verdict"] == "correct"
    unknown = dict(right, inputs={})
    assert run(task, "L2", **unknown)["verdict"] == "could_not_determine"


def test_tooth_text_items_follow_the_graded_quantities():
    right = RIGHT[("engineering/conveyor-gear-ratio", "L2")]
    quantities = dict(right["quantities"], tooth_ratio=q(34.0, **TEETH),
                      belt_speed_for_teeth=q(0.39847, "m/s", **TEETH))
    result = run("engineering/conveyor-gear-ratio", "L2", quantities, inputs=TEETH)
    assert result["verdict"] == "correct", result


def test_record_only_items_do_not_decide():
    answer = dict(RIGHT[("engineering/compression-spring", "L2")])
    answer["inputs"] = dict(SPRING_INPUTS, solid_length_in=0.54, stated_limit_psi=50000)
    answer["quantities"] = dict(answer["quantities"],
                                solid_length=q(0.54, "in", Nt=18))
    result = run("engineering/compression-spring", "L2", **answer)
    assert result["criteria"]["design_meets_requirements"]["status"] == "pass"


@pytest.mark.parametrize("inputs", [
    {"motor_rpm": 0, "ratio": 0}, {"motor_rpm": 1e300, "ratio": 1e-300},
])
def test_impossible_inputs_are_not_graded(inputs):
    result = run("engineering/conveyor-gear-ratio", "L0",
                 {"belt_speed_for_stated_ratio": q(0.4, "m/s", **inputs)})
    status = result["quantities"]["belt_speed_for_stated_ratio"]["status"]
    assert status == "could_not_determine"


@pytest.mark.parametrize("data", [
    {"quantities": {"range": {"value": [1]}}, "unknown": 1},
    {"quantities": {"range": {"val": 1}}},
    {"quantities": {"range": {"value": float("nan")}}},
    {"inputs": {"d": "1e9999"}},
    {"conditions": {"one_face": "yes"}},
    {"criteria": {"life": {"verdict_given": "maybe"}}},
    {"review": {"range": "yes"}},
    {"review": ["range"]},
    [1, 2],
])
def test_a_malformed_answers_file_is_refused(data):
    with pytest.raises(AnswersError):
        answers_from_dict(data)


def test_a_quantity_the_task_does_not_have_is_refused():
    with pytest.raises(AnswersError):
        run("math/projectile-drag", "L2", {"rnage": q(37.4, "m")})
    with pytest.raises(AnswersError):
        run("math/projectile-drag", "L2", review={"rnage": "confirmed"})


def test_supplied_values_are_never_only_suspected():
    for task, level, name, wrong in WRONG:
        answer = dict(RIGHT[(task, level)])
        answer["quantities"] = dict(answer["quantities"], **{name: wrong})
        assert run(task, level, **answer)["verdict"] == "wrong"
        part = run(task, level, **dict(answer, complete=False))
        assert "suspected_wrong" not in {r["status"] for r in part["quantities"].values()}
        assert part["verdict"] in ("wrong", "could_not_determine")


def test_every_formula_comes_through_the_shared_evaluator():
    import reference_checks
    assert reference_checks.evaluate is evaluate


def test_the_default_level_is_not_assumed_for_a_part_answer():
    answer = {"decision": q("reject")}
    part = run("math/hypothesis-test", "L0", answer, complete=False,
               facts={"test": "t"})
    assert part["quantities"]["decision"]["status"] == "could_not_determine"
    full = run("math/hypothesis-test", "L0", answer, facts={"test": "t"})
    assert full["quantities"]["decision"]["status"] == "correct"


def test_an_item_about_a_figure_never_stated_does_not_apply():
    task = "engineering/conveyor-gear-ratio"
    right = RIGHT[(task, "L2")]
    result = run(task, "L2", **dict(right, criteria={}))
    items = result["criteria"]["tooth_counts"]["items"]
    assert items["stated_ratio_matches_counts"]["status"] == "not_applicable"
    assert result["verdict"] == "correct", result
    part = run(task, "L2", **dict(right, criteria={}, complete=False))
    assert part["verdict"] == "could_not_determine"


def test_a_level_with_only_alternative_groups_can_be_graded():
    reference = dict(REFERENCE["math/hypothesis-test"])
    level = {k: v for k, v in reference["levels"]["L0"].items() if k != "quantities"}
    reference["levels"] = dict(reference["levels"], L0=level)
    answers = answers_from_dict({"quantities": {"p_value": q(0.0061)}, "complete": True})
    assert grade(reference, "L0", answers)["verdict"] == "correct"
