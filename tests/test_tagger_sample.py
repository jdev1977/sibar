"""The calibration sample (T2.5): ``python -m tagger sample``. No network."""

import random
from collections import Counter

import pytest

from runner.record import read_records, write_records
from tagger import __main__ as cli
from tagger.sample import SampleError, human_subset, stratified
from tests.tagger_support import record, rubric

MODELS = (("claude-opus-5-5", "anthropic"), ("gpt-6.2-sol", "openai"),
          ("gemini-4-hydrogen", "google"))


def pool(project_type="pipeline", runs=5, tasks=None):
    tasks = tasks or rubric(project_type).tasks
    made = []
    for task in tasks:
        for level in ("L0", "L1", "L2"):
            for wording in "AB":
                for model, provider in MODELS:
                    for run_index in range(1, runs + 1):
                        made.append(record(project_type, task, level, model_id=model,
                                           provider=provider, wording=wording,
                                           run_index=run_index))
    return made


def spread(chosen, key):
    counts = Counter(key(r) for r in chosen)
    return max(counts.values()) - min(counts.values()), len(counts)


def test_the_100_are_balanced_over_tasks_levels_wordings_and_models():
    records = pool()
    noise = [record(status="failed"), record(status="truncated"),
             record("math", rubric("math").tasks[0])]
    chosen = stratified(records + noise, rubric(), 100, seed=1)
    assert len(chosen) == 100 and len({r["record_id"] for r in chosen}) == 100
    assert all(r["status"] == "ok" and r["project_type"] == "pipeline" for r in chosen)
    per_task = Counter(r["task_id"] for r in chosen)
    assert set(per_task) == set(rubric().tasks)
    assert set(per_task.values()) <= {16, 17}
    for task in per_task:
        mine = [r for r in chosen if r["task_id"] == task]
        for key in (lambda r: r["level"], lambda r: r["wording"], lambda r: r["model_id"]):
            difference, kinds = spread(mine, key)
            assert difference <= 1 and kinds in (2, 3)


def test_the_sample_is_fixed_by_the_seed_not_by_file_order():
    records = pool()
    first = [r["record_id"] for r in stratified(records, rubric(), 100, seed=1)]
    shuffled = list(records)
    random.Random(5).shuffle(shuffled)
    assert [r["record_id"] for r in stratified(shuffled, rubric(), 100, seed=1)] == first
    assert [r["record_id"] for r in stratified(records, rubric(), 100, seed=2)] != first


def test_the_30_for_the_human_cover_every_level_and_model_per_task():
    chosen = stratified(pool(), rubric(), 100, seed=1)
    human = human_subset(chosen, rubric(), 5, seed=1)
    assert len(human) == 30 and {r["record_id"] for r in human} <= \
        {r["record_id"] for r in chosen}
    for task in rubric().tasks:
        mine = [r for r in human if r["task_id"] == task]
        assert len(mine) == 5
        assert {r["level"] for r in mine} == {"L0", "L1", "L2"}
        assert {r["model_id"] for r in mine} == {m for m, _ in MODELS}


def test_too_few_records_of_a_task_are_refused():
    records = [r for r in pool(runs=1)
               if not (r["task_id"] == rubric().tasks[0] and r["level"] != "L0")]
    with pytest.raises(SampleError, match=rubric().tasks[0]):
        stratified(records, rubric(), 100, seed=1)


def test_models_can_be_limited():
    records = pool(runs=3) + [record(model_id="deepseek-v4", provider="deepseek",
                                     task=rubric().tasks[0])]
    chosen = stratified(records, rubric(), 60, seed=1,
                        models=[m for m, _ in MODELS])
    assert {r["model_id"] for r in chosen} == {m for m, _ in MODELS}


def test_the_command_writes_files_that_tag_and_template_take(tmp_path):
    source = tmp_path / "records.jsonl"
    write_records(source, pool())
    out = tmp_path / "sample"
    lines = []
    assert cli.main(["sample", "--type", "pipeline", "--records", str(source),
                     "--size", "100", "--human", "5", "--seed", "1", "--models", "pilot",
                     "--out", str(out)], out=lines.append) == 0
    subset = read_records(out / "records.jsonl")
    assert subset.ok and len(subset.records) == 100
    ids = (out / "ids.txt").read_text(encoding="utf-8").split()
    assert ids == [r["record_id"] for r in subset.records]
    human = read_records(out / "human-records.jsonl").records
    assert len(human) == 30
    assert (out / "human-ids.txt").read_text(encoding="utf-8").split() == \
        [r["record_id"] for r in human]
    assert "100 records" in "\n".join(lines)
    # The human template takes the 30 as they are.
    assert cli.main(["template", "--type", "pipeline", "--records",
                     str(out / "human-records.jsonl"), "--out", str(tmp_path / "human")],
                    out=lines.append) == 0
    assert "30 outputs" in lines[-1]
    # Same command again: the files are never overwritten.
    assert cli.main(["sample", "--type", "pipeline", "--records", str(source),
                     "--size", "100", "--seed", "1", "--out", str(out)],
                    out=lines.append) == 2
    assert lines[-1].startswith("refused:")


def test_the_website_rubric_samples_too():
    chosen = stratified(pool("website", runs=2), rubric("website"), 100, seed=3)
    assert set(Counter(r["task_id"] for r in chosen).values()) <= {16, 17}
