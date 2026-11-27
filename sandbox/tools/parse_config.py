"""Parse-checks configuration files, inside the sandbox (T2.7).

``python -I parse_config.py <result file> <folder> <file> ...``: for each
YAML, TOML or JSON file, whether it parses, and for workflow-like YAML the
commands it would run (``run:`` and ``script:`` entries). The files are
untrusted: they are parsed in the sandbox, never outside it.
"""

import json
import os
import sys

MAX_BYTES = 1 << 20


def commands(node, found):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("run", "script", "before_script", "after_script") and len(found) < 50:
                if isinstance(value, str):
                    found.append(value[:300])
                elif isinstance(value, list):
                    found.extend(str(item)[:300] for item in value[:20])
            commands(value, found)
    elif isinstance(node, list):
        for item in node:
            commands(item, found)
    return found


def check(folder, relative):
    path = os.path.join(folder, *relative.split("/"))
    entry = {"path": relative}
    try:
        if os.path.getsize(path) > MAX_BYTES:
            entry["error"] = "too large"
            return entry
        with open(path, "rb") as handle:
            data = handle.read()
        suffix = relative.rsplit(".", 1)[-1].lower()
        if suffix in ("yml", "yaml"):
            import yaml

            documents = list(yaml.safe_load_all(data))
            entry["parses"] = True
            found = []
            for document in documents:
                commands(document, found)
            entry["commands"] = found
        elif suffix == "toml":
            import tomllib

            tomllib.loads(data.decode("utf-8"))
            entry["parses"] = True
        else:
            json.loads(data)
            entry["parses"] = True
    except Exception as error:
        entry["parses"] = False
        entry["error"] = f"{type(error).__name__}: {error}"[:300]
    return entry


def main():
    result, folder, files = sys.argv[1], sys.argv[2], sys.argv[3:]
    with open(result, "w", encoding="utf-8") as handle:
        json.dump([check(folder, relative) for relative in files[:100]], handle)


if __name__ == "__main__":
    main()
