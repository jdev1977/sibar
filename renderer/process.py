"""Run one render in a process of its own, inside a memory cap.

The child is ``renderer.worker``. It says its process id and then waits, so it
is in the cap before it starts the Playwright driver or a browser. Whatever a
page makes any of them hold, this process only ever reads the child's short
reply.
"""

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from renderer.limits import ProcessLimit

ROOT = Path(__file__).resolve().parents[1]
STARTUP = 60.0  # seconds for the child to say it is there
REPLY = b"reply "


class WorkerFailed(Exception):
    """The render process could not be started inside its cap."""


@dataclass(frozen=True)
class Run:
    reply: Optional[dict]  # None: the child ended without one
    timed_out: bool
    exit_code: Optional[int]
    memory_limited: bool
    peak_mb: int
    refused_memory: bool


def run_worker(request, memory_mb, deadline):
    """Send ``request`` to a new render process, allowed ``memory_mb`` for all
    its processes and ``deadline`` seconds; return a :class:`Run`."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT), environment.get("PYTHONPATH")]))
    child = subprocess.Popen(
        [sys.executable, "-m", "renderer.worker"], cwd=ROOT, env=environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt")
    limit, output, timed_out = None, b"", False
    try:
        watchdog = threading.Timer(STARTUP, child.kill)
        watchdog.start()
        try:
            hello = child.stdout.readline().split()
        finally:
            watchdog.cancel()
        if len(hello) != 2 or hello[0] != b"ready":
            raise WorkerFailed("the render process did not start")
        try:
            # The id the child gave: in a virtual environment on Windows,
            # ``child`` is only the launcher of the real interpreter.
            limit = ProcessLimit(int(hello[1]), memory_mb)
        except OSError as error:
            raise WorkerFailed(f"the memory cap could not be applied: {error}"
                               ) from error
        try:
            output, _ = child.communicate(
                json.dumps(request).encode("ascii") + b"\n", timeout=deadline)
        except subprocess.TimeoutExpired:
            timed_out = True
            limit.end()
            child.kill()
            output, _ = child.communicate()
    finally:
        if limit is not None:
            limit.end()
        if child.poll() is None:
            child.kill()
        child.wait()
        for stream in (child.stdin, child.stdout):
            try:
                stream.close()
            except OSError:
                pass  # the child went without reading
    replies = [line for line in output.splitlines() if line.startswith(REPLY)]
    try:
        reply = json.loads(replies[-1][len(REPLY):]) if replies else None
    except ValueError:  # cut off while being written
        reply = None
    return Run(reply, timed_out, child.returncode, limit.memory_limited,
               limit.peak_mb, limit.refused_memory)
