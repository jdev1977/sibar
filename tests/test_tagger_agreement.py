"""Agreement measures, the human tag file and its template (T2.6)."""

import argparse

import pytest
import yaml

from runner.record import with_features, write_records
from tagger import agreement
from tagger.agreement import AgreementError, Tagged, ac1, compare, family
from tests.tagger_support import record, rubric

R = rubric("pipeline")
CSV = [i.id for i in R.items_for("csv-to-database", "L0")]


def tagged(values, task="csv-to-database", provider=None):
    full = {"response_mode": "answers"}
    full.update(values)
    return Tagged(task, tuple(CSV), full, "L0", provider)


def first(item_id):
    return R.item(item_id).option_ids[0]


def base_values(**changes):
    values = {}
    for item_id in CSV[1:]:
        item = R.item(item_id)
        values[item_id] = [item.option_ids[0]] if item.multi else item.option_ids[0]
    values.update(changes)
    return values


# --- the worked examples of docs/rubrics.md ------------------------------------------

def test_ac1_matches_the_two_worked_examples():
    strong = [("content", "content")] * 28 + [("other", "content"), ("content", "other")]
    assert round(ac1(strong), 2) == 0.93
    pairs = ([("x", "x")] * 23 + [("y", "y")] * 3 + [("z", "z")]
             + [("x", "y"), ("y", "x"), ("z", "x")])
    assert sum(a == b for a, b in pairs) / 30 == 0.9
    assert round(ac1(pairs), 2) == 0.88
    assert ac1([("a", "a")] * 5) is None  # one answer only: undefined


def test_scores_follow_the_rules():
    item = R.item("cleaning_steps")
    a = tagged(base_values(cleaning_steps=["removes-duplicates", "trims-whitespace"]))
    b = tagged(base_values(cleaning_steps=["trims-whitespace"]))
    assert agreement.score(R, item, a, b, True, True) == 0.5   # Jaccard
    none = tagged(base_values(cleaning_steps=["none"]))
    assert agreement.score(R, item, none, none, True, True) == 1.0
    assert agreement.score(R, item, none, b, True, True) == 0.0
    na = tagged(base_values(cleaning_steps=[]))
    assert agreement.score(R, item, na, na, True, True) == 1.0
    assert agreement.score(R, item, na, b, True, True) == 0.0
    ct = tagged(base_values(cleaning_steps=None))
    assert agreement.score(R, item, ct, ct, True, True) == 1.0
    assert agreement.score(R, item, ct, b, True, True) == 0.0


def test_a_gate_disagreement_scores_every_further_item_zero():
    a = {"r1": tagged(base_values())}
    b = {"r1": Tagged("csv-to-database", tuple(CSV), {"response_mode": "asks-first"})}
    result = compare(R, a, b, reps=50)
    assert result["items"]["response_mode"]["agreement"] == 0.0
    for item_id in CSV[1:]:
        assert result["items"][item_id] == {**result["items"][item_id], "n": 1,
                                            "agreement": 0.0}
    # Both stopped: only the gate is judged.
    stop = {"r1": Tagged("csv-to-database", tuple(CSV), {"response_mode": "declines"})}
    assert set(compare(R, stop, stop, reps=50)["items"]) == {"response_mode"}


def test_rubric_agreement_is_weighted_by_judged_outputs_with_an_interval():
    a = {f"r{i}": tagged(base_values()) for i in range(10)}
    b = dict(a)
    b["r0"] = tagged(base_values(opening="question" if first("opening") != "question"
                                 else "content"))
    result = compare(R, a, b, reps=300, seed=3)
    judged = result["judgements"]
    assert judged == 10 * len(CSV)
    assert result["agreement"] == pytest.approx((judged - 1) / judged)
    low, high = result["interval"]
    assert low <= result["agreement"] <= high <= 1.0
    assert result["items"]["opening"]["agreement"] == pytest.approx(0.9)


def test_the_bar_and_minority_agreement():
    # 30 outputs where A's minority answers are all missed by B.
    a, b = {}, {}
    other = [o for o in R.item("opening").option_ids if o != first("opening")][0]
    for i in range(30):
        values = base_values(opening=other if i < 3 else first("opening"))
        a[f"r{i}"] = tagged(values)
        b[f"r{i}"] = tagged(base_values())
    result = compare(R, a, b, reps=200)
    assert result["minority"] == {"agreement": 0.0, "n": 3}
    checks = {c["condition"][0]: c["passed"] for c in result["bar"]}
    assert checks["1"] is True and checks["3"] is False and checks["4"] is True
    # cannot-tell where A gave a value
    b2 = dict(b)
    for i in range(5):
        b2[f"r{i}"] = tagged(base_values(closing=None))
    result = compare(R, a, b2, reps=50)
    assert result["items"]["closing"]["cannot_tell_rate"] == pytest.approx(5 / 30)
    assert {c["condition"][0]: c["passed"] for c in result["bar"]}["4"] is False


def test_judgements_where_a_stopped_at_the_gate_are_not_minority_judgements():
    # A stops at the gate on 5 of 30 outputs where B goes on. Those 5 gate
    # answers are A's minority answers; the items after the gate have no A
    # answer, so they are not minority judgements (docs/rubrics.md, bar 3).
    a, b = {}, {}
    for i in range(30):
        b[f"r{i}"] = tagged(base_values())
        a[f"r{i}"] = (Tagged("csv-to-database", tuple(CSV), {"response_mode": "declines"})
                      if i < 5 else tagged(base_values()))
    result = compare(R, a, b, reps=50)
    assert result["minority"] == {"agreement": 0.0, "n": 5}


def test_tagger_errors_are_left_out_and_counted_not_scored_as_cannot_tell():
    a = {f"r{i}": tagged(base_values()) for i in range(4)}
    b = dict(a)
    b["r1"] = Tagged("csv-to-database", tuple(CSV), {}, "L0", error=True)
    b["r2"] = Tagged("csv-to-database", tuple(CSV), {}, "L0", error=True)
    a["r3"] = Tagged("csv-to-database", tuple(CSV), {}, "L0", error=True)
    result = compare(R, a, b, reps=50)
    assert result["outputs"] == 1 and result["agreement"] == 1.0
    assert result["errors"] == {"a": 1, "b": 2, "left_out": 3}
    assert result["items"]["response_mode"]["cannot_tell_rate"] == 0.0
    assert "tagger error" in agreement.report(result)
    # No output left to compare is refused.
    with pytest.raises(AgreementError):
        compare(R, {"r1": a["r3"]}, {"r1": a["r0"]}, reps=10)


def test_a_tagged_file_marks_outputs_whose_tagging_ended_in_an_error(tmp_path):
    good, bad = record(), record()
    items = [i.id for i in R.items_for("csv-to-database", "L0")]
    values = {i: ([R.item(i).option_ids[0]] if R.item(i).multi
                  else R.item(i).option_ids[0]) for i in items}
    values.update(response_mode="answers", status="ok")
    path = tmp_path / "tagged.jsonl"
    write_records(path, [
        with_features(good, "rubric.pipeline", "1@claude-haiku-5-5", values),
        with_features(bad, "rubric.pipeline", "1@claude-haiku-5-5",
                      {"status": "error", "error": "no usable answer after retry"})])
    loaded = agreement.load_tagged_records(path, R)
    assert not loaded[good["record_id"]].error and loaded[bad["record_id"]].error
    assert loaded[bad["record_id"]].values == {}


def test_the_cross_family_check_flags_a_direction():
    a, b, writers = {}, {}, {}
    item = R.item("opening")
    one = item.option_ids[0]
    for i in range(40):
        inside = i < 20
        writers[f"r{i}"] = "anthropic" if inside else "openai"
        a[f"r{i}"] = tagged(base_values(opening=one))
        # The other tagger stops at the gate on inside outputs, and agrees
        # on the outside ones.
        b[f"r{i}"] = (Tagged("csv-to-database", tuple(CSV), {"response_mode": "declines"})
                      if inside else tagged(base_values(opening=one)))
    fam = family(R, a, b, writers, "anthropic", reps=300)
    assert fam["gap"] == pytest.approx(-1.0) and fam["gap_flagged"]
    found = {(d["item"], d["answer"]): d for d in fam["directions"]}
    assert found[("opening", one)]["value"] == pytest.approx(1.0)
    assert found[("opening", one)]["flagged"]
    assert found[("response_mode", "declines")]["value"] == pytest.approx(-1.0)
    with pytest.raises(AgreementError):
        family(R, a, b, {k: "anthropic" for k in writers}, "anthropic", reps=10)


# --- files ------------------------------------------------------------------------------

def _records(tmp_path, n=4):
    records = [record(text=f"Answer {i}\n```python\nprint({i})\n```") for i in range(n)]
    records.append(record(project_type="math", task="loan-amortization"))
    path = tmp_path / "records.jsonl"
    write_records(path, records)
    return records, path


def test_the_template_is_blind_and_loads_once_filled(tmp_path):
    records, path = _records(tmp_path)
    folder = tmp_path / "human"
    assert agreement.make_template(R, records, folder, sample=3, seed=1) == 3
    doc = yaml.safe_load((folder / "tags.yaml").read_text(encoding="utf-8"))
    assert doc["kind"] == "human-tags" and doc["rubric"] == "pipeline.v1"
    assert len(doc["outputs"]) == 3
    text = (folder / "tags.yaml").read_text(encoding="utf-8")
    for output in doc["outputs"]:
        sheet = (folder / output["sheet"]).read_text(encoding="utf-8")
        for leak in ("claude-opus-5-5", "anthropic", "L0", "Write it."):
            assert leak not in sheet and leak not in text
        assert R.item("opening").question in sheet
    # Blank answers are refused.
    with pytest.raises(AgreementError, match="blank"):
        agreement.load_human(folder / "tags.yaml", R)
    # Filled in, it loads.
    for output in doc["outputs"]:
        for item_id in output["items"]:
            item = R.item(item_id)
            output["answers"][item_id] = [item.option_ids[0]] if item.multi \
                else ("answers" if item_id == "response_mode" else item.option_ids[0])
        output["answers"]["opening"] = "cannot-tell"
        output["answers"]["cleaning_steps"] = "not-applicable"
    (folder / "tags.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    loaded = agreement.load_human(folder / "tags.yaml", R)
    one = next(iter(loaded.values()))
    assert one.values["opening"] is None and one.values["cleaning_steps"] == []
    with pytest.raises(AgreementError, match="never overwritten"):
        agreement.make_template(R, records, folder, sample=1)


def test_a_human_file_with_a_bad_answer_is_refused(tmp_path):
    records, _ = _records(tmp_path, n=1)
    folder = tmp_path / "human"
    agreement.make_template(R, records, folder)
    doc = yaml.safe_load((folder / "tags.yaml").read_text(encoding="utf-8"))
    doc["outputs"][0]["answers"]["response_mode"] = "declines"
    doc["outputs"][0]["answers"]["opening"] = "content"  # after a stopping gate
    (folder / "tags.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(AgreementError, match="leave it blank"):
        agreement.load_human(folder / "tags.yaml", R)


def test_agreement_of_a_tagged_file_with_itself_through_the_command(tmp_path):
    records, _ = _records(tmp_path)
    tagged_records = []
    for rec in records:
        if rec["project_type"] == "pipeline":
            items = [i.id for i in R.items_for(rec["task_id"], rec["level"])]
            values = {i: ([R.item(i).option_ids[0]] if R.item(i).multi
                          else R.item(i).option_ids[0]) for i in items}
            values["response_mode"] = "answers"
            values["status"] = "ok"
            rec = with_features(rec, "rubric.pipeline", "1@claude-haiku-5-5", values)
        tagged_records.append(rec)
    path = tmp_path / "tagged.jsonl"
    write_records(path, tagged_records)
    from tagger.__main__ import main
    lines = []
    code = main(["agreement", "--type", "pipeline", "--a", str(path), "--b", str(path),
                 "--reps", "50", "--json", str(tmp_path / "a.json")], out=lines.append)
    assert code == 0
    assert "Rubric agreement A = 1.000" in lines[0]
    assert (tmp_path / "a.json").exists()
    code = main(["agreement", "--type", "math", "--a", str(path), "--b", str(path)],
                out=lines.append)
    assert code == 2 and "no output in common" in lines[-1]


def test_the_template_command(tmp_path):
    _, path = _records(tmp_path)
    from tagger.__main__ import main
    lines = []
    code = main(["template", "--type", "pipeline", "--records", str(path),
                 "--sample", "2", "--seed", "4", "--out", str(tmp_path / "h")],
                out=lines.append)
    assert code == 0 and (tmp_path / "h" / "tags.yaml").exists()
    assert len(list((tmp_path / "h" / "sheets").iterdir())) == 2
    assert argparse  # imported for the command's parser


def test_the_template_covers_website_outputs(tmp_path):
    web = rubric("website")
    records = [record(project_type="website", task="bakery-landing",
                      text="Here it is.\n```html\n<h1>Crumb</h1>\n```")]
    assert agreement.make_template(web, records, tmp_path / "w") == 1
    doc = yaml.safe_load((tmp_path / "w" / "tags.yaml").read_text(encoding="utf-8"))
    assert doc["rubric"] == "website.v1"
    assert doc["outputs"][0]["items"][0] == "response_mode"
    sheet = (tmp_path / "w" / doc["outputs"][0]["sheet"]).read_text(encoding="utf-8")
    assert "<h1>Crumb</h1>" in sheet and "````text" in sheet
