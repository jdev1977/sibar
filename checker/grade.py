"""Grading one response's answers against a reference file.

The rule everywhere: where it cannot be established that an answer is right
or that it is wrong, the result is ``could_not_determine``. A mismatch found
by reading the response's text is never a final ``wrong``: text cannot tell
a wrong answer from one under an assumption of the response's own, so it is
``suspected_wrong`` until an answers file supplies the value or a reader
confirms it. The meaning of levels, alternatives, conditional answers and
tolerances is set by checker/references/README.md.
"""

import math

from checker import units
from checker.answers import CONFIRMED, EXTRACTED, NOT_STATED, AnswersError
from checker.formulas import (evaluate, level_quantities, paired, tolerance_for,
                              within)
from checker.methods import METHODS, VISCOSITY

CORRECT = "correct"
ALTERNATIVE = "correct_alternative"
WRONG = "wrong"
SUSPECTED = "suspected_wrong"
UNSTATED = "not_stated"
UNKNOWN = "could_not_determine"
INCOMPLETE = "incomplete"
NOT_CHECKABLE = "not_checkable"
PASS, FAIL, NOT_APPLICABLE = "pass", "fail", "not_applicable"
SUSPECTED_FAIL = "suspected_fail"
RIGHT = (CORRECT, ALTERNATIVE)

# Alternatives that replace the reference: a response that states one and
# gives the reference value contradicts itself, which is not graded.
REPLACING = frozenset({"effective_annual_rate", "fitted_minus_measured"})

WILCOXON = ("wilcoxon_exact", "wilcoxon_normal", "wilcoxon_normal_corrected")
# Criterion items a response may leave out altogether ("if the answer ...").
OPTIONAL_ITEMS = {("section_meets_its_own_limits", "deflection_within_limit"):
                  "limit_mm",
                  ("pump_choice", "pump_covers_duty"): "rated_flow_l_per_s"}
# An input with a value the criterion sets when the response states none.
DEFAULT_INPUTS = {("life", "verdict_follows"): {"stated_limit_psi": 100800.0}}
# Text items that a graded quantity settles.
ITEM_FROM_QUANTITY = {("tooth_counts", "stated_ratio_matches_counts"): "tooth_ratio",
                      ("tooth_counts", "stated_speed_matches_counts"):
                      "belt_speed_for_teeth"}


def _result(status, reason=None, alternative=None):
    found = {"status": status}
    if alternative:
        found["alternative"] = alternative
    if reason:
        found["reason"] = reason
    return found


class _Grader:
    def __init__(self, reference, level, answers):
        self.reference, self.level, self.answers = reference, level, answers
        self.task = reference["task_id"]

    # --- computing an expected value ---------------------------------------

    def inputs_for(self, holder, statement):
        """The inputs of a formula, or None where one is not known."""
        known = {**self.answers.inputs, **statement.inputs}
        if ("viscosity_mm2_per_s" in holder["inputs"]
                and "viscosity_mm2_per_s" not in known
                and known.get("temperature_c") in VISCOSITY):
            known["viscosity_mm2_per_s"] = VISCOSITY[known["temperature_c"]] * 1e6
        if not all(name in known for name in holder["inputs"]):
            return None
        return {name: float(known[name]) for name in holder["inputs"]}

    def expected(self, name, holder, statement):
        """The value of a reference or alternative, or None."""
        if "value" in holder and "inputs" not in holder:
            return holder["value"]
        inputs = self.inputs_for(holder, statement)
        if inputs is None:
            return None
        try:
            if "formula" in holder:
                value = evaluate(holder["formula"], inputs)
            else:
                value = METHODS[(self.task, name)](inputs)
        except (ArithmeticError, ValueError, KeyError, TypeError):
            return None
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        return value

    # --- one statement ------------------------------------------------------

    def converted(self, quantity, statement):
        """``(factor, offset)`` of the statement's unit, or None."""
        if quantity["unit"].startswith("the answer"):
            return 1.0, 0.0
        unit = statement.unit
        if unit is None:
            unit = ""
        return units.conversion(unit, quantity)

    def matches(self, tolerance, reference, quantity, statement, scale):
        """Whether the stated value is the reference one, and how far off."""
        factor, offset = scale
        kind = quantity.get("type", "number")
        value = statement.value
        if kind == "list":
            pairs = paired(dict(quantity, value=reference), value)
            if pairs is None:
                return False, math.inf
        else:
            pairs = [(reference, value)]
        scaled = dict(tolerance)
        if "abs" in scaled:
            scaled["abs"] = scaled["abs"] * factor
        gap = 0.0
        for wanted, stated in pairs:
            wanted = wanted * factor + offset
            if not within(scaled, wanted, stated):
                return False, math.inf
            gap = max(gap, abs(stated - wanted))
        return True, gap

    def statement(self, name, statement):
        """The result for one statement of a quantity."""
        quantity = self.reference["quantities"][name]
        kind = quantity.get("type", "number")
        if kind in ("choice", "date"):
            return self.word(name, quantity, statement)
        value = statement.value
        shape = dict if kind == "list" else (int, float)
        if not isinstance(value, shape):
            return _result(UNKNOWN, "the stated value is not of the quantity's type")
        scale = self.converted(quantity, statement)
        if scale is None:
            return _result(UNKNOWN, "no unit, or a unit the reference does not list")
        if self.reference["task_id"] == "hypothesis-test" and name == "p_value":
            return self.p_value(quantity, statement, scale)
        alternatives = [a for a in quantity.get("alternatives", ())
                        if self.level in a.get("levels", (self.level,))]
        own = self.expected(name, quantity, statement)
        own_match = (False, math.inf)
        if own is not None:
            own_match = self.matches(tolerance_for(quantity, self.level), own,
                                     quantity, statement, scale)
        pending = []
        for alternative in alternatives:
            state = self.answers.condition(alternative["id"])
            if state is False:
                continue
            wanted = self.expected(name, alternative, statement)
            if wanted is None:
                pending.append(alternative["id"])
                continue
            tolerance = tolerance_for(quantity, self.level, alternative)
            found, gap = self.matches(tolerance, wanted, quantity, statement, scale)
            if not found:
                continue
            if state is None:
                pending.append(alternative["id"])
            elif not own_match[0] or gap <= own_match[1]:
                return _result(ALTERNATIVE, alternative=alternative["id"])
        if own_match[0]:
            # from text, a mention of the replacing assumption leaves it open
            opened = (True, None) if statement.source == EXTRACTED else (True,)
            if any(a["id"] in REPLACING and self.answers.condition(a["id"]) in opened
                   for a in alternatives):
                return _result(UNKNOWN, "the reference value, with an assumption "
                                        "stated that changes it")
            return _result(CORRECT)
        if pending:
            return _result(UNKNOWN, "could be right under an alternative that is "
                                    f"not established: {', '.join(sorted(pending))}")
        if own is None:
            return self.in_range(quantity, statement, scale)
        return _result(WRONG)

    def in_range(self, quantity, statement, scale):
        span = quantity.get("range")
        missing = [n for n in quantity.get("inputs", ())
                   if n not in self.answers.inputs and n not in statement.inputs]
        stated_some = len(missing) < len(quantity.get("inputs", ()))
        if (span is None or stated_some or not self.answers.complete
                or "temperature_c" in {**self.answers.inputs, **statement.inputs}):
            return _result(UNKNOWN, "the choices this answer depends on are not "
                                    "established")
        factor, offset = scale
        if span["low"] * factor + offset <= statement.value <= span["high"] * factor + offset:
            return _result(CORRECT, "inside the range for an unstated choice")
        return _result(WRONG, "outside the range for an unstated choice")

    def word(self, name, quantity, statement):
        if not isinstance(statement.value, str):
            return _result(UNKNOWN, "the stated value is not text")
        stated = "_".join(statement.value.strip().lower().split())
        if quantity["type"] == "date":
            if len(stated) != 10:
                return _result(UNKNOWN, "not an ISO date")
        elif stated not in quantity["choices"]:
            return _result(UNKNOWN, "not one of the choices")
        if self.task == "hypothesis-test" and name == "decision":
            return self.decision(stated)
        return _result(CORRECT if stated == quantity["value"] else WRONG)

    # --- the hypothesis test: graded against the test used ------------------

    def tests(self):
        if self.answers.tests:
            return self.answers.tests
        return ("t",) if self.answers.complete else ()

    def p_of(self, test):
        quantity = self.reference["quantities"]["p_value"]
        if test == "t":
            return quantity
        return next((a for a in quantity["alternatives"] if a["id"] == test), None)

    def p_value(self, quantity, statement, scale):
        tests = self.tests()
        if len(tests) != 1 or tests[0] == "other":
            return _result(UNKNOWN, "the test the answer uses is not established")
        test = tests[0]

        def found(holder):
            tolerance = tolerance_for(quantity, self.level,
                                      None if holder is quantity else holder)
            return self.matches(tolerance, holder["value"], quantity, statement,
                                scale)[0]

        if test == "wilcoxon":
            if any(found(self.p_of(variant)) for variant in WILCOXON):
                return _result(UNKNOWN, "which Wilcoxon p-value is meant is not "
                                        "established")
            return _result(WRONG)
        holder = quantity if test == "z" else self.p_of(test)
        if not found(holder):
            return _result(WRONG)
        if test == "z":
            return _result(UNKNOWN, "a z test that gives the t test's value")
        if holder is quantity:
            return _result(CORRECT)
        return _result(ALTERNATIVE, alternative=test)

    def decision(self, stated):
        tests = self.tests()
        # 5% where none is stated, which only complete answers can show
        # (the extractor gives it as a level where it finds none)
        levels = self.answers.levels or ((5.0,) if self.answers.complete else ())
        if not tests or len(levels) != 1:
            return _result(UNKNOWN, "the test or the level is not established")
        level = levels[0]
        expected = set()
        for test in tests:
            variants = WILCOXON if test == "wilcoxon" else (test,)
            for variant in variants:
                holder = self.p_of(variant)
                if holder is None:
                    return _result(UNKNOWN, "no reference p-value for the test used")
                expected.add("reject" if holder["value"] < level / 100
                             else "do_not_reject")
        if len(expected) != 1:
            return _result(UNKNOWN, "the tests used lead to different decisions")
        if stated != expected.pop():
            return _result(WRONG)
        identifier = None
        if all(t.startswith(("wilcoxon", "sign_flip")) for t in tests):
            identifier = {5.0: "wilcoxon_at_5_percent",
                          1.0: "wilcoxon_at_1_percent"}.get(level)
        elif tests == ("sign_test",):
            identifier = "sign_test"
        elif tests == ("t",) and level == 1.0:
            identifier = "t_test_at_1_percent"
        if identifier:
            return _result(ALTERNATIVE, alternative=identifier)
        return _result(CORRECT)

    # --- one quantity -------------------------------------------------------

    def quantity(self, name):
        statements = self.answers.quantities.get(name)
        if statements == NOT_STATED:
            return _result(UNSTATED)
        if not statements:
            if self.answers.complete:
                return _result(UNSTATED)
            return _result(UNKNOWN, "no value was found")
        results = [self.statement(name, s) for s in statements]
        shown = {"stated": [self.shown(s) for s in statements]}
        if statements[0].source != EXTRACTED:
            chosen = next((r for wanted in (WRONG, UNKNOWN, ALTERNATIVE, CORRECT)
                           for r in results if r["status"] == wanted), results[0])
            return {**chosen, **shown}
        found = self.extracted(name, statements, results)
        ruling = self.answers.review.get(name)      # a reader's ruling on it
        if ruling:
            if found["status"] != SUSPECTED:
                found = {**found, "review": "not_applied"}
            elif ruling == CONFIRMED:
                found = {**_result(WRONG, "a reader confirmed the value found"),
                         "review": ruling}
            else:
                found = {**_result(UNKNOWN, "a reader rejected the value found"),
                         "review": ruling}
        return {**found, **shown}

    def extracted(self, name, statements, results):
        """One result from the statements found in the response: they must
        all lead to it. A mismatch is at most suspected."""
        plain = [(s, r) for s, r in zip(statements, results) if not s.hedged]
        if not plain:
            return _result(UNKNOWN, "only found in a comparison, condition or check")
        outcomes = {(r["status"], r.get("alternative")) for r in results}
        if len(outcomes) != 1:
            return _result(UNKNOWN, "the response states values that grade differently")
        found = plain[0][1]
        if found["status"] != UNKNOWN and any(s.unsettled for s in statements):
            return _result(UNKNOWN, "a correction or summary in the response holds a "
                                    "number that was not read")
        if found["status"] == WRONG:
            # Text cannot tell a wrong answer from one under an assumption of
            # the response's own, or from a number the extractor misread.
            cut = any(s.cut_off for s in statements)
            return _result(SUSPECTED, "the value found in the text does not match"
                           + (" (the response is cut off)" if cut else "")
                           + "; needs review")
        return found

    @staticmethod
    def shown(statement):
        value = statement.value
        if isinstance(value, dict):
            value = [[key, value[key]] for key in sorted(value)]
        found = {"value": value, "source": statement.source}
        if statement.unit:
            found["unit"] = statement.unit
        if statement.inputs:
            found["inputs"] = dict(sorted(statement.inputs.items()))
        if statement.hedged:
            found["hedged"] = True
        return found

    # --- criteria -----------------------------------------------------------

    def item(self, criterion, item, quantities):
        judged = self.answers.criteria.get(criterion, {}).get(item["id"])
        key = (criterion, item["id"])
        if "check" not in item:
            if judged:
                return judged
            source = quantities.get(ITEM_FROM_QUANTITY.get(key), {}).get("status")
            if source in RIGHT:
                return PASS
            if source == UNSTATED:
                return NOT_APPLICABLE       # nothing stated to hold to the rule
            return {WRONG: FAIL, SUSPECTED: SUSPECTED_FAIL}.get(source, UNKNOWN)
        known = dict(self.answers.inputs)
        if self.answers.complete:
            for name, value in DEFAULT_INPUTS.get(key, {}).items():
                known.setdefault(name, value)
        from_text = self.answers.extracted_inputs & set(item["inputs"])
        if judged and (from_text or not all(name in known for name in item["inputs"])):
            return judged
        if not all(name in known for name in item["inputs"]):
            optional = OPTIONAL_ITEMS.get(key)
            if optional and optional not in known and self.answers.complete:
                return NOT_APPLICABLE
            return UNKNOWN
        try:
            met = evaluate(item["check"],
                           {n: float(known[n]) for n in item["inputs"]}, allow_logic=True)
        except (ArithmeticError, ValueError, TypeError):
            return UNKNOWN
        if met:
            return PASS
        return SUSPECTED_FAIL if from_text else FAIL    # found inputs: only suspected

    def criterion(self, name, quantities):
        items, decisive = {}, []
        for item in self.reference["criteria"][name]["pass_when"]:
            status = self.item(name, item, quantities)
            items[item["id"]] = {"status": status}
            if item.get("record_only"):
                items[item["id"]]["record_only"] = True
            else:
                decisive.append(status)
        if FAIL in decisive:
            status = FAIL
        elif SUSPECTED_FAIL in decisive:
            status = SUSPECTED_FAIL
        elif all(s in (PASS, NOT_APPLICABLE) for s in decisive):
            status = PASS
        else:
            status = UNKNOWN
        return {"status": status, "items": items}


def _complete_verdict(entry, results):
    """The verdict on the reference values of a checkable level."""
    status = {name: result["status"] for name, result in results.items()}
    for worst in (WRONG, SUSPECTED):
        if worst in status.values():
            return worst
    required = [status[name] for name in entry.get("quantities", ())]
    groups = [[status[name] for name in group] for group in entry.get("one_of", ())]
    # An extra value found but not settled could be a wrong one.
    unsettled = any(result["status"] == UNKNOWN and len(result.get("stated", ())) > 1
                    for result in results.values())
    if UNKNOWN in required or unsettled:
        return UNKNOWN
    met = not groups or any(all(s in RIGHT for s in group) for group in groups)
    if UNSTATED in required:
        return INCOMPLETE
    if not met:
        return UNKNOWN if any(UNKNOWN in group for group in groups) else INCOMPLETE
    return ALTERNATIVE if ALTERNATIVE in status.values() else CORRECT


def grade(reference, level, answers):
    """The result for one response: per quantity, per criterion and for the
    level. ``verdict`` takes the criteria into account; ``answers_verdict``
    is about the reference values alone."""
    known = set(reference["quantities"])
    unknown = sorted((set(answers.quantities) | set(answers.review)) - known)
    if unknown:
        raise AnswersError(f"{reference['task_id']} has no quantity "
                           f"{', '.join(unknown)}")
    entry = reference["levels"][level]
    grader = _Grader(reference, level, answers)
    listed = level_quantities(entry)
    results = {name: grader.quantity(name) for name in listed}
    criteria = {name: grader.criterion(name, results)
                for name in entry.get("criteria", ())}
    found = {"level": level, "checkable": entry["checkable"],
             "partial": bool(entry.get("partial")), "quantities": results,
             "criteria": criteria}
    ignored = sorted(set(answers.quantities) - set(listed))
    if ignored:
        found["not_graded_at_this_level"] = ignored
    if not entry["checkable"]:
        return {**found, "verdict": NOT_CHECKABLE, "answers_verdict": NOT_CHECKABLE}
    answered = _complete_verdict(entry, results)
    outcomes = [c["status"] for c in criteria.values()]
    if FAIL in outcomes or answered == WRONG:
        verdict = WRONG
    elif SUSPECTED_FAIL in outcomes or answered == SUSPECTED:
        verdict = SUSPECTED
    elif (answered in RIGHT and not entry.get("partial")
          and any(s != PASS for s in outcomes)):
        verdict = UNKNOWN
    else:
        verdict = answered
    used = sorted({r["alternative"] for r in results.values() if "alternative" in r})
    if used:
        found["alternatives"] = used
    return {**found, "verdict": verdict, "answers_verdict": answered}
