"""Tests for tools/secret_scan.py and the pre-commit hook.

Every fake secret and every `*_API_KEY` assignment is assembled at runtime so
that the scanner does not flag this file.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

KEY_NAME = "ANTHROPIC_API" + "_KEY"
BODY = "Ab3dEf6h" * 5
FAKE_KEYS = {
    "anthropic": "sk-" + "ant-api03-" + BODY,
    "openai-project": "sk-" + "proj-" + BODY,
    "openai-legacy": "sk-" + BODY,
    "deepseek": "sk-" + "0123456789abcdef" * 2,
    "openrouter": "sk-" + "or-v1-" + "0123456789abcdef" * 4,
    "google": "AI" + "za" + BODY[:35],
    "xai": "xai" + "-" + BODY,
    "vercel": "vck" + "_" + BODY,
}
PEM_HEADERS = [
    "-" * 5 + "BEGIN " + kind + "PRIVATE KEY" + suffix + "-" * 5
    for kind, suffix in [
        ("", ""), ("RSA ", ""), ("OPENSSH ", ""), ("EC ", ""),
        ("ENCRYPTED ", ""), ("PGP ", " BLOCK"),
    ]
]
FAKE = FAKE_KEYS["anthropic"]


def scanner():
    import secret_scan

    return secret_scan


def assign(value, name=KEY_NAME, op="="):
    return name + op + value


# --- content rules ----------------------------------------------------------


@pytest.mark.parametrize("provider", FAKE_KEYS)
def test_provider_key_is_found(provider):
    findings = scanner().scan_text("a.txt", f"first\ntoken {FAKE_KEYS[provider]}\n")
    assert [(f.path, f.line) for f in findings] == [("a.txt", 2)]


@pytest.mark.parametrize("header", PEM_HEADERS)
def test_private_key_block_is_found(header):
    assert scanner().scan_text("a.txt", header + "\n")


@pytest.mark.parametrize(
    "line",
    [
        assign("hunter2value"),
        assign('"hunter2value"'),
        assign("'hunter2value'", op=" = "),
        assign("hunter2value", name="MISTRAL_API" + "_KEY"),
        "export " + assign("hunter2value"),
        assign("hunter2value", op=": "),
        '{"' + KEY_NAME + '": "hunter2value"}',
        'os.environ["' + KEY_NAME + '"] = "hunter2value"',
        "$env:" + assign('"hunter2value"', op=" = "),
        assign("hunter2value", op=" := "),
        assign("$abc!realvalue"),
        assign("${" + KEY_NAME + ":-hunter2value}", name="X_API" + "_KEY"),
    ],
)
def test_generic_api_key_assignment_is_found(line):
    assert scanner().scan_text("a.txt", line)


@pytest.mark.parametrize(
    "line",
    [
        assign(""),
        assign("   "),
        assign('""'),
        assign("''"),
        assign("  # set this locally"),
        assign("$OTHER_VALUE"),
        assign('"${OTHER_VALUE}"'),
        assign("${{ secrets.ANTHROPIC }}", op=": "),
        assign("%OTHER_VALUE%"),
        assign("<your-key>"),
        assign("..."),
        assign('os.environ.get("' + KEY_NAME + '")', op=" = "),
        assign('os.getenv("' + KEY_NAME + '")', op=" = "),
        assign("process.env." + KEY_NAME, op=": "),
        assign("None", op=" = "),
        "if " + KEY_NAME + " == expected:",
        'if os.environ["' + KEY_NAME + '"]:',
        "echo ${" + KEY_NAME + ":-}",
        "the `" + assign("") + "` line",
        "Keys such as " + KEY_NAME + " come from the environment.",
        "a task-" + "oriented-description-of-something-long",
        "disk-" + "usage-report-generator-for-everything",
    ],
)
def test_harmless_line_is_not_flagged(line):
    assert scanner().scan_text("a.txt", line) == []


def test_allow_marker_silences_only_the_generic_rule():
    marker = "  # secret-scan: allow"
    assert scanner().scan_text("a.py", assign("not-a-secret") + marker) == []
    assert scanner().scan_text("a.py", assign(FAKE) + marker)
    assert scanner().scan_text("a.py", PEM_HEADERS[0] + marker)


@pytest.mark.parametrize(
    "secret", list(FAKE_KEYS.values()) + ["hunter2value-very-private"]
)
def test_findings_never_contain_the_secret(secret):
    findings = scanner().scan_text("a.txt", assign(secret))
    assert findings
    report = "\n".join(str(f) + repr(f) for f in findings)
    assert secret not in report
    assert secret[8:] not in report


def test_secret_in_a_path_is_redacted():
    findings = scanner().scan_text(f"dir/{FAKE}.txt", FAKE)
    assert findings
    assert all(FAKE not in str(f) + repr(f) for f in findings)


def test_utf16_content_is_scanned():
    data = ("x = " + FAKE + "\r\n").encode("utf-16")
    assert scanner().scan_blob("a.txt", data)


# --- filename rules ---------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".env", "sub/.env", ".env.local", "prod.env", ".envrc", ".ENV",
        "server.key", "a/b/cert.PEM", "plan.private.md", "notes/x.private.md",
    ],
)
def test_forbidden_filename(path):
    assert scanner().forbidden_filename(path)


@pytest.mark.parametrize(
    "path",
    [".env.example", "sub/.env.example", "environment.py", "keys.md",
     "docs/secrets.md", "private.md", "monkey"],
)
def test_allowed_filename(path):
    assert not scanner().forbidden_filename(path)


# --- repository files -------------------------------------------------------


def test_env_example_has_names_only():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    entries = [line for line in lines if line and not line.startswith("#")]
    assert all(entry.endswith("=") and entry.count("=") == 1 for entry in entries)
    names = {entry[:-1] for entry in entries}
    for provider in ("ANTHROPIC", "OPENAI", "GEMINI", "XAI", "MISTRAL",
                     "DEEPSEEK", "OPENROUTER", "AI_GATEWAY"):
        assert provider + "_API" + "_KEY" in names


def ignored(path):
    # --no-index so that already tracked files are judged by the patterns too
    return subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path], cwd=ROOT
    ).returncode


@pytest.mark.parametrize(
    "path",
    [".env", ".env.local", "prod.env", ".envrc", "a.key", "a.pem",
     "x.private.md", "data/x.json", "runs/x.json", "outputs/x.json"],
)
def test_gitignore_covers(path):
    assert ignored(path) == 0


def test_gitignore_keeps_env_example():
    assert ignored(".env.example") == 1


def test_hook_is_checked_out_with_lf():
    out = subprocess.run(
        ["git", "check-attr", "eol", "--", ".githooks/pre-commit"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert out.strip().endswith("eol: lf")


# --- end to end -------------------------------------------------------------


class Repo:
    """A throwaway git repository, isolated from the user's git config."""

    def __init__(self, path):
        self.path = path
        self.env = {
            k: v for k, v in os.environ.items() if not k.startswith("GIT_")
        }
        self.env["GIT_CONFIG_GLOBAL"] = os.devnull
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"

    def git(self, *args, check=True):
        result = subprocess.run(
            ["git", *args], cwd=self.path, env=self.env,
            capture_output=True, text=True, errors="replace",
        )
        if check:
            assert result.returncode == 0, result.stderr
        return result

    def write(self, name, content):
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))

    def add(self, name, content):
        self.write(name, content)
        self.git("add", "-f", name)

    def commit(self, *args):
        return self.git("commit", "-m", "test", *args, check=False)

    def commit_unchecked(self, name, content, message="test"):
        self.add(name, content)
        self.git("commit", "-q", "--no-verify", "-m", message)

    def head(self):
        return self.git("rev-parse", "HEAD").stdout.strip()

    def commit_count(self):
        return int(self.git("rev-list", "--count", "--all").stdout)

    def scan(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(self.path / "tools" / "secret_scan.py"), *args],
            cwd=cwd or self.path, env=self.env,
            capture_output=True, text=True, errors="replace",
        )


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo with space"
    path.mkdir()
    r = Repo(path)
    r.git("init", "-q")
    r.git("config", "user.name", "Test")
    r.git("config", "user.email", "test@example.invalid")
    for relative in (".githooks/pre-commit", "tools/secret_scan.py"):
        source = ROOT / relative
        if source.exists():
            (path / relative).parent.mkdir(exist_ok=True)
            shutil.copy(source, path / relative)
            (path / relative).chmod(0o755)
    r.git("config", "core.hooksPath", ".githooks")
    return r


def assert_blocked(repo, result, commits=0):
    assert result.returncode != 0, result.stdout + result.stderr
    assert repo.commit_count() == commits
    assert FAKE not in result.stdout + result.stderr


def test_clean_commit_succeeds(repo):
    repo.add("ok.txt", "nothing to see\n")
    result = repo.commit()
    assert result.returncode == 0, result.stderr
    assert repo.commit_count() == 1


def test_commit_with_fake_key_is_rejected(repo):
    repo.add("config.py", f'TOKEN = "{FAKE}"\n')
    result = repo.commit()
    assert_blocked(repo, result)
    assert "config.py:1" in result.stderr


@pytest.mark.parametrize("name", [".env", "server.pem", "plan.private.md"])
def test_force_added_forbidden_file_is_rejected(repo, name):
    repo.add(name, "harmless\n")
    result = repo.commit()
    assert_blocked(repo, result)
    assert name in result.stderr


def test_staged_content_is_scanned_not_working_tree(repo):
    repo.add("a.txt", FAKE + "\n")
    repo.write("a.txt", "cleaned but not staged\n")
    assert_blocked(repo, repo.commit())


def test_unstaged_secret_does_not_block(repo):
    repo.add("a.txt", "clean\n")
    repo.write("a.txt", FAKE + "\n")
    result = repo.commit()
    assert result.returncode == 0, result.stderr


def test_partial_commit_is_scanned(repo):
    repo.add("a.txt", "clean\n")
    assert repo.commit().returncode == 0
    repo.write("a.txt", FAKE + "\n")
    assert_blocked(repo, repo.commit("a.txt"), commits=1)


def test_renaming_to_forbidden_name_is_rejected(repo):
    repo.add("a.txt", "some stable content\n")
    assert repo.commit().returncode == 0
    repo.git("mv", "a.txt", "a.key")
    assert_blocked(repo, repo.commit(), commits=1)


def test_deleting_a_forbidden_file_is_allowed(repo):
    repo.commit_unchecked(".env", "harmless\n")
    repo.git("rm", "-q", ".env")
    result = repo.commit()
    assert result.returncode == 0, result.stderr


def test_commit_blocked_when_python_is_unavailable(repo, tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("python", "python3", "py"):
        (stubs / name).write_bytes(b"#!/bin/sh\nexit 1\n")
        (stubs / name).chmod(0o755)
    repo.env["PATH"] = str(stubs) + os.pathsep + repo.env["PATH"]
    repo.add("ok.txt", "nothing to see\n")
    result = repo.commit()
    assert_blocked(repo, result)
    assert "no usable Python" in result.stderr


def test_commit_blocked_when_scanner_is_missing(repo):
    (repo.path / "tools" / "secret_scan.py").unlink(missing_ok=True)
    repo.add("ok.txt", "nothing to see\n")
    assert_blocked(repo, repo.commit())


def test_all_mode_scans_tracked_files(repo):
    repo.add("ok.txt", "clean\n")
    repo.write("untracked.txt", FAKE + "\n")
    assert repo.scan("--all").returncode == 0
    repo.add("sub/a.txt", FAKE + "\n")
    (repo.path / "other").mkdir()
    result = repo.scan("--all", cwd=repo.path / "other")
    assert result.returncode == 1
    assert "sub/a.txt:1" in result.stderr
    assert FAKE not in result.stdout + result.stderr


def test_range_mode_finds_secret_that_was_later_removed(repo):
    repo.commit_unchecked("a.txt", "clean\n")
    base = repo.head()
    repo.commit_unchecked("a.txt", FAKE + "\n")
    repo.commit_unchecked("a.txt", "clean again\n")
    assert repo.scan("--all").returncode == 0
    result = repo.scan("--range", f"{base}..HEAD")
    assert result.returncode == 1
    assert "a.txt:1" in result.stderr
    assert FAKE not in result.stdout + result.stderr


def test_range_mode_excludes_older_commits_and_includes_root(repo):
    repo.commit_unchecked("a.txt", FAKE + "\n")
    base = repo.head()
    repo.commit_unchecked("a.txt", "clean\n")
    assert repo.scan("--range", f"{base}..HEAD").returncode == 0
    assert repo.scan("--range", "HEAD").returncode == 1


def test_range_mode_scans_commit_messages(repo):
    repo.commit_unchecked("a.txt", "clean\n", message="oops " + FAKE)
    result = repo.scan("--range", "HEAD")
    assert result.returncode == 1
    assert FAKE not in result.stdout + result.stderr


def test_range_mode_scans_content_added_by_a_merge(repo):
    repo.commit_unchecked("a.txt", "base\n")
    trunk = repo.git("branch", "--show-current").stdout.strip()
    repo.git("checkout", "-q", "-b", "side")
    repo.commit_unchecked("b.txt", "side\n")
    repo.git("checkout", "-q", trunk)
    repo.commit_unchecked("c.txt", "trunk\n")
    base = repo.head()
    repo.git("merge", "-q", "--no-ff", "--no-commit", "side")
    repo.commit_unchecked("d.txt", FAKE + "\n")
    assert repo.scan("--range", f"{base}..HEAD").returncode == 1


@pytest.mark.parametrize("rng", ["no-such-ref..HEAD", "--all", ""])
def test_bad_range_fails_closed(repo, rng):
    repo.commit_unchecked("a.txt", "clean\n")
    assert repo.scan(f"--range={rng}").returncode == 2


def test_outside_a_repository_fails_closed(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    repo.env["GIT_CEILING_DIRECTORIES"] = str(tmp_path)
    assert repo.scan("--staged", cwd=outside).returncode == 2


# --- gitleaks ---------------------------------------------------------------


@pytest.mark.parametrize("status, passed", [(0, True), (1, False), (126, False)])
def test_gitleaks_runs_when_on_path(monkeypatch, status, passed):
    # gitleaks is an optional external program: fake only that process.
    scan = scanner()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, status)

    monkeypatch.setattr(scan.shutil, "which", lambda name: "fake-gitleaks")
    monkeypatch.setattr(scan.subprocess, "run", fake_run)
    assert scan.run_gitleaks(ROOT, "staged") is passed
    assert calls[0][0] == "fake-gitleaks"
    assert "--redact" in calls[0] and "--staged" in calls[0]


def test_gitleaks_is_optional(monkeypatch):
    scan = scanner()
    monkeypatch.setattr(scan.shutil, "which", lambda name: None)
    assert scan.run_gitleaks(ROOT, "staged") is True
