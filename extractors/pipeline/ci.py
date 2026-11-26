"""The build service, triggers, test matrix, tools and limits of a
continuous integration file.

Files are read as YAML with limits: a file that is too large, nests too much,
holds many aliases or does not parse leaves the features read from it
undetermined (``null``).
"""

import re

import yaml

from extractors.base import Extractor
from extractors.common.response import NO_INPUT, get_doc, result

MAX_YAML = 100_000      # characters of one YAML file
MAX_ALIASES = 20        # merge keys over aliases grow exponentially
MAX_BRACKETS = 2_000
MAX_NODES = 20_000
MAX_FILES = 20
_ALIAS = re.compile(r"(?:^|[\s\[{,])\*[\w-]", re.M)
_BY_PATH = (
    ("github-actions", re.compile(r"(?:^|/)\.?github/workflows/[^/]{1,100}\.ya?ml$")),
    ("gitlab-ci", re.compile(r"(?:^|/)\.?gitlab-ci\.yml$")),
    ("circleci", re.compile(r"(?:^|/)\.?circleci/config\.ya?ml$")),
    ("azure-pipelines", re.compile(r"(?:^|/)\.?azure-pipelines[\w.-]{0,40}\.ya?ml$")),
    ("travis", re.compile(r"(?:^|/)\.?travis\.yml$")),
    ("bitbucket", re.compile(r"(?:^|/)bitbucket-pipelines\.yml$")),
    ("jenkins", re.compile(r"(?:^|/)jenkinsfile$")),
)
# Marks that follow one another, each found by its own search. One pattern with
# a gap between them would retry every pairing: cubic time for three marks.
_JENKINS = (re.compile(r"^pipeline ?\{", re.M), re.compile(r"\bagent\b"))
_GITHUB_TEXT = (re.compile(r"^on:", re.M), re.compile(r"^jobs:", re.M),
                re.compile(r"\bruns-on:"))
_TRIGGERS = {
    "push": "push", "pull_request": "pull-request",
    "pull_request_target": "pull-request", "schedule": "schedule",
    "workflow_dispatch": "manual", "release": "release", "merge_group": "merge-queue",
    "workflow_call": "called",
}
_OS = (("linux", re.compile(r"ubuntu|linux|debian|alpine", re.IGNORECASE)),
       ("windows", re.compile(r"windows|win-", re.IGNORECASE)),
       ("macos", re.compile(r"macos|mac-os|osx", re.IGNORECASE)))
_TOOLS = tuple((name, re.compile(pattern)) for name, pattern in (
    ("go-test", r"\bgo test\b"), ("go-vet", r"\bgo vet\b"),
    ("gofmt", r"\bgofmt\b|\bgo fmt\b|\bgofumpt\b"), ("golangci-lint", r"golangci-lint"),
    ("staticcheck", r"staticcheck"), ("go-build", r"\bgo build\b"),
    ("pytest", r"\bpytest\b"), ("unittest", r"-m unittest\b"), ("tox", r"\btox\b"),
    ("nox", r"\bnox\b"), ("ruff", r"\bruff\b"), ("flake8", r"\bflake8\b"),
    ("pylint", r"\bpylint\b"), ("black", r"\bblack\b[ -]"), ("mypy", r"\bmypy\b"),
    ("pyright", r"\bpyright\b"),
    ("coverage", r"\bcoverage (?:run|report|xml)\b|--cov\b|-coverprofile\b|-cover\b|"
                 r"\bgo tool cover\b|codecov|coveralls"),
    ("npm-test", r"\b(?:npm|pnpm|yarn)(?: run)? test\b"), ("eslint", r"\beslint\b"),
    ("prettier", r"\bprettier\b"), ("tsc", r"\btsc\b"),
    ("npm-build", r"\b(?:npm|pnpm|yarn)(?: run)? build\b"),
    ("cargo-test", r"\bcargo test\b"), ("cargo-clippy", r"\bcargo clippy\b"),
    ("cargo-fmt", r"\bcargo fmt\b"),
))
_COMMAND_KEYS = ("run", "script", "before_script", "command", "uses", "bash", "pwsh",
                 "powershell", "task")


def _load(text):
    """The document of a YAML text, or None where it is not safely read."""
    if (len(text) > MAX_YAML or len(_ALIAS.findall(text)) > MAX_ALIASES
            or text.count("[") + text.count("{") > MAX_BRACKETS):
        return None
    try:
        return yaml.safe_load(text)
    except Exception:  # noqa: BLE001 - hostile or broken YAML in any way
        return None


def _walk(node):
    """Every ``(key, value)`` in a document, each object visited once."""
    seen, stack, count = set(), [node], 0
    while stack and count < MAX_NODES:
        item = stack.pop()
        if not isinstance(item, (dict, list)) or id(item) in seen:
            continue
        seen.add(id(item))
        pairs = list(item.items()) if isinstance(item, dict) else \
            [(None, value) for value in item]
        for key, value in pairs[:MAX_NODES]:
            count += 1
            yield key, value
            stack.append(value)


def _service_of(document):
    if not isinstance(document, dict):
        return None
    jobs = document.get("jobs")
    keys = {key for key, _ in _walk(document) if isinstance(key, str)}
    if ("on" in document or True in document) and isinstance(jobs, dict) \
            and keys & {"runs-on", "steps", "uses"}:
        return "github-actions"
    if str(document.get("version")) in ("2", "2.1") and isinstance(jobs, dict) \
            and keys & {"docker", "machine", "macos", "executor", "steps"}:
        return "circleci"
    if "pool" in keys and keys & {"trigger", "steps", "stages", "pr"}:
        return "azure-pipelines"
    if "pipelines" in document and "step" in keys:
        return "bitbucket"
    if any(isinstance(v, dict) and "script" in v for v in document.values()):
        return "gitlab-ci"
    if "language" in document and "script" in document:
        return "travis"
    return None


def _in_order(patterns, text):
    """Whether each pattern is found after the one before it: linear."""
    position = 0
    for pattern in patterns:
        found = pattern.search(text, position)
        if not found:
            return False
        position = found.end()
    return True


def _text(value):
    """The strings of a command value."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(v for v in value[:1000] if isinstance(v, str))
    return ""


def _scalar(value):
    if isinstance(value, bool) or value is None:
        return str(value).lower()
    return str(value)[:60] if isinstance(value, (str, int, float)) else None


def _github_triggers(document):
    on = document.get("on", document.get(True))
    if isinstance(on, str):
        names = {on: None}
    elif isinstance(on, list):
        names = {n: None for n in on if isinstance(n, str)}
    elif isinstance(on, dict):
        names = on
    else:
        return set()
    found = {_TRIGGERS.get(str(name), "other") for name in names}
    push = names.get("push")
    if isinstance(push, dict) and push.get("tags"):
        found.add("tag")
        if not push.get("branches") and not push.get("paths"):
            found.discard("push")
    return found


def _other_triggers(service, document, text):
    if service == "gitlab-ci":
        found = {name for name, pattern in (
            ("pull-request", r"merge_request"), ("tag", r"CI_COMMIT_TAG|\btags\b ?$"),
            ("schedule", r"\bschedules?\b"),
            ("push", r"CI_COMMIT_BRANCH|[\"']push[\"']"))
            if re.search(pattern, text, re.M)}
        return found or None
    if service == "azure-pipelines" and isinstance(document, dict):
        found = {name for key, name in (("trigger", "push"), ("pr", "pull-request"),
                                        ("schedules", "schedule"))
                 if document.get(key) not in (None, "none")}
        return found or None
    return None


def _matrices(document):
    """Every matrix mapping: ``strategy.matrix`` and ``parallel.matrix``."""
    for key, value in _walk(document):
        if key == "matrix":
            for entry in value if isinstance(value, list) else [value]:
                if isinstance(entry, dict):
                    yield entry


def _read(service, document, text):
    triggers = _github_triggers(document) if service == "github-actions" \
        else _other_triggers(service, document, text)
    keys, values = set(), set()
    systems = set()
    for matrix in _matrices(document):
        entries = list(matrix.items())
        for item in matrix.get("include") or [] if isinstance(
                matrix.get("include"), list) else []:
            if isinstance(item, dict):
                entries += [(k, [v]) for k, v in item.items()]
        for key, listed in entries[:200]:
            key = str(key)[:60]
            if key in ("include", "exclude"):
                continue
            keys.add(key)
            for value in listed if isinstance(listed, list) else [listed]:
                shown = _scalar(value)
                if shown is None:
                    continue
                matched = {name for name, pattern in _OS if pattern.search(shown)}
                if matched:
                    systems |= matched
                else:
                    values.add(f"{key}={shown}")
    commands, timeout, cancel = [], False, False
    for key, value in _walk(document):
        if key in _COMMAND_KEYS:
            commands.append(_text(value))
        if key in ("runs-on", "vmImage", "image", "os"):
            shown = _text(value)
            systems |= {name for name, pattern in _OS if pattern.search(shown)}
        if key in ("timeout-minutes", "timeout", "timeoutInMinutes",
                   "no_output_timeout"):
            timeout = True
        if key in ("cancel-in-progress", "interruptible", "autoCancel") \
                and value not in (False, None, "false"):
            cancel = True
    joined = "\n".join(commands)
    return {
        "triggers": triggers, "matrix_keys": keys, "matrix_os": systems,
        "matrix_versions": values,
        "ci_tools": {name for name, pattern in _TOOLS if pattern.search(joined)},
        "timeout": timeout, "cancel": cancel,
    }


def ci(inputs):
    doc = get_doc(inputs)
    if not any(f.language not in (None, "markdown", "csv") for f in doc.files):
        return dict(NO_INPUT)
    found, unread = [], False
    candidates = [f for f in doc.files if f.language in ("yaml", "groovy")]
    for source in candidates[:MAX_FILES]:
        path = source.path.lower()
        service = next((name for name, p in _BY_PATH if p.search(path)), None)
        if source.language == "groovy":
            if service or _in_order(_JENKINS, source.text):
                found.append(("jenkins", None, source.text))
            continue
        document = _load(source.text)
        if document is None:
            if not service and _in_order(_GITHUB_TEXT, source.text[:MAX_YAML]):
                service = "github-actions"
            unread = unread or not service
        elif not service:
            service = _service_of(document)
        if service:
            found.append((service, document, source.text))
    lists = ("triggers", "matrix_keys", "matrix_os", "matrix_versions", "ci_tools")
    if not found:
        service = None if unread else "none"
        empty = None if unread else []
        flag = None if unread else "no-workflow"
        return result(doc, {"ci_service": service, **dict.fromkeys(lists, empty),
                            "timeout": flag, "cancel_superseded": flag})
    services = {service for service, _, _ in found}
    values = {"ci_service": services.pop() if len(services) == 1 else "several"}
    readings = [_read(service, document, text) if isinstance(document, dict) else None
                for service, document, text in found]
    complete = all(reading is not None for reading in readings)
    for name in lists:
        parts = [r[name] for r in readings if r is not None]
        known = complete and all(part is not None for part in parts)
        values[name] = sorted(set().union(*parts))[:200] if known else None
    for name, key in (("timeout", "timeout"), ("cancel_superseded", "cancel")):
        hit = any(r[key] for r in readings if r is not None)
        values[name] = "set" if hit else "not-set" if complete else None
    return result(doc, values)


EXTRACTOR = Extractor("pipeline.ci", "2", "pipeline", ci,
                      "build service, triggers, test matrix and tools of a CI file")
