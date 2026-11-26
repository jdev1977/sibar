"""The pipeline extractors on hand-made fixtures with known values (T2.8).

Fixtures are in tests/fixtures/pipeline/. Each expected value was worked out
by reading the fixture.
"""

from pathlib import Path

import pytest

from extractors.base import InputFile, Inputs, run_extractors
from extractors.registry import extractors_for

FIXTURES = Path(__file__).parent / "fixtures" / "pipeline"
PIPELINE = extractors_for("pipeline")


def run_inputs(inputs):
    results = run_extractors(PIPELINE, inputs)
    return {full.split(".", 1)[1]: values for full, (_, values) in results.items()}


def run(name):
    return run_inputs(Inputs.from_directory(FIXTURES / name))


def reply(text, files=()):
    record = {"raw_response": text, "prompt_text": "Write a pipeline.", "files": []}
    return run_inputs(Inputs(files, record=record))


def one_file(source, name="a.py"):
    return reply("code", [InputFile(name, source.encode())])


def check(values, expected):
    assert {key: values.get(key, "<missing>") for key in expected} == expected


def test_every_extractor_runs_on_every_fixture_twice_alike():
    for folder in sorted(FIXTURES.iterdir()):
        first, second = run(folder.name), run(folder.name)
        assert first == second, folder.name
        for name, values in first.items():
            assert values["status"] in ("ok", "no-input"), (folder.name, name, values)


def test_standard_library_package():
    out = run("csv-package")
    check(out["language"], {"primary_language": "python",
                            "languages": ["python", "shell"]})
    check(out["libraries"], {
        "third_party": [], "other_imports": [], "stdlib_only": True,
        "database_libraries": ["sqlite3"], "scheduling_libraries": [],
        "imports": ["argparse", "csv", "logging", "pathlib", "sqlite3", "unittest"]})
    check(out["layout"], {
        "structure": "single-file", "source_files": 1, "has_readme": False,
        "dependency_files": [], "entry_point_guard": True,
        "file_names": ["pipeline.py", "test_pipeline.py"]})
    check(out["testing"], {"tests_present": True, "test_files": 1,
                           "test_frameworks": ["unittest"]})
    check(out["logging"], {"logging_style": "both", "logging_libraries": ["logging"],
                           "uses_print": True})
    check(out["comments"], {"comment_lines": 1, "docstrings": 2,
                            "has_docstrings": True})
    check(out["config"], {"config_sources": ["arguments"], "key_source": "none"})
    check(out["operations"], {
        "retry_present": False, "retry_libraries": [], "file_reading": "streaming",
        "output_formats": ["csv", "database", "printed"], "parallel_work": []})
    check(out["ci"], {"ci_service": "none", "triggers": [], "timeout": "no-workflow"})
    check(out["images"], {"orientation_handling": "no-image-code",
                          "metadata_handling": "no-image-code"})
    check(out["reply"], {"headings": 2, "list_items": 2, "code_blocks": 3})


def test_single_script_with_key_retries_and_scheduler():
    out = run("api-script")
    check(out["language"], {"primary_language": "python", "languages": ["python"]})
    check(out["libraries"], {
        "third_party": ["python-dotenv", "requests", "schedule", "tenacity"],
        "stdlib_only": False, "database_libraries": [],
        "scheduling_libraries": ["schedule"]})
    check(out["layout"], {"structure": "single-file", "source_files": 1,
                          "file_names": [], "entry_point_guard": False})
    check(out["testing"], {"tests_present": False, "test_frameworks": []})
    check(out["logging"], {"logging_style": "print", "logging_libraries": []})
    check(out["config"], {"config_sources": ["environment"],
                          "key_source": "environment"})
    check(out["operations"], {"retry_present": True,
                              "retry_libraries": ["tenacity"],
                              "output_formats": ["json", "printed"]})


def test_whole_file_reading():
    out = run("log-whole")
    check(out["operations"], {"file_reading": "whole-file",
                              "read_calls": ["readlines"]})


def test_streaming_package_with_config_file_and_tests():
    out = run("log-stream")
    check(out["layout"], {"structure": "package", "has_readme": True,
                          "dependency_files": ["pyproject.toml"], "source_files": 3})
    check(out["libraries"], {"stdlib_only": True, "third_party": [],
                             "other_imports": []})
    check(out["testing"], {"tests_present": True, "test_files": 1,
                           "test_frameworks": ["pytest"]})
    check(out["config"], {"config_sources": ["arguments", "config-file"]})
    check(out["operations"], {"file_reading": "streaming",
                              "read_calls": ["line-loop"]})
    check(out["logging"], {"logging_style": "neither", "uses_print": False})


def test_image_orientation_metadata_and_parallel_work():
    out = run("image-pillow")
    check(out["images"], {
        "orientation_handling": "present", "orientation_calls": ["exif-transpose"],
        "metadata_handling": "strips", "metadata_calls": ["empty-exif"],
        "image_libraries": ["pillow"]})
    check(out["operations"], {"parallel_work": ["process-pool"],
                              "output_formats": ["image", "printed"]})


def test_ci_workflow():
    out = run("ci-github")
    check(out["language"], {"status": "ok", "primary_language": "none",
                            "languages": []})
    check(out["layout"], {"structure": "config-only", "source_files": 0})
    check(out["ci"], {
        "ci_service": "github-actions",
        "triggers": ["pull-request", "push", "tag"],
        "matrix_keys": ["go", "os"],
        "matrix_os": ["linux", "macos", "windows"],
        "matrix_versions": ["go=1.24.x", "go=1.25.x"],
        "ci_tools": ["coverage", "go-test", "go-vet", "gofmt"],
        "timeout": "set", "cancel_superseded": "set"})
    check(out["libraries"], {"status": "no-input"})


def test_a_reply_without_code_has_no_code_and_unread_code_features():
    out = run("prose-only")
    check(out["layout"], {"structure": "no-code", "source_files": 0})
    for name in ("language", "libraries", "testing", "logging", "comments",
                 "config", "operations", "images", "ci"):
        assert out[name] == {"status": "no-input"}, name


def test_comments_strings_and_docstrings_are_not_choices():
    out = run("negative")
    check(out["libraries"], {"imports": ["json"], "third_party": [],
                             "stdlib_only": True})
    check(out["config"], {"config_sources": [], "key_source": "none"})
    check(out["operations"], {"retry_present": False, "output_formats": []})
    check(out["logging"], {"logging_style": "neither", "logging_libraries": []})
    check(out["testing"], {"tests_present": False})


def test_alternative_snippets_leave_the_structure_open():
    out = run("snippets")
    assert out["layout"]["structure"] is None
    assert out["layout"]["source_files"] is None
    check(out["libraries"], {"database_libraries": ["sqlite3"]})


def test_javascript_with_a_written_in_key():
    out = run("node-fetch")
    check(out["language"], {"primary_language": "javascript"})
    check(out["libraries"], {"third_party": ["axios", "node-cron"],
                             "scheduling_libraries": ["node-cron"],
                             "stdlib_only": False})
    check(out["config"], {"key_source": "written-in", "config_sources": []})
    check(out["operations"], {"retry_present": True,
                              "output_formats": ["json", "printed"]})
    check(out["logging"], {"logging_style": "print"})


@pytest.mark.parametrize("source, expected", [
    ('key = os.getenv("API_KEY")\n', "environment"),
    ('API_KEY = "<your-key>"\n', "written-in"),
    ('api_key = config["api_key"]\n', "file"),
    ('api_key = args.api_key\n', "argument"),
    ('api_key = os.getenv("SERVICE_KEY")\napi_key = args.api_key\n', "several"),
    ('def f(api_key):\n    return api_key\n', None),
    ('def f(day):\n    return day\n', "none"),
    ('headers = {"X-Api-Key": key}\ntokens = line.split()\n', None),
    ('for token in text.split():\n    pass\n', "none"),
])
def test_where_a_key_is_read_from(source, expected):
    assert one_file(source)["config"]["key_source"] == expected


@pytest.mark.parametrize("source, expected", [
    ("data = open('a').read()\n", "whole-file"),
    ("import pandas as pd\npd.read_csv('a.csv')\n", "whole-file"),
    ("import pandas as pd\nfor c in pd.read_csv('a.csv', chunksize=10):\n    pass\n",
     "streaming"),
    ("with open('a') as f:\n    for n, line in enumerate(f, 1):\n        pass\n",
     "streaming"),
    ("with open('a') as f:\n    rows = list(csv.reader(f))\n", "whole-file"),
    ("with open('a') as f:\n    while chunk := f.read(65536):\n        pass\n",
     "streaming"),
    ("body = response.read()\n", "none"),
    ("with open('a') as f:\n    consume(f)\n", None),
    ("with open('r.json') as f:\n    rules = json.load(f)\n"
     "with open('a') as g:\n    for line in g:\n        pass\n", "both"),
])
def test_how_files_are_read(source, expected):
    assert one_file(source)["operations"]["file_reading"] == expected


def test_an_unrecognised_import_makes_stdlib_only_undetermined():
    out = one_file("import helpers\nimport csv\n")
    check(out["libraries"], {"stdlib_only": None, "other_imports": ["helpers"],
                             "third_party": []})


def test_an_unsupported_language_leaves_libraries_undetermined():
    out = one_file("import java.util.List;\nclass A {}\n", "A.java")
    check(out["language"], {"primary_language": "java"})
    assert out["libraries"]["third_party"] is None
    assert out["libraries"]["stdlib_only"] is None


def test_go_imports():
    out = one_file('package main\nimport (\n    "fmt"\n    "log/slog"\n'
                   '    "github.com/robfig/cron/v3"\n)\n', "main.go")
    check(out["libraries"], {"third_party": ["github.com/robfig/cron"],
                             "scheduling_libraries": ["github.com/robfig/cron"],
                             "stdlib_only": False})
    check(out["logging"], {"logging_libraries": ["slog"]})


@pytest.mark.parametrize("name, source, service", [
    (".gitlab-ci.yml", "test:\n  script: [pytest]\n", "gitlab-ci"),
    ("block-01.yaml", "version: 2.1\njobs:\n  a:\n    docker: []\n    steps: []\n",
     "circleci"),
    ("block-01.yaml", "trigger: [main]\npool:\n  vmImage: ubuntu-latest\nsteps: []\n",
     "azure-pipelines"),
    ("block-01.yaml", "services:\n  db:\n    image: x\n", "none"),
    ("block-01.yaml", "on: push\njobs:\n  a:\n    runs-on: x\n    steps: []\n",
     "github-actions"),
])
def test_ci_services(name, source, service):
    assert one_file(source, name)["ci"]["ci_service"] == service


def test_a_workflow_that_does_not_parse_is_undetermined():
    out = one_file("on: [push\njobs: {\n", ".github/workflows/ci.yml")
    assert out["ci"]["ci_service"] == "github-actions"
    assert out["ci"]["triggers"] is None and out["ci"]["timeout"] is None


def test_a_yaml_alias_bomb_is_refused_quickly():
    lines = ["a0: &a0 {k0: 1, k1: 1}"]
    for i in range(1, 40):
        lines.append(f"a{i}: &a{i} {{<<: [*a{i-1}, *a{i-1}], x{i}: 1}}")
    text = "on: push\njobs: {}\n" + "\n".join(lines) + "\n"
    out = one_file(text, ".github/workflows/ci.yml")
    assert out["ci"]["triggers"] is None
