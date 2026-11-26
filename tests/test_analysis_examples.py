"""The worked examples of docs/metrics.md, reproduced by the code of
analysis/ (T1.6). Inputs are the document's; expected values are its exact
fractions, or its decimals to four places."""

from fractions import Fraction as F

import pytest

from analysis import stability, stats, tables
from analysis.runs import NA, UND, Run, convert, coverage, ordered_pairs, read_values
from analysis.spec import Spec, Variable, load_spec
from runner.record import build_record

R = round


def r4(x):
    return round(float(x), 4)


@pytest.fixture(scope="module")
def spec():
    return load_spec("website")


# --- the example grid E1 ----------------------------------------------------------

S = frozenset
CORNER = {
    ("t1", "A"): ["rounded", "rounded", "rounded", "rounded", "pill"],
    ("t1", "B"): ["rounded", "rounded", None, "square", "rounded"],
    ("t2", "A"): ["very-rounded", "very-rounded", "rounded", "very-rounded", "rounded"],
    ("t2", "B"): ["rounded"],
}
TW, LU, RE = "tailwindcss", "lucide", "react"
LIBRARIES = {
    ("t1", "A"): [S({TW}), S({LU, TW}), S({TW}), S(), S({LU, TW})],
    ("t1", "B"): [S({TW}), S(), S({TW}), S(), S({TW})],
    ("t2", "A"): [S({RE, TW}), S({RE, TW}), S({TW}), S({RE}), S({TW})],
    ("t2", "B"): [S({TW})],
}
GRADIENT_RAW = {
    ("t1", "A"): [2, 3, 0, 1, 7],
    ("t1", "B"): [0, 0, 4, 0, 2],
    ("t2", "A"): [5, 2, 0, 6, 1],
    ("t2", "B"): [0],
}


def gradients(spec):
    var = spec.variables["website.gradients.gradient_count"]
    return {key: [convert(var, n) for n in values] for key, values in GRADIENT_RAW.items()}


# --- 1. Conversions ----------------------------------------------------------------


def test_1_conversions(spec):
    var = spec.variables["website.gradients.gradient_count"]
    assert var.bins == (0, 1, 3, 6)
    assert [convert(var, n) for n in (0, 1, 2, 3, 5, 6, 7)] == [
        "0", "1-2", "1-2", "3-5", "3-5", "6+", "6+"]
    assert coverage(0, 0) is NA
    assert coverage(0, 4) == "none"
    assert coverage(2, 4) == "some"
    assert coverage(4, 4) == "all"
    assert ordered_pairs(["header", "hero", "features", "footer"]) == S(
        {"^>header", "header>hero", "hero>features", "features>footer", "footer>$"})
    assert ordered_pairs([]) == S({"^>$"})
    counts = spec.variables["website.stock-phrases.stock_phrase_counts"]
    assert convert(counts, {"cta-get-started": 2, "cta-learn-more": 3,
                            "placeholder-lorem-ipsum": 1}) == S(
        {"cta-learn-more", "placeholder-lorem-ipsum"})


def _record(spec, libraries, corners):
    features = []
    for extractor in spec.extractor_versions:
        features.append({"name": "status", "value": "ok", "extractor": extractor,
                         "extractor_version": spec.extractor_versions[extractor]})
    features += [
        {"name": k, "value": v, "extractor": "website.libraries",
         "extractor_version": spec.extractor_versions["website.libraries"]}
        for k, v in libraries.items()] + [
        {"name": k, "value": v, "extractor": "website.corners-shadows",
         "extractor_version": spec.extractor_versions["website.corners-shadows"]}
        for k, v in corners.items()]
    return build_record(project_type="website", task_id="bakery-landing",
                        prompt_text="x", provider="example", model_id="m",
                        status="ok", raw_response="x", level="L0", wording="A",
                        run_index=1, prompt_set_version="1", features=features)


def test_1_mask(spec):
    bootstrap = read_values(_record(spec, {"css_framework": "bootstrap"},
                                    {"corner_style": "rounded"}), spec)
    assert bootstrap.values["website.corners-shadows.corner_style"] is UND
    assert bootstrap.values["website.libraries.css_framework"] == "bootstrap"
    assert bootstrap.masked
    tailwind = read_values(_record(spec, {"css_framework": "tailwindcss"},
                                   {"corner_style": "rounded"}), spec)
    assert tailwind.values["website.corners-shadows.corner_style"] == "rounded"
    assert not tailwind.masked
    # an undetermined condition masks the run; health rates are never masked
    unknown = read_values(_record(spec, {"css_framework": None},
                                  {"corner_style": "rounded"}), spec)
    assert unknown.values["website.corners-shadows.corner_style"] is UND
    assert unknown.masked


# --- 2. Outcomes ---------------------------------------------------------------------


def test_2_outcomes():
    groups = {("t1", "A"): ["artifact"] * 5, ("t1", "B"): ["artifact"] * 5,
              ("t2", "A"): ["artifact"] * 5,
              ("t2", "B"): ["artifact", "refused", "truncated", "no-artifact"]}
    p = stats.pool(groups)
    assert p.task_shares["t1"]["artifact"] == 1
    assert p.task_shares["t2"]["artifact"] == F(5, 8)
    for other in ("refused", "truncated", "no-artifact"):
        assert p.task_shares["t2"][other] == F(1, 8)
        assert p.shares[other] == F(1, 16)
    assert p.shares["artifact"] == F(13, 16)
    assert p.n == 19
    assert p.n_eff == F(320, 17)
    assert r4(p.n_eff) == 18.8235
    assert 1 - p.shares["artifact"] == F(3, 16)
    assert 1 - p.shares["artifact"] > stats.FLAG_SHARE      # incomplete outcomes


# --- 3. corner_style ------------------------------------------------------------------


def test_3_shares_weights_labels():
    p = stats.pool(CORNER)
    assert p.task_shares["t1"]["rounded"] == F(31, 40)
    assert p.task_shares["t1"]["pill"] == F(1, 10)
    assert p.task_shares["t1"]["square"] == F(1, 8)
    assert p.task_shares["t2"]["rounded"] == F(7, 10)
    assert p.task_shares["t2"]["very-rounded"] == F(3, 10)
    assert p.shares == {"rounded": F(59, 80), "very-rounded": F(3, 20),
                        "square": F(1, 16), "pill": F(1, 20)}
    assert r4(p.shares["rounded"]) == 0.7375
    assert sum(p.shares.values()) == 1
    assert (p.n, p.t) == (15, 2)
    assert p.n_eff == F(320, 33)
    assert r4(p.n_eff) == 9.6970
    intervals = {k: tuple(r4(x) for x in stats.wilson(v, p.n_eff))
                 for k, v in p.shares.items()}
    assert intervals == {"rounded": (0.4262, 0.9140), "very-rounded": (0.0347, 0.4639),
                         "square": (0.0077, 0.3656), "pill": (0.0051, 0.3503)}
    e = stats.evidence_single(p)
    assert (r4(e.x1), r4(e.x2)) == (7.1515, 1.4545)
    assert r4((e.x1 - e.x2) ** 2) == 32.4555
    assert r4(stats.Z2 * (e.x1 + e.x2)) == 33.0610
    assert not e.clear_lead
    n = float(p.n_eff)
    assert r4((2 * e.x1 - n) ** 2) == 21.2158
    assert r4(stats.Z2 * n) == 37.2519
    assert not e.majority
    assert e.label == "insufficient data"
    assert e.nominal_top == ("rounded",)
    assert e.reported is None


def test_3_undetermined_share_by_weight():
    states = {key: ["undetermined" if v is None else "value" for v in values]
              for key, values in CORNER.items()}
    p = stats.pool(states)
    assert p.n == 16
    assert p.shares["undetermined"] == F(1, 20)
    assert not p.shares["undetermined"] > stats.FLAG_SHARE   # not partly read


# --- 4. libraries ----------------------------------------------------------------------


def test_4_set_variable():
    p = stats.pool(LIBRARIES, is_set=True)
    assert p.shares == {TW: F(4, 5), RE: F(3, 20), LU: F(1, 10)}
    assert sum(p.shares.values()) != 1
    assert p.n == 16 and p.n_eff == 10
    rows, defaults = stats.default_items(p, labelled=False)
    assert rows[0][0] == TW and rows[0][2] is False       # 36 against 38.416: no
    assert (2 * 8 - 10) ** 2 == 36 and r4(stats.Z2 * 10) == 38.416
    assert defaults == ()
    assert stats.default_items(p)[1] == ()                 # insufficient data anyway


# --- 5. gradient_count -----------------------------------------------------------------


def test_5_number_variable(spec):
    groups = gradients(spec)
    t1a = stats.task_pool({("t1", "A"): groups[("t1", "A")]}, "t1")
    assert t1a.shares == {"0": F(1, 5), "1-2": F(2, 5), "3-5": F(1, 5), "6+": F(1, 5)}
    t1b = stats.task_pool({("t1", "B"): groups[("t1", "B")]}, "t1")
    assert t1b.shares == {"0": F(3, 5), "1-2": F(1, 5), "3-5": F(1, 5)}
    p = stats.pool(groups)
    assert p.shares == {"0": F(1, 2), "1-2": F(1, 4), "3-5": F(3, 20), "6+": F(1, 10)}
    assert p.n == 16 and p.n_eff == 10
    var = spec.variables["website.gradients.gradient_count"]
    e = stats.evidence_single(p, var.order_key)
    assert e.nominal_top == ("0",)
    assert (e.x1, e.x2) == (5.0, 2.5)
    assert (e.x1 - e.x2) ** 2 == 6.25 and r4(stats.Z2 * 7.5) == 28.812
    assert not e.clear_lead
    assert [k for k, _ in stats.ordered(p.shares, var.order_key)] == ["0", "1-2", "3-5", "6+"]


# --- 6. Missing data ---------------------------------------------------------------------


def test_6_one_run():
    assert stats.within(CORNER[("t2", "B")]) is None
    assert stats.shift(CORNER[("t2", "A")], CORNER[("t2", "B")]) is None
    assert stats.cross(CORNER[("t2", "A")], CORNER[("t2", "B")]) == F(2, 5)
    p = stats.pool({("t1", "A"): ["x"]})
    assert p.n_eff == 1
    e = stats.evidence_single(p, labelled=False)
    assert (e.x1, e.x2) == (1.0, 0.0) and not e.clear_lead and e.reported is None


def test_6_cell_with_no_value():
    groups = dict(CORNER)
    groups[("t2", "B")] = [None]
    p = stats.pool(groups)
    assert p.task_shares["t2"]["rounded"] == F(2, 5)
    assert p.shares == {"rounded": F(47, 80), "very-rounded": F(3, 10),
                        "square": F(1, 16), "pill": F(1, 20)}
    assert r4(p.shares["rounded"]) == 0.5875
    assert p.n_eff == F(64, 5) and p.n == 14


def test_6_all_missing():
    p = stats.pool({("t1", "A"): [None, None], ("t2", "A"): [None]})
    assert (p.n, p.t, p.shares) == (0, 0, {})
    assert stats.evidence_single(p).label == "insufficient data"
    assert stats.summarise({("t1", "v"): None}, {"v": "d"}, {"v"}).variables == {}


def test_6_tie():
    # three tasks, 20 effective runs: enough data for a label
    groups = {(t, w): ["a", "b"] * 2 for t in ("t1", "t2", "t3") for w in ("A", "B")}
    groups[("t1", "A")] = ["a", "b", "a", "b", "a", "b"]
    p = stats.pool(groups)
    assert p.shares == {"a": F(1, 2), "b": F(1, 2)}
    e = stats.evidence_single(p)
    assert e.nominal_top == ("a", "b") and e.x1 == e.x2
    assert not e.clear_lead
    assert e.label == "contested" and e.reported is None
    # at a thin n_eff the evidence is the same
    small = stats.evidence_single(stats.pool({("t1", "A"): ["b", "a"]}), labelled=False)
    assert small.nominal_top == ("a", "b") and not small.clear_lead and small.reported is None


# --- 7. E2 -------------------------------------------------------------------------------

E2_COUNTS = {"t1": ((5, 0, 0), (4, 1, 0)), "t2": ((4, 1, 0), (5, 0, 0)),
             "t3": ((3, 2, 0), (4, 0, 1)), "t4": ((5, 0, 0), (3, 1, 1)),
             "t5": ((1, 4, 0), (2, 3, 0)), "t6": ((4, 1, 0), (4, 0, 1))}


def e2_groups():
    out = {}
    for task, cells in E2_COUNTS.items():
        for wording, (i, b, n) in zip("AB", cells):
            out[(task, wording)] = ["indigo"] * i + ["blue"] * b + ["none"] * n
    return out


def test_7_e2_shares_intervals_labels():
    p = stats.pool(e2_groups())
    assert [p.task_shares[t]["indigo"] for t in sorted(E2_COUNTS)] == [
        F(9, 10), F(9, 10), F(7, 10), F(4, 5), F(3, 10), F(4, 5)]
    assert p.task_shares["t3"]["blue"] == F(1, 5)
    assert p.shares == {"indigo": F(11, 15), "blue": F(13, 60), "none": F(1, 20)}
    assert (r4(p.shares["indigo"]), r4(p.shares["blue"])) == (0.7333, 0.2167)
    assert (p.n, p.t, p.n_eff) == (60, 6, 60)
    run = {k: stats.wilson(v, p.n_eff) for k, v in p.shares.items()}
    assert tuple(map(r4, run["indigo"])) == (0.6099, 0.8287)
    assert tuple(map(r4, run["blue"])) == (0.1312, 0.3362)
    assert tuple(map(r4, run["none"])) == (0.0171, 0.1370)
    values = {k: [p.task_shares[t][k] for t in p.tasks] for k in p.shares}
    raw = stats.task_interval(values["indigo"])
    assert (r4(raw.mean), r4(raw.sd)) == (0.7333, 0.2251)
    assert r4(stats.t975(5) * raw.sd / 6 ** 0.5) == 0.2363
    indigo = stats.share_task_interval(values["indigo"], run["indigo"])
    assert (r4(indigo.low), r4(indigo.high)) == (0.4971, 0.9696)
    blue_raw = stats.task_interval(values["blue"])
    assert (r4(blue_raw.mean), r4(blue_raw.sd)) == (0.2167, 0.2401)
    assert (r4(blue_raw.low), r4(blue_raw.high)) == (-0.0354, 0.4687)
    blue = stats.share_task_interval(values["blue"], run["blue"])
    assert (r4(blue.low), r4(blue.high)) == (0, 0.4687)
    none_raw = stats.task_interval(values["none"])
    assert (r4(none_raw.mean), r4(none_raw.sd)) == (0.05, 0.0548)
    assert (r4(none_raw.low), r4(none_raw.high)) == (-0.0075, 0.1075)
    none = stats.share_task_interval(values["none"], run["none"])
    assert (r4(none.low), r4(none.high)) == (0, 0.1370)
    e = stats.evidence_single(p)
    assert (e.x1, R(e.x2, 9)) == (44.0, 13.0)
    assert R((88 - 60) ** 2) == 784 and r4(stats.Z2 * 60) == 230.496
    assert e.majority and not e.strong
    assert e.label == "default" and e.reported == "indigo"
    assert stats.task_support(p, "indigo") == 5
    assert stats.task_spread(p, "indigo") == F(3, 5)
    assert not stats.task_spread(p, "indigo") >= stats.TASK_DEPENDENT


def test_7_label_limits_at_60_runs():
    def lower(k):
        return r4(stats.wilson(F(k, 60), 60)[0])
    assert lower(37) == 0.4902 and not stats.majority(37, 60)
    assert lower(38) == 0.5068 and stats.majority(38, 60)
    assert lower(54) == 0.7985 and not stats.strong(F(54, 60), 60)
    assert lower(55) == 0.8193 and stats.strong(F(55, 60), 60)


# --- 8. Agreement and convergence ---------------------------------------------------------

DIMS = {"corner_style": "corners-shadows", "libraries": "libraries",
        "gradient_count": "gradients"}


def test_8_convergence(spec):
    assert stats.within(CORNER[("t1", "A")]) == F(3, 5) == F(12, 20)
    assert stats.within(LIBRARIES[("t1", "A")]) == F(2, 5)
    grads = gradients(spec)
    assert stats.within(grads[("t1", "A")]) == F(1, 10)
    assert stats.agreement(ordered_pairs(["header", "hero", "features", "footer"]),
                           ordered_pairs(["header", "hero", "pricing", "footer"])) == F(3, 7)
    data = {"corner_style": CORNER, "libraries": LIBRARIES, "gradient_count": grads}
    cells = {var: {key: stats.within(values) for key, values in groups.items()}
             for var, groups in data.items()}
    assert cells["corner_style"] == {("t1", "A"): F(3, 5), ("t1", "B"): F(1, 2),
                                     ("t2", "A"): F(2, 5), ("t2", "B"): None}
    assert cells["libraries"][("t1", "B")] == F(2, 5)
    assert cells["libraries"][("t2", "A")] == F(1, 2)
    assert cells["gradient_count"][("t1", "B")] == F(3, 10)
    per_task = {(t, var): stats.mean_defined([cells[var][(t, w)] for w in "AB"])
                for var in data for t in ("t1", "t2")}
    assert per_task[("t1", "corner_style")] == F(11, 20)
    assert per_task[("t2", "libraries")] == F(1, 2)
    assert per_task[("t1", "gradient_count")] == F(1, 5)
    out = stats.summarise(per_task, DIMS, set(DIMS))
    assert out.variables["corner_style"]["mean"] == F(19, 40)
    assert out.variables["libraries"]["mean"] == F(9, 20)
    assert out.variables["gradient_count"]["mean"] == F(3, 20)
    assert out.dimensions["corners-shadows"]["mean"] == F(19, 40)
    assert out.overall["tasks"] == {"t1": F(23, 60), "t2": F(1, 3)}
    assert out.overall["mean"] == F(43, 120) and r4(F(43, 120)) == 0.3583
    interval = out.overall["interval"]
    assert r4(interval.sd) == 0.0354
    # 0.31765 exactly: the document rounds half up to 0.3177
    assert abs(12.706 * interval.sd / 2 ** 0.5 - 0.3177) <= 0.00005 + 1e-12
    assert (r4(interval.low), r4(interval.high)) == (0.0407, 0.6760)


def test_8_convergence_e2():
    groups = e2_groups()
    per_task = {(t, "v"): stats.mean_defined([stats.within(groups[(t, w)]) for w in "AB"])
                for t in E2_COUNTS}
    assert stats.within(groups[("t3", "A")]) == F(2, 5)
    assert stats.within(groups[("t3", "B")]) == F(3, 5)
    assert [per_task[(t, "v")] for t in sorted(E2_COUNTS)] == [
        F(4, 5), F(4, 5), F(1, 2), F(13, 20), F(1, 2), F(3, 5)]
    out = stats.summarise(per_task, {"v": "d"}, {"v"})
    block = out.variables["v"]
    assert r4(block["mean"]) == 0.6417 and r4(block["interval"].sd) == 0.1357
    assert (r4(block["interval"].low), r4(block["interval"].high)) == (0.4992, 0.7841)


# --- 9. Shift ---------------------------------------------------------------------------

L2A = ["square"] * 4 + ["rounded"]
L2B = ["square"] * 5


def test_9_shift():
    a0, b0 = CORNER[("t1", "A")], CORNER[("t1", "B")]
    assert [stats.within(x) for x in (a0, b0, L2A, L2B)] == [F(3, 5), F(1, 2), F(3, 5), 1]
    assert stats.cross(a0, b0) == F(3, 5)
    sw0 = stats.shift(a0, b0)
    assert sw0 == F(-1, 20)
    assert stats.cross(L2A, L2B) == F(4, 5)
    sw2 = stats.shift(L2A, L2B)
    assert sw2 == 0
    assert stats.cross(a0, L2A) == F(4, 25)
    shift_a, shift_b = stats.shift(a0, L2A), stats.shift(b0, L2B)
    assert (shift_a, shift_b) == (F(11, 25), F(1, 2))
    s = tables.level_shift([(a0, L2A), (b0, L2B)])
    assert s == F(47, 100)
    assert tables.excess(s, sw0, sw2) == F(99, 200) == F(47, 100) + F(1, 40)
    assert r4(F(99, 200)) == 0.495
    assert tables.excess(s, None, sw2) is None        # E needs all three shifts


def test_9_set_wording_shift():
    a, b = LIBRARIES[("t1", "A")], LIBRARIES[("t1", "B")]
    assert stats.within(b) == F(2, 5)
    assert stats.cross(a, b) == F(11, 25)
    assert stats.shift(a, b) == F(-1, 25)


def test_9_e2_wording_shift_and_moved():
    groups = e2_groups()
    values = [stats.shift(groups[(t, "A")], groups[(t, "B")]) for t in sorted(E2_COUNTS)]
    assert values == [0, 0, F(1, 50), F(1, 20), F(-3, 50), F(-1, 25)]
    interval = stats.task_interval(values)
    assert (r4(interval.mean), r4(interval.sd)) == (-0.0050, 0.0399)
    assert (r4(interval.low), r4(interval.high)) == (-0.0469, 0.0369)
    assert stats.shift(CORNER[("t2", "A")], CORNER[("t2", "B")]) is None
    moved = stats.task_interval([F(3, 10), F(1, 10), F(1, 4), F(1, 20), F(1, 5), F(3, 10)])
    assert (r4(moved.mean), r4(moved.sd)) == (0.2, 0.1049)
    assert r4(2.571 * moved.sd / 6 ** 0.5) == 0.1101
    assert (r4(moved.low), r4(moved.high)) == (0.0899, 0.3101) and moved.low > 0
    not_shown = stats.task_interval([F(1, 2), F(-1, 20), 0, F(3, 5), F(-1, 10), F(1, 4)])
    assert (r4(not_shown.mean), r4(not_shown.sd)) == (0.2, 0.2983)
    assert (r4(not_shown.low), r4(not_shown.high)) == (-0.1131, 0.5131)


# --- 10. Compliance and persistence ------------------------------------------------------


def corner_var(spec):
    return spec.variables["website.corners-shadows.corner_style"]


def test_10_compliance_and_persistence(spec):
    var = corner_var(spec)
    expect = tables.Expect(in_=("square",))
    l0 = stats.task_pool({k: v for k, v in CORNER.items() if k[0] == "t1"}, "t1")
    assert l0.shares == {"rounded": F(31, 40), "square": F(1, 8), "pill": F(1, 10)}
    assert l0.n_eff == F(80, 9) and r4(l0.n_eff) == 8.8889
    e = stats.evidence_single(l0, var.order_key, labelled=False)
    assert (r4(e.x1), r4(e.x2)) == (6.8889, 1.1111)
    assert r4((e.x1 - e.x2) ** 2) == 33.3827 and r4(stats.Z2 * 8) == 30.7328
    assert e.clear_lead
    assert tables.l0_default(var, expect, l0) == "rounded"
    l2 = {("t1", "A"): L2A, ("t1", "B"): L2B}
    table = stats.task_pool(l2, "t1")
    assert table.shares == {"square": F(9, 10), "rounded": F(1, 10)} and table.n_eff == 10
    compliance = tables.compliance(var, {"t1": expect}, l2)
    assert compliance["share"] == F(9, 10)
    assert tuple(map(r4, compliance["run_interval"])) == (0.5958, 0.9821)
    assert compliance["no_verdict"] == 0
    persistence = tables.persistence(var, {"t1": expect}, {"t1": l0}, l2)
    assert persistence["share"] == F(1, 10)
    assert tuple(map(r4, persistence["run_interval"])) == (0.0179, 0.4042)
    assert persistence["reading"] == "undecided"
    # not read when the brief asks for the default, or without a clear lead
    assert tables.l0_default(var, tables.Expect(in_=("square", "rounded")), l0) is None
    flat = stats.task_pool({("t1", "A"): ["rounded", "square"]}, "t1")
    assert tables.l0_default(var, expect, flat) is None
    assert tables.persistence(var, {"t1": tables.Expect(in_=("square", "rounded"))},
                              {"t1": l0}, l2) is None


def test_10_readings():
    assert tables.reading((0.11, 0.3)) == "persists"
    assert tables.reading((0.0, 0.0989)) == "gave way"
    assert tables.reading((0.0179, 0.4042)) == "undecided"
    # none in 34 runs leaves 0.1015, none in 35 gives 0.0989
    assert r4(stats.wilson(0, 34)[1]) == 0.1015 and r4(stats.wilson(0, 35)[1]) == 0.0989
    assert r4(stats.wilson(0, 10)[1]) == 0.2775          # "0 of 10 leaves 0.28"


def test_10_set_compliance(spec):
    var = spec.variables["website.fonts.font_sources"]
    cell = {("t1", "A"): [S({"google-fonts"}), S(), S(), S({"self-hosted"}), S()]}
    absent = tables.Expect(absent=("google-fonts", "bunny-fonts"))
    assert tables.compliance(var, {"t1": absent}, cell)["share"] == F(4, 5)
    present = tables.Expect(present=("self-hosted",))
    assert tables.compliance(var, {"t1": present}, cell)["share"] == F(1, 5)
    assert tables.persistence(var, {"t1": absent}, {}, cell) is None


def test_10_no_verdict(spec):
    var = spec.variables["website.fonts.heading_category"]
    assert "unknown" in var.no_verdict
    expect = tables.Expect(in_=("sans", "display"))
    cell = {("t1", "A"): ["sans", "display", "unknown", "serif", "sans"]}
    result = tables.compliance(var, {"t1": expect}, cell)
    assert result["share"] == F(3, 4) and result["no_verdict"] == 1
    expect_same = tables.Expect(in_=("sans", "display"), no_verdict=frozenset({"same"}))
    cell = {("t1", "A"): ["sans", "same", "unknown", "serif", "same"]}
    result = tables.compliance(var, {"t1": expect_same}, cell)
    assert result["share"] == F(1, 2) and result["no_verdict"] == 3


# --- 11. Two models ----------------------------------------------------------------------


def test_11_two_models():
    m1 = CORNER[("t1", "A")]
    m2 = ["pill", "pill", "pill", "rounded", "rounded"]
    assert (stats.within(m1), stats.within(m2)) == (F(3, 5), F(2, 5))
    assert stats.cross(m1, m2) == F(11, 25)
    assert stats.shift(m1, m2) == F(3, 50) and float(F(3, 50)) == 0.06
    assert ((F(4, 5) - F(2, 5)) ** 2 + (F(1, 5) - F(3, 5)) ** 2) / 2 == F(4, 25)


# --- 12. The stability rule ---------------------------------------------------------------


def counted_groups(counts, runs_per_cell):
    """Complete cells of 3 tasks x 2 wordings from ``{choice: count}``."""
    values = [k for k, n in counts.items() for _ in range(n)]
    cells = [(t, w) for t in ("t1", "t2", "t3") for w in "AB"]
    assert len(values) == runs_per_cell * len(cells)
    return {cell: values[i * runs_per_cell:(i + 1) * runs_per_cell]
            for i, cell in enumerate(cells)}


def set_groups(counts, total, runs_per_cell):
    values = [S(k for k, n in counts.items() if i < n) for i in range(total)]
    cells = [(t, w) for t in ("t1", "t2", "t3") for w in "AB"]
    return {cell: values[i * runs_per_cell:(i + 1) * runs_per_cell]
            for i, cell in enumerate(cells)}


V = {name: Variable(name=name, extractor="x", feature=name, type="categorical",
                    role="primary", dimension="d") for name in ("v1", "v2", "v3", "v4", "v5")}
V["v6"] = Variable(name="v6", extractor="x", feature="v6", type="set", role="primary",
                   dimension="d")

F5 = {"v1": {"a": 24, "b": 6}, "v2": {"a": 17, "b": 13}, "v3": {"a": 22, "b": 8},
      "v4": {"a": 15, "b": 15}, "v5": {"a": 22, "b": 8}}
F10 = {"v1": {"a": 45, "b": 15}, "v2": {"a": 40, "b": 20}, "v3": {"a": 29, "b": 31},
       "v4": {"a": 29, "b": 31}, "v5": {"a": 35, "b": 25}}
SET5 = {TW: 26, LU: 19, RE: 6}
SET10 = {TW: 50, LU: 40, RE: 13}


def table(counts, set_counts, per_cell):
    out = {}
    for name, c in counts.items():
        out[name] = stability.variable_report(V[name], stats.pool(counted_groups(c, per_cell)))
    out["v6"] = stability.variable_report(
        V["v6"], stats.pool(set_groups(set_counts, 6 * per_cell, per_cell), is_set=True))
    return out


def test_12_stability():
    f5, f10 = table(F5, SET5, 5), table(F10, SET10, 10)
    assert f5["v1"].reported == "a" and f10["v1"].reported == "a"
    assert f5["v2"].reported is None and f10["v2"].reported == "a"
    assert f5["v3"].reported == "a" and f10["v3"].reported is None
    assert f10["v3"].nominal_top == ("b",)
    assert f5["v4"].reported is None and f10["v4"].reported is None
    assert f5["v5"].reported == "a" and f10["v5"].reported is None
    assert f5["v6"].default_set == (TW,) and f10["v6"].default_set == (LU, TW)
    result = stability.compare(f5, f10)
    assert result.counted == ["v1", "v2", "v3", "v5", "v6"]
    assert result.credits == {"v1": 1, "v2": 0, "v3": 0, "v5": 0, "v6": F(1, 2)}
    assert result.score == F(3, 10)
    assert result.reversals == 1
    kinds = {c["variable"]: c["kind"] for c in result.changes}
    assert kinds == {"v2": "new", "v3": "reversed", "v5": "lost", "v6": "changed"}
    assert result.kinds["kept"] == 1
    assert (result.e_small, result.e_big) == (4, 4)
    assert result.growth == 0
    assert stability.verdict(result) == "unstable: contested choices"
    v6 = next(c for c in result.changes if c["variable"] == "v6")
    assert v6["gained"] == [LU] and v6["dropped"] == []


def test_12_variants():
    kept = dict(F10, v5={"a": 45, "b": 15})       # v5 keeps an established majority
    result = stability.compare(table(F5, SET5, 5), table(kept, SET10, 10))
    assert result.e_big == 5 and result.growth == F(1, 4)
    assert stability.verdict(result) == "unstable: defaults still appearing"
    flipped = dict(F10, v5={"a": 25, "b": 35})    # v5 ends with b on top
    result = stability.compare(table(F5, SET5, 5), table(flipped, SET10, 10))
    assert result.reversals == 2
    assert stability.verdict(result) == "drift suspected"
    assert stability.growth(0, 0) == 0
    assert stability.growth(0, 3) == float("inf")


def test_12_read_as_the_repeat():
    result = stability.compare(table(F5, SET5, 5), table(F10, SET10, 10))
    verdict = stability.verdict(result)
    assert verdict == "unstable: contested choices"
    assert "10 runs per cell stand" in stability.consequence(verdict, repeat=True)
    assert "5 runs per cell stand" in stability.consequence(verdict, repeat=False)


def test_12_ties_and_set_halves():
    tie_small = {"v1": {"a": 15, "b": 15}}
    big = {"v1": {"a": 45, "b": 15}}
    small_tab = {"v1": stability.variable_report(V["v1"], stats.pool(counted_groups(tie_small["v1"], 5)))}
    big_tab = {"v1": stability.variable_report(V["v1"], stats.pool(counted_groups(big["v1"], 10)))}
    assert stability.compare(small_tab, big_tab).kinds["new"] == 1   # a tie in F5 claims nothing
    # a tie in F10 that includes F5's choice is lost, not a reversal
    small_tab = {"v1": stability.variable_report(V["v1"], stats.pool(counted_groups({"a": 24, "b": 6}, 5)))}
    big_tab = {"v1": stability.variable_report(V["v1"], stats.pool(counted_groups({"a": 30, "b": 30}, 10)))}
    result = stability.compare(small_tab, big_tab)
    assert result.reversals == 0 and result.kinds["lost"] == 1
    # a set item held by exactly half of the runs in F10 is not a reversal
    small_set = {"v6": stability.variable_report(
        V["v6"], stats.pool(set_groups({TW: 30}, 30, 5), is_set=True))}
    big_set = {"v6": stability.variable_report(
        V["v6"], stats.pool(set_groups({TW: 30}, 60, 10), is_set=True))}
    assert big_set["v6"].shares[TW] == F(1, 2)
    assert stability.compare(small_set, big_set).reversals == 0
    big_set = {"v6": stability.variable_report(
        V["v6"], stats.pool(set_groups({TW: 29}, 60, 10), is_set=True))}
    assert stability.compare(small_set, big_set).reversals == 1
    nothing = stability.compare({}, {})
    assert stability.verdict(nothing) == "no defaults"


# --- 13. Representative output -------------------------------------------------------------


def e1_runs(spec):
    grads = gradients(spec)
    runs = []
    for wording in "AB":
        for index in range(5):
            values = {
                "corner_style": CORNER[("t1", wording)][index],
                "libraries": LIBRARIES[("t1", wording)][index],
                "gradient_count": grads[("t1", wording)][index]}
            runs.append(Run(
                record_id=f"r-{wording}{index + 1}", model="m", task="t1", level="L0",
                wording=wording, run_index=index + 1, timestamp="", batch_id="b",
                model_id_returned=None, settings="{}", outcome="artifact",
                values={k: (UND if v is None else v) for k, v in values.items()}))
    return runs


def test_13_representative_output(spec):
    runs = e1_runs(spec)
    ranking = tables.typicality(runs, list(DIMS), DIMS)
    by_id = {entry["run"].record_id: entry for entry in ranking}
    a1 = by_id["r-A1"]
    assert a1["variables"] == {"corner_style": F(3, 4), "libraries": F(5, 9),
                               "gradient_count": F(2, 9)}
    assert a1["typicality"] == F(55, 108) and r4(F(55, 108)) == 0.5093
    expected = {"A1": F(55, 108), "A2": F(5, 12), "A3": F(59, 108), "A4": F(43, 108),
                "A5": F(7, 54), "B1": F(59, 108), "B2": F(47, 108), "B3": F(1, 3),
                "B4": F(5, 27), "B5": F(55, 108)}
    assert {k[2:]: v["typicality"] for k, v in by_id.items()} == expected
    assert by_id["r-A2"]["variables"]["libraries"] == F(7, 18)
    assert by_id["r-B3"]["variables"] == {"libraries": F(5, 9), "gradient_count": F(1, 9)}
    chosen = tables.representative(runs, list(DIMS), DIMS)
    assert chosen["representative"] == "r-A3"
    assert [e["record_id"] for e in chosen["most_typical"]] == ["r-A3", "r-B1", "r-A1"]
    assert chosen["least_typical"]["record_id"] == "r-A5"
    assert tables.representative(runs[:2], list(DIMS), DIMS) is None


# --- 14. Closed by dependence -------------------------------------------------------------


def chain_spec(listed):
    variables = {
        "x.a": Variable("x.a", "x", "a", "categorical", "primary", "d"),
        "x.b": Variable("x.b", "x", "b", "categorical", "primary", "d", depends_on=("x.a",)),
        "x.c": Variable("x.c", "x", "c", "categorical", "primary", "d", depends_on=("x.b",)),
    }
    tasks = {"t": {"prompt_set_version": "1", "L2": [{"closed": [listed]}]}}
    return Spec("x", "1", {}, {"x": "d"}, variables, (), tasks)


def test_14_chain():
    assert chain_spec("x.a").closed("t", "L2") == {"x.a": None, "x.b": "x.a", "x.c": "x.b"}
    assert chain_spec("x.b").closed("t", "L2") == {"x.b": None, "x.c": "x.b"}
    assert chain_spec("x.c").closed("t", "L2") == {"x.c": None}


DEPENDENCE_ALONE = {
    "bakery-landing": {"website.fonts.font_sources", "website.fonts.system_stack",
                       "website.dark-mode.mechanisms"},
    "pricing-page": {"website.dark-mode.mechanisms"},
    "portfolio": {"website.gradients.gradient_hues", "website.libraries.libraries",
                  "website.dark-mode.mechanisms"},
    "event-page": {"website.gradients.gradient_hues", "website.libraries.libraries",
                   "website.dark-mode.mechanisms"},
    "todo-app": {"website.fonts.font_sources", "website.fonts.system_stack",
                 "website.dark-mode.mechanisms"},
    "dashboard": {"website.gradients.gradient_hues",
                  "website.responsiveness.tailwind_breakpoints",
                  "website.dark-mode.mechanisms"},
}


def test_14_closed_by_dependence_alone(spec):
    for task, expected in DEPENDENCE_ALONE.items():
        closed = spec.closed(task, "L2")
        alone = {name for name, closer in closed.items() if closer is not None
                 and spec.variables[name].role in ("primary", "provisional")}
        assert alone == expected, task
        assert not spec.closed(task, "L0") and not spec.closed(task, "L1")
    closed = spec.closed("bakery-landing", "L2")
    assert closed["website.dark-mode.mechanisms"] == "website.dark-mode.dark_mode"
    assert closed["website.dark-mode.dark_mode"] is None


# the table "What stays open at L2" under Open choices
OPEN_AT_L2 = {
    "palette": {},
    "fonts": {"primary_font": 3, "heading_font": 1, "system_stack": 1},
    "libraries": {"libraries": 3, "framework": 5, "css_framework": 5, "delivery": 5},
    "layout": {"landmarks": 6, "layout_systems": 6, "grid_columns": 4, "nav_position": 6},
    "corners-shadows": {"corner_style": 1, "pill_shapes": 1, "shadow_count": 1,
                        "shadow_kinds": 1, "text_shadow": 2, "backdrop_blur": 3},
    "gradients": {"gradient_count": 3, "gradient_types": 3, "gradient_directions": 3,
                  "gradient_text": 3},
    "icons-emoji": {"icon_kinds": 3, "icon_libraries": 3, "emoji_count": 3, "favicon": 6},
    "copy": {},
    "file-structure": {"structure": 6, "file_count": 6, "inline_style_blocks": 6,
                       "inline_script_blocks": 6, "style_attributes": 6, "has_readme": 6},
    "responsiveness": {"viewport_meta": 6, "media_query_style": 6, "breakpoints_px": 6,
                       "tailwind_breakpoints": 5, "fluid_techniques": 6,
                       "responsive_images": 6},
    "dark-mode": {},
    "accessibility": {name: 6 for name in (
        "html_lang", "alt_coverage", "h1_count", "heading_skips", "main_landmark",
        "skip_link", "buttons_without_name", "generic_link_text", "aria_attributes",
        "focus_styles", "outline_removed", "reduced_motion", "unlabelled")},
}


def test_open_at_l2_table(spec):
    found = {dim: {} for dim in OPEN_AT_L2}
    for name, var in spec.variables.items():
        if var.role != "primary":
            continue
        count = sum(spec.is_open(task, "L2", name) for task in spec.tasks)
        if count:
            found[var.dimension][var.feature] = count
    assert found == OPEN_AT_L2
