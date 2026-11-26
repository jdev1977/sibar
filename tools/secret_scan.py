"""Block secrets from being committed. Standard library only.

Usage (see docs/secrets.md):
    python tools/secret_scan.py [--staged]     what is about to be committed
    python tools/secret_scan.py --all          every tracked file (index content)
    python tools/secret_scan.py --range A..B   every commit in a git range
        [--exclude-remote NAME]                except what that remote has

Exit status: 0 clean, 1 findings, 2 the scan could not run.
Matched secrets are never printed.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

PROVIDER_PATTERNS = {
    # Anthropic, OpenAI, OpenRouter, DeepSeek and others using "sk-"
    "API key (sk- prefix)": re.compile(
        r"(?<![A-Za-z0-9])sk-"
        r"(?:(?:ant|proj|svcacct|admin|or)-[A-Za-z0-9_-]{20,}|[A-Za-z0-9]{20,})"
    ),
    "Google API key": re.compile(r"(?<![A-Za-z0-9])AIza[A-Za-z0-9_-]{35}"),
    "xAI API key": re.compile(r"(?<![A-Za-z0-9])xai-[A-Za-z0-9]{20,}"),
    "Vercel AI Gateway key": re.compile(r"(?<![A-Za-z0-9])vck_[A-Za-z0-9]{20,}"),
}

PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")

# NAME_API_KEY followed by an assignment: shell, dotenv, YAML, JSON, code.
ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9])(?P<name>(?:[A-Z0-9_]*_)?API_KEY)(?![A-Za-z0-9_])"
    r"[\"']?\]?[ \t]*"
    r"(?::=|\?=|\+=|=(?!=)|:(?!-\}|[:=?]))"
    r"(?=[ \t]*(?P<value>.*))"
)

# A literal default in a lookup: getenv, .get or .setdefault.
LITERAL_DEFAULT = re.compile(
    r"(?:getenv|\.get|\.setdefault)\(\s*"
    r"[\"'](?P<name>(?:[A-Z0-9_]*_)?API_KEY)[\"']\s*,\s*(?:default\s*=\s*)?"
    r"(?P<literal>(?P<quote>[\"'])(?:(?!(?P=quote)).)+(?P=quote))"
)

# Private key files by their usual OpenSSH names (the .pub halves are fine).
SSH_KEY_NAME = re.compile(r"id_(?:rsa|dsa|ecdsa|ed25519)(?:_sk)?(?:\..*)?(?<!\.pub)")

# Right-hand sides that cannot be a literal secret.
SAFE_VALUE = re.compile(
    r"$|#"
    r"|(?P<quote>[\"'])(?P=quote)(?![^\s,;:)}\]])"  # empty string
    r"|`(?=$|[\s,.;:)])"  # empty value at the end of Markdown inline code
    r"|[\"']?(?:"
    r"(?:\$\{\{[^}]*\}\}"  # CI expression
    r"|\$\{[A-Za-z_]\w*(?::-)?\}|\$(?:env:)?[A-Za-z_]\w*|%\w+%"  # variables
    r"|<[^<>]*>|\.\.\.|None|null)"  # placeholders
    r"(?=$|[\s\"',;)}\]])"
    r"|os\.environ|(?:os\.)?getenv\(|process\.env[.\[])"
)

ALLOW_MARKER = "secret-scan: allow"
SUBMODULE_MODE = "160000"


class ScanError(Exception):
    """The scan could not be completed, so nothing can be declared clean."""


class Finding(NamedTuple):
    path: str
    line: int  # 0 when the finding is about the file name
    rule: str
    commit: str = ""

    def __str__(self):
        where = f"{self.path}:{self.line}" if self.line else self.path
        suffix = f" (commit {self.commit[:12]})" if self.commit else ""
        return f"{where}: {self.rule}{suffix}"


def redact(text):
    for pattern in PROVIDER_PATTERNS.values():
        text = pattern.sub("<redacted>", text)
    return text


def forbidden_filename(path):
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name == ".env.example":
        return False
    return (
        name == ".envrc"
        or name.startswith(".env.")
        or ".pem." in name
        or name.endswith((".env", ".key", ".pem", ".p12", ".pfx", ".private.md"))
        or SSH_KEY_NAME.fullmatch(name) is not None
    )


def scan_text(path, text, commit=""):
    findings = []
    shown = redact(path)
    for number, line in enumerate(text.split("\n"), start=1):
        line = line.rstrip("\r")
        rules = [
            rule for rule, pattern in PROVIDER_PATTERNS.items() if pattern.search(line)
        ]
        if PRIVATE_KEY.search(line):
            rules.append("private key block")
        if not rules and ALLOW_MARKER not in line:
            rules = [
                f"non-empty value assigned to {match['name']}"
                for match in ASSIGNMENT.finditer(line)
                if not SAFE_VALUE.match(match["value"])
            ]
            rules += [
                f"non-empty default for {match['name']}"
                for match in LITERAL_DEFAULT.finditer(line)
                if not SAFE_VALUE.match(match["literal"])
            ]
        findings.extend(Finding(shown, number, rule, commit) for rule in rules)
    return findings


def scan_blob(path, data, commit=""):
    # latin-1 never fails; dropping NULs makes UTF-16 text readable.
    return scan_text(path, data.decode("latin-1").replace("\x00", ""), commit)


def git(root, *args, stdin=None):
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        input=stdin,
        capture_output=True,
        env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if result.returncode != 0:
        message = redact(result.stderr.decode("utf-8", "replace").strip())
        raise ScanError(f"git {args[0]} failed: {message}")
    return result.stdout


def parse_raw_diff(output):
    """Yield (mode, object id, path) from `git diff --raw -z --no-renames`."""
    fields = output.split(b"\0")
    for meta, path in zip(fields[0::2], fields[1::2]):
        _, mode, _, object_id, _ = meta.decode("ascii").split()
        yield mode, object_id, path.decode("utf-8", "surrogateescape")


RAW_DIFF = ("--raw", "-z", "--no-renames", "--no-abbrev", "--diff-filter=d")


def staged_entries(root):
    output = git(root, "diff", "--cached", "--no-relative", *RAW_DIFF)
    return [(*entry, "") for entry in parse_raw_diff(output)]


def tracked_entries(root):
    entries = []
    for record in git(root, "ls-files", "-s", "-z").split(b"\0"):
        if record:
            meta, path = record.split(b"\t", 1)
            mode, object_id, _ = meta.decode("ascii").split()
            entries.append((mode, object_id, path.decode("utf-8", "surrogateescape"), ""))
    return entries


def exclusion(exclude_remote):
    """Revision options leaving out what a remote's tracking refs contain."""
    return ["--not", f"--remotes={exclude_remote}"] if exclude_remote else []


def range_commits(root, revisions, exclude_remote=None):
    if not revisions or revisions.startswith("-"):
        raise ScanError("--range needs a revision or A..B range")
    excluded = exclusion(exclude_remote)
    if excluded:
        excluded.append("--not")  # the revisions that follow are included again
    output = git(root, "rev-list", *excluded, "--end-of-options", revisions, "--")
    return output.decode("ascii").split()


def commit_entries(root, commits):
    """Everything each commit introduced, including content removed again later."""
    entries = {}
    for commit in commits:
        # -m: compare merges with every parent; --root: include the first commit
        output = git(
            root, "diff-tree", "-r", "-m", "--root", "--no-commit-id", *RAW_DIFF, commit
        )
        for mode, object_id, path in parse_raw_diff(output):
            entries.setdefault((object_id, path), (mode, object_id, path, commit))
    return list(entries.values())


def read_objects(root, object_ids):
    wanted = list(dict.fromkeys(object_ids))
    if not wanted:
        return {}
    output = git(
        root, "cat-file", "--batch", stdin="".join(f"{i}\n" for i in wanted).encode()
    )
    objects, position = {}, 0
    for object_id in wanted:
        end = output.index(b"\n", position)
        header = output[position:end].split()
        if len(header) != 3:
            raise ScanError(f"cannot read git object {object_id}")
        start, size = end + 1, int(header[2])
        objects[object_id] = output[start : start + size]
        position = start + size + 1
    return objects


def scan_repository(root, mode, revisions=None, exclude_remote=None):
    commits = []
    if mode == "range":
        commits = range_commits(root, revisions, exclude_remote)
        entries = commit_entries(root, commits)
    elif mode == "all":
        entries = tracked_entries(root)
    else:
        entries = staged_entries(root)

    files = [entry for entry in entries if entry[0] != SUBMODULE_MODE]
    objects = read_objects(root, [entry[1] for entry in files] + commits)

    findings = [
        Finding(redact(path), 0, "forbidden file name", commit)
        for _, _, path, commit in entries
        if forbidden_filename(path)
    ]
    for _, object_id, path, commit in files:
        findings.extend(scan_blob(path, objects[object_id], commit))
    for commit in commits:  # commit messages are pushed too
        findings.extend(scan_blob(f"commit object {commit[:12]}", objects[commit]))
    return findings


def run_gitleaks(root, mode, revisions=None, exclude_remote=None):
    """Run gitleaks as a second opinion if installed. True means it passed."""
    executable = shutil.which("gitleaks")
    if executable is None:
        return True

    def passes(directory, *arguments):
        command = [executable, *arguments, "--redact", "--no-banner", "--source", "."]
        return subprocess.run(command, cwd=directory).returncode == 0

    if mode == "staged":
        return passes(root, "protect", "--staged")
    if mode == "range":
        log_opts = " ".join([revisions, *exclusion(exclude_remote)])
        return passes(root, "detect", f"--log-opts={log_opts}")
    # Scan the tracked files themselves: not history, and not untracked files
    # such as a local .env. So give gitleaks a copy of the index.
    with tempfile.TemporaryDirectory() as copy:
        git(root, "checkout-index", "--all", f"--prefix={Path(copy).as_posix()}/")
        return passes(copy, "detect", "--no-git")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--staged", action="store_true", help="staged changes (default)")
    modes.add_argument("--all", action="store_true", help="all tracked files")
    modes.add_argument("--range", metavar="A..B", help="all commits in a git range")
    parser.add_argument(
        "--exclude-remote",
        metavar="NAME",
        help="with --range: skip commits that remote already has",
    )
    args = parser.parse_args(argv)
    if args.exclude_remote is not None and args.range is None:
        parser.error("--exclude-remote requires --range")
    if args.range is not None:
        mode = "range"
    else:
        mode = "all" if args.all else "staged"
    sys.stderr.reconfigure(errors="backslashreplace")

    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True
        )
        if top.returncode != 0:
            raise ScanError("not inside a git work tree")
        root = top.stdout.decode("utf-8").rstrip("\r\n")
        findings = scan_repository(root, mode, args.range, args.exclude_remote)
        gitleaks_passed = run_gitleaks(root, mode, args.range, args.exclude_remote)
    except ScanError as error:
        print(f"secret-scan: error: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # fail closed, without echoing scanned data
        print(f"secret-scan: error: {type(error).__name__}", file=sys.stderr)
        return 2

    if not findings and gitleaks_passed:
        return 0
    for finding in findings:
        print(finding, file=sys.stderr)
    if not gitleaks_passed:
        print("gitleaks reported a problem (see its output above)", file=sys.stderr)
    print("secret-scan: blocked. See docs/secrets.md.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
