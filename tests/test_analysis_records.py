"""analysis/ on run records (T1.6): which records count, outcomes, refusals,
and an end-to-end run of both commands on synthetic records built with
runner/record.py."""

import json
import uuid
from fractions import Fraction as F

import pytest

from analysis import __main__ as cli
from analysis import stability, tables
from analysis.runs import Refused, select, select_files
from analysis.spec import load_spec
from runner.record import build_record, write_records

TASKS = ("bakery-landing", "pricing-page", "portfolio", "event-page", "todo-app", "dashboard")
CORNER = "website.corners-shadows.corner_style"
NAV = "website.layout.nav_position"


@pytest.fixture(scope="module")
def spec():
    return load_spec("website")


def feature_list(spec, values, statuses=None, versions=None):
    """Features for every website extractor: status ok unless ``statuses``
    says otherwise, plus ``values`` ({variable: stored value})."""
    statuses = statuses or {}
    versions = versions or {}
    out = []
    for extractor, version in spec.extractor_versions.items():
        version = versions.get(extractor, version)
        out.append({"name": "status", "value": statuses.get(extractor, "ok"),
                    "extractor": extractor, "extractor_version": version})
        for name, value in values.items():
            ext, feature = name.rsplit(".", 1)
            if ext == extractor:
                out.append({"name": feature, "value": value, "extractor": extractor,
                            "extractor_version": version})
    return out


COUNTER = {"n": 0}


def make(spec, task="bakery-landing", level="L0", wording="A", run_index=1, model="m1",
         status="ok", values=None, statuses=None, versions=None, extract=True,
         timestamp=None, settings=None, batch="b1", returned=None, prompt_set="1",
         **extra):
    COUNTER["n"] += 1
    n = COUNTER["n"]
    base = {"website.file-structure.structure": "single-html",
            "website.libraries.css_framework": "tailwindcss"}
    base.update(values or {})
    features = feature_list(spec, base, statuses, versions) if extract and status in (
        "ok", "truncated") else []
    return build_record(
        project_type="website", task_id=task, prompt_text="p", provider="example",
        model_id=model, status=status, level=level, wording=wording, run_index=run_index,
        prompt_set_version=prompt_set, batch_id=batch,
        raw_response="x" if status != "failed" else None,
        error="boom" if status == "failed" else None,
        settings={"max_tokens": 100} if settings is None else settings,
        timestamp=timestamp or f"2026-12-01T00:{n // 60 % 60:02d}:{n % 60:02d}.000Z",
        record_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"sibar-test-{n}")),
        model_id_returned=returned, features=features, **extra)


# --- which records count ------------------------------------------------------------


def test_first_non_failed_record_by_timestamp(spec):
    late_ok = make(spec, timestamp="2026-12-01T10:00:00Z", values={CORNER: "square"})
    early_fail = make(spec, status="failed", timestamp="2026-12-01T09:00:00Z")
    refusal = make(spec, run_index=2, status="refused", timestamp="2026-12-01T09:00:00Z")
    rerun = make(spec, run_index=2, timestamp="2026-12-01T11:00:00Z")
    only_failed = make(spec, run_index=3, status="failed")
    runs = select([late_ok, early_fail, rerun, refusal, only_failed], spec, ["b1"]).runs
    assert [(r.run_index, r.outcome) for r in runs] == [(1, "artifact"), (2, "refused")]
    assert runs[0].values[CORNER] == "square"


def test_outcomes(spec):
    records = [
        make(spec, run_index=1),
        make(spec, run_index=2, values={"website.file-structure.structure": "no-html"}),
        make(spec, run_index=3, statuses={"website.file-structure": "no-input"}),
        make(spec, run_index=4, statuses={"website.file-structure": "error"}),
        make(spec, run_index=5, status="truncated"),
        make(spec, run_index=6, status="refused"),
    ]
    runs = select(records, spec, ["b1"]).runs
    assert [r.outcome for r in runs] == ["artifact", "no-artifact", "no-artifact", "unread",
                                         "truncated", "refused"]


def test_other_batches_and_sources_are_left_out(spec):
    records = [make(spec), make(spec, run_index=2, batch="other"),
               make(spec, run_index=3, source="manual", surface="product")]
    selection = select(records, spec, ["b1"])
    assert [r.run_index for r in selection.runs] == [1]
    assert any("not controlled API runs" in note for note in selection.notes)


@pytest.mark.parametrize("case, message", [
    ({"versions": {"website.palette": "5"}}, "at version 5"),
    ({"prompt_set": "2"}, "prompt_set_version"),
    ({"values": {"website.palette.made_up": 1}}, "not declared"),
    ({"values": {"website.gradients.gradient_count": -1}}, "below its first bin edge"),
    ({"values": {"website.gradients.gradient_count": "many"}}, "not a whole number"),
    ({"task": "unknown-task"}, "not in dictated.yaml"),
])
def test_refusals(spec, case, message):
    with pytest.raises(Refused, match=message):
        select([make(spec, **case)], spec, ["b1"])


def test_refuses_a_usable_run_missing_an_extractor(spec):
    record = make(spec)
    record["extractors"] = [e for e in record["extractors"]
                            if e["extractor"] != "website.gradients"]
    record["features"] = [f for f in record["features"]
                          if f["extractor"] != "website.gradients"]
    with pytest.raises(Refused, match="has not run on it"):
        select([record], spec, ["b1"])


def test_refuses_mixed_settings_within_a_model(spec):
    records = [make(spec), make(spec, run_index=2, settings={"max_tokens": 200})]
    with pytest.raises(Refused, match="settings"):
        select(records, spec, ["b1"])
    other_model = make(spec, run_index=2, model="m2", settings={"max_tokens": 200})
    assert len(select([records[0], other_model], spec, ["b1"]).runs) == 2


def test_refused_and_truncated_records_need_no_current_extractors(spec):
    old = make(spec, status="truncated", versions={"website.palette": "1"})
    assert select([old], spec, ["b1"]).runs[0].outcome == "truncated"


def test_undetermined_states_and_masks(spec):
    run = select([make(spec, values={CORNER: "rounded",
                                     "website.libraries.css_framework": "bootstrap",
                                     "website.gradients.gradient_types": [],
                                     "website.gradients.gradient_count": 0},
                       statuses={"website.fonts": "error"})], spec, ["b1"]).runs[0]
    assert run.value(CORNER) is None                     # masked
    assert run.health["masked"] is True
    assert run.value("website.fonts.primary_font") is None   # extractor error
    assert run.value("website.gradients.gradient_count") == "0"
    assert repr(run.values["website.gradients.gradient_types"]) == "not applicable"
    assert run.value("website.layout.landmarks") is None     # missing: undetermined


def test_real_extractor_output_converts(spec):
    """Features from the real website extractors on fixture pages convert
    without refusal; the Bootstrap page is masked."""
    from pathlib import Path

    from extractors.base import Inputs, run_extractors
    from extractors.registry import extractors_for
    from runner.record import with_features
    fixtures = Path(__file__).resolve().parent / "fixtures" / "website"
    records = []
    for index, page in enumerate(("tailwind-landing", "bootstrap", "negative",
                                  "react-components"), start=1):
        record = make(spec, run_index=index, extract=False)
        results = run_extractors(extractors_for("website"),
                                 Inputs.from_directory(fixtures / page))
        for name, (version, values) in results.items():
            record = with_features(record, name, version, values)
        records.append(record)
    runs = select(records, spec, ["b1"]).runs
    assert all(run.usable for run in runs)
    by_index = {run.run_index: run for run in runs}
    assert by_index[1].value("website.libraries.css_framework") == "tailwindcss"
    assert by_index[1].value(CORNER) is not None and not by_index[1].masked
    assert by_index[2].masked and by_index[2].value(CORNER) is None
    assert by_index[2].value("website.libraries.css_framework") not in (None, "none",
                                                                        "tailwindcss")
    for run in runs:
        typed = [run.value(n) for n, v in spec.variables.items() if v.role != "diagnostic"]
        assert any(value is not None for value in typed)


# --- end to end ----------------------------------------------------------------------


def corner_value(model, level, wording, index):
    if model == "m2":
        return "square"
    if level == "L2":
        return "square" if index <= 4 else "rounded"
    return "pill" if (wording == "B" and index == 5) else "rounded"


def grid_records(spec):
    records = []
    for model in ("m1", "m2"):
        for task in TASKS:
            for level in ("L0", "L1", "L2"):
                for wording in "AB":
                    for index in range(1, 6):
                        special = (model, task, level, wording) == ("m1", "bakery-landing",
                                                                    "L0", "B")
                        values = {CORNER: corner_value(model, level, wording, index),
                                  NAV: "sticky-top",
                                  "website.libraries.libraries": ["tailwindcss"]
                                  + (["lucide"] if index % 2 else []),
                                  "website.gradients.gradient_count": index - 1}
                        if special and index == 2:
                            records.append(make(spec, task, level, wording, index, model,
                                                status="refused"))
                        elif special and index == 3:
                            records.append(make(spec, task, level, wording, index, model,
                                                status="truncated"))
                        elif special and index == 4:
                            records.append(make(spec, task, level, wording, index, model,
                                                status="failed"))
                            records.append(make(spec, task, level, wording, index, model,
                                                values=values, returned="m1-2026"))
                        elif special and index == 5:
                            records.append(make(spec, task, level, wording, index, model,
                                                values={"website.file-structure.structure":
                                                        "no-html"}))
                        else:
                            records.append(make(spec, task, level, wording, index, model,
                                                values=values, returned=f"{model}-2025"))
    return records


@pytest.fixture(scope="module")
def grid_file(spec, tmp_path_factory):
    path = tmp_path_factory.mktemp("grid") / "records.jsonl"
    write_records(path, grid_records(spec))
    return path


def test_tables_end_to_end(spec, grid_file, tmp_path):
    lines = []
    status = cli.main(["tables", "--records", str(grid_file), "--batch", "b1",
                       "--out", str(tmp_path)], out=lines.append)
    assert status == 0, lines
    data = json.loads((tmp_path / "website-tables.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "website-tables.md").read_text(encoding="utf-8")
    assert "# Fingerprints: website" in markdown and "corner_style" in markdown
    assert data["metrics_version"] == "1" and data["batch_group"] == ["b1"]
    assert data["extractor_versions"] == spec.extractor_versions
    fp = data["models"]["m1"]["levels"]["L0"]["fingerprint"]
    outcomes = fp["outcomes"]
    assert outcomes["counts"] == {"artifact": 57, "no-artifact": 1, "unread": 0,
                                  "truncated": 1, "refused": 1}
    # bakery-landing B: five selected records (the failed attempt is not one),
    # two of them artifacts: (5 + (1 + 2/5) / 2) / 6
    assert outcomes["shares"]["artifact"]["fraction"] == str(F(19, 20))
    assert not outcomes["incomplete_outcomes"]
    assert "mixed snapshots" in fp["flags"]
    assert fp["dates"] == ["2026-12-01", "2026-12-01"]
    rows = {row["variable"]: row for row in fp["variables"]}
    corner = rows[CORNER]
    assert corner["T"] == 6 and corner["reported"] == "rounded"
    assert corner["label"] in ("default", "strong default")
    assert corner["holds_across_tasks"] is True
    nav = rows[NAV]
    assert nav["label"] == "strong default" and nav["task_support"] == [6, 6]
    libraries = rows["website.libraries.libraries"]
    assert libraries["default_set"] == ["tailwindcss"]
    assert rows["website.layout.landmarks"]["N"] == 0
    assert rows["website.layout.landmarks"]["label"] == "insufficient data"
    assert "partly read" in rows["website.layout.landmarks"]["flags"]
    reps = fp["representative_outputs"]
    assert set(reps) == set(TASKS) and all(rep is not None for rep in reps.values())
    # L2: palette closed everywhere; corner style open in one task only
    l2 = {row["variable"]: row for row in
          data["models"]["m1"]["levels"]["L2"]["fingerprint"]["variables"]}
    assert l2["website.palette.dominant_hue"]["label"] == "closed in every task"
    assert l2[CORNER]["open_tasks"] == ["event-page"]
    assert l2[CORNER]["label"] == "insufficient data"
    pooled = data["models"]["m1"]["levels"]["L2"]["directed"]["pooled"][CORNER]
    assert pooled["compliance"]["share"]["fraction"] == "4/5"
    assert pooled["persistence"]["share"]["fraction"] == "1/5"
    assert pooled["persistence"]["defaults"] == {
        t: "rounded" for t in ("bakery-landing", "dashboard", "pricing-page", "todo-app")}
    entries = data["models"]["m1"]["levels"]["L2"]["directed"]["entries"]
    mechanisms = [e for e in entries if e["variable"] == "website.dark-mode.mechanisms"]
    assert mechanisms and all(e["closed_by"] == "dependent"
                              and e["closer"] == "website.dark-mode.dark_mode"
                              for e in mechanisms)
    # convergence: nav_position is unanimous everywhere
    conv = data["models"]["m1"]["levels"]["L0"]["convergence"]
    assert conv["variables"][NAV]["mean"]["fraction"] == "1"
    sens = data["models"]["m1"]["sensitivity"]
    assert [(s["from"], s["to"]) for s in sens] == [("L0", "L1"), ("L1", "L2"), ("L0", "L2")]
    # spill-over L0 to L2: corner style is open at both levels in event-page only
    assert set(sens[2]["shift"]["variables"][CORNER]["tasks"]) == {"event-page"}
    assert "bakery-landing" in sens[0]["associations"]
    comparison = data["model_comparisons"][0]
    assert comparison["models"] == ["m1", "m2"]
    d = comparison["pairs"][0]["model_shift"]["variables"][CORNER]
    assert float(d["mean"]["decimal"]) > 0.5
    assert comparison["shared_defaults"][NAV] == ["sticky-top"]
    assert CORNER not in comparison["shared_defaults"]


def test_tables_output_is_deterministic(grid_file, tmp_path):
    for name in ("one", "two"):
        assert cli.main(["tables", "--records", str(grid_file), "--batch", "b1",
                         "--out", str(tmp_path / name)], out=lambda *_: None) == 0
    for suffix in (".json", ".md"):
        assert (tmp_path / "one" / f"website-tables{suffix}").read_bytes() == \
            (tmp_path / "two" / f"website-tables{suffix}").read_bytes()


def test_tables_refuses_an_unknown_batch(grid_file, tmp_path):
    lines = []
    assert cli.main(["tables", "--records", str(grid_file), "--batch", "nope",
                     "--out", str(tmp_path)], out=lines.append) == 2
    assert lines[-1].startswith("refused:")


# --- the stability check ---------------------------------------------------------------


def l0_records(spec, runs, corner, nav=lambda i: "sticky-top"):
    records = []
    for task in TASKS:
        for wording in "AB":
            for index in range(1, runs + 1):
                records.append(make(spec, task, "L0", wording, index, "m1",
                                    values={CORNER: corner(index), NAV: nav(index),
                                            "website.libraries.libraries": ["tailwindcss"]}))
    return records


def test_stability_plans_the_doubling(spec, tmp_path):
    path = tmp_path / "records.jsonl"
    write_records(path, l0_records(spec, 5, lambda i: "rounded"))
    lines = []
    assert cli.main(["stability", "--records", str(path), "--batch", "b1", "--model", "m1",
                     "--out", str(tmp_path)], out=lines.append) == 0
    result = json.loads((tmp_path / "website-stability-m1-5v10.json").read_text("utf-8"))
    assert result["verdict"] == "not run"
    cells = result["selection"]["cells"]
    assert len(cells) == 12 and all(c["run_indexes"] == [6, 7, 8, 9, 10] for c in cells)
    assert result["selection"]["runner_command"] == (
        "python -m runner.run --prompts prompts/website --batch-id b1 --models m1 "
        "--levels L0 --runs 10 --dry-run")
    assert any("runner.run" in line for line in lines)


def test_stability_stable(spec):
    selection = select(l0_records(spec, 10, lambda i: "rounded"), spec, ["b1"])
    result = stability.check(selection, spec, "m1", 5, 10)
    assert result["verdict"] == "stable"
    assert result["score"] == 1 and result["reversals"] == 0
    assert result["consequence"] == "5 runs per cell stand for this model."
    assert set(result["counted"]) >= {CORNER, NAV, "website.libraries.libraries"}


def test_stability_drift(spec):
    selection = select(l0_records(spec, 10, lambda i: "square" if i == 1 or i > 5 else "rounded",
                                  lambda i: "static" if i == 1 or i > 5 else "sticky-top"),
                       spec, ["b1"])
    result = stability.check(selection, spec, "m1", 5, 10)
    assert result["reversals"] == 2
    assert result["verdict"] == "drift suspected"
    kinds = {c["variable"]: c["kind"] for c in result["changes"]}
    assert kinds == {CORNER: "reversed", NAV: "reversed"}
    halves = result["halves"]
    assert halves["groups"] == ["1-5", "6-10"]
    assert float(halves["shift_by_dimension"]["layout"]["mean"]) > 0


def test_stability_command_prints_the_figures(spec, tmp_path):
    path = tmp_path / "records.jsonl"
    write_records(path, l0_records(spec, 10, lambda i: "square" if i == 1 or i > 5
                                   else "rounded"))
    lines = []
    assert cli.main(["stability", "--records", str(path), "--batch", "b1", "--model", "m1",
                     "--out", str(tmp_path)], out=lines.append) == 0
    text = "\n".join(lines)
    assert "verdict: unstable: contested choices" in text
    assert "score 4/5" in text and "reversals 1" in text and "growth 0" in text
    assert f"{CORNER}: reversed" in text
    markdown = (tmp_path / "website-stability-m1-5v10.md").read_text(encoding="utf-8")
    assert "Check: first (5 against 10)" in markdown and "rounded -> square" in markdown


def test_stability_short_cells_and_bad_pairs(spec):
    records = l0_records(spec, 10, lambda i: "rounded")
    for record in records:
        if record["task_id"] == "portfolio" and record["wording"] == "A" and \
                record["run_index"] in (1, 2):
            record["status"], record["raw_response"] = "refused", "no"
            record["features"], record["extractors"] = [], []
    selection = select(records, spec, ["b1"])
    result = stability.check(selection, spec, "m1", 5, 10)
    assert result["verdict"] == "not run" and result["cells_short"] == ["portfolio L0 A"]
    with pytest.raises(Refused, match="5 with 10"):
        stability.check(selection, spec, "m1", 5, 20)
    repeat = stability.check(select(l0_records(spec, 10, lambda i: "rounded"), spec, ["b1"]),
                             spec, "m1", 10, 20)
    assert repeat["verdict"] == "not run" and repeat["check"].startswith("repeat")
    assert "--runs 20" in repeat["selection"]["runner_command"]


def test_select_files_reads_and_names_files(spec, grid_file, tmp_path):
    selection = select_files([grid_file], spec, ["b1"])
    assert selection.files == (str(grid_file),)
    assert tables.Grid(selection.runs, spec).models == ["m1", "m2"]
    copy = tmp_path / "copy.jsonl"
    copy.write_bytes(grid_file.read_bytes())
    with pytest.raises(Refused, match="is in both"):
        select_files([grid_file, copy], spec, ["b1"])


def test_t_quantiles_beyond_the_table():
    from analysis.stats import T975, _t_cdf_upper_half, t975
    for df, value in T975.items():            # the method agrees with the table
        assert abs(_t_cdf_upper_half(value, df) - 0.475) < 0.0002, df
    assert t975(12) == 2.179 and t975(20) == 2.086 and t975(5) == 2.571
