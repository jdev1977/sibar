"""The prompt file format and loader (T0.5, used by T1.1). No network."""

from pathlib import Path

import pytest

from runner.prompts import PromptError, load_prompt_file, load_prompts

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "prompts" / "example" / "tiny-task.yaml"

GOOD = """\
schema_version: 1
project_type: website
task_id: bakery
prompt_set_version: "1"
prompts:
  L0:
    A: Make a website for a bakery.
    B: Build a website for a bakery.
  L1:
    A: One.
    B: Two.
  L2:
    A: Three.
    B: Four.
"""


def write(tmp_path, text, name="bakery.yaml", folder="website"):
    path = tmp_path / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_committed_example_loads():
    task = load_prompt_file(FIXTURE)
    assert (task.project_type, task.task_id, task.prompt_set_version) == (
        "example", "tiny-task", "0")
    assert task.text("L0", "A") == "Write a short poem about bread."
    assert len(task.variants()) == 6


def test_variants_come_in_level_then_wording_order(tmp_path):
    task = load_prompt_file(write(tmp_path, GOOD))
    assert [(level, wording) for level, wording, _ in task.variants()] == [
        ("L0", "A"), ("L0", "B"), ("L1", "A"), ("L1", "B"),
        ("L2", "A"), ("L2", "B")]
    assert task.variants()[1][2] == "Build a website for a bakery."


def test_texts_are_stripped_of_surrounding_whitespace():
    task = load_prompt_file(FIXTURE)
    text = task.text("L2", "A")
    assert text.startswith("Write a four-line poem")
    assert text.endswith("eight words.")
    assert "\n" in text  # inner line breaks are kept


def test_a_one_wording_type_may_leave_out_b(tmp_path):
    text = GOOD.replace("    B: Two.\n", "").replace(
        "    B: Build a website for a bakery.\n", "").replace("    B: Four.\n", "")
    task = load_prompt_file(write(tmp_path, text))
    assert [wording for _, wording, _ in task.variants()] == ["A", "A", "A"]
    with pytest.raises(KeyError):
        task.text("L0", "B")


@pytest.mark.parametrize("old,new,message", [
    ("schema_version: 1", "schema_version: 2", "schema_version"),
    ("task_id: bakery", "task_id: Bakery", "task_id"),
    ("task_id: bakery", "task_id: other", "file name"),
    ("project_type: website", "project_type: pipeline", "folder"),
    ('prompt_set_version: "1"', "prompt_set_version: 1", "quote"),
    ('prompt_set_version: "1"', 'prompt_set_version: "v 1"', "prompt_set_version"),
    ("  L2:\n    A: Three.\n    B: Four.\n", "", "L2"),
    ("    A: One.\n", "", "L1.A"),
    ("    A: One.", "    A: '   '", "L1.A"),
    ("    A: One.", "    A: 7", "L1.A"),
    ("    B: Two.", "    C: Two.", "wording"),
    ("  L2:", "  L3:", "level"),
    ("prompts:", "extra: 1\nprompts:", "unknown key"),
    ("schema_version: 1\n", "", "missing"),
    ("    A: One.", "    A: One.\n    A: Again.", "repeated key"),
])
def test_broken_files_are_refused_with_a_reason(tmp_path, old, new, message):
    assert old in GOOD
    path = write(tmp_path, GOOD.replace(old, new, 1))
    with pytest.raises(PromptError) as error:
        load_prompt_file(path)
    assert message in str(error.value)
    assert "bakery.yaml" in str(error.value)


@pytest.mark.parametrize("prompts,message", [
    ("[]", "prompts must be a mapping of level to wordings"),
    ("{L0: x, L1: x, L2: x}", "prompts.L0 must be a mapping of wording"),
])
def test_prompts_must_nest_levels_and_wordings(tmp_path, prompts, message):
    text = GOOD.split("prompts:")[0] + f"prompts: {prompts}\n"
    with pytest.raises(PromptError, match=message):
        load_prompt_file(write(tmp_path, text))


def test_notes_are_allowed_for_authors(tmp_path):
    task = load_prompt_file(write(tmp_path, GOOD + "notes: Leak check passed.\n"))
    assert task.task_id == "bakery"


def test_invalid_yaml_is_a_prompt_error(tmp_path):
    with pytest.raises(PromptError):
        load_prompt_file(write(tmp_path, "prompts: [unclosed\n"))


def test_only_yaml_files_are_prompt_files(tmp_path):
    with pytest.raises(PromptError):
        load_prompt_file(write(tmp_path, GOOD, name="bakery.txt"))


def test_a_directory_loads_every_prompt_file_below_it_in_path_order(tmp_path):
    write(tmp_path, GOOD)
    write(tmp_path, GOOD.replace("task_id: bakery", "task_id: alpha"),
          name="alpha.yml")
    write(tmp_path, GOOD.replace("website", "pipeline").replace(
        "task_id: bakery", "task_id: csv"), name="csv.yaml", folder="pipeline")
    (tmp_path / "README.md").write_text("not a prompt", encoding="utf-8")
    tasks = load_prompts([tmp_path])
    assert [(t.project_type, t.task_id) for t in tasks] == [
        ("pipeline", "csv"), ("website", "alpha"), ("website", "bakery")]


def test_the_same_task_twice_is_refused(tmp_path):
    first = write(tmp_path, GOOD)
    second = write(tmp_path / "copy", GOOD)
    with pytest.raises(PromptError, match="more than once"):
        load_prompts([first, second])


def test_no_prompt_files_is_an_error(tmp_path):
    with pytest.raises(PromptError, match="no prompt files"):
        load_prompts([tmp_path])


def test_a_missing_path_is_an_error(tmp_path):
    with pytest.raises(PromptError, match="not found"):
        load_prompts([tmp_path / "nothing.yaml"])
