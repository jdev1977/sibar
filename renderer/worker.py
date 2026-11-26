"""The render process (see ``renderer.process``): makes one image.

It prints ``ready <process id>``, reads one request line and prints one reply
line. It starts nothing before the request arrives.
"""

import datetime
import json
import os
import sys
from dataclasses import asdict


def _answer(request):
    from renderer.browser import (
        BrowserUnavailable, Settings, Variant, render_here,
    )

    values = dict(request["settings"])
    values["clock"] = datetime.datetime.fromisoformat(values["clock"])
    values["variants"] = tuple(Variant(**v) for v in values["variants"])
    try:
        result = render_here(
            request["root"], request["entry"], request["out"], Settings(**values),
            request["files"])
    except BrowserUnavailable as error:
        return {"unavailable": str(error)}
    except Exception as error:
        text = str(error).splitlines()[0] if str(error) else ""
        return {"error": f"{type(error).__name__}: {text}"
                .replace(request["root"], "<folder>")[:300]}
    return {"page": asdict(result)}


def main():
    print(f"ready {os.getpid()}", flush=True)
    line = sys.stdin.readline()
    if line:
        print("reply " + json.dumps(_answer(json.loads(line))), flush=True)


if __name__ == "__main__":
    main()
