"""Helpers for the sandbox tests: the runtime check, probes, local listeners.

Every probe is this repository's own code, bounded so that it stops by
itself well before it could hurt a machine with little free memory or disk,
even with the boundary it tests turned off. Listeners bind to 127.0.0.1 only,
and no probe names any host but this machine.
"""

import json
import os
import socket
import threading

import pytest

from sandbox.box import Box, Isolation, Limits

# Small limits, so a test that fails cannot cost much.
SMALL = Limits(seconds=30, cpu_seconds=30, memory_mb=256, processes=8, disk_mb=32,
               files=2000, write_mb=256, free_disk_mb=512)
OFF = Isolation(appcontainer=False, restricted_token=False, desktop=False,
                job_limits=False, watch=False)


def require_runtime():
    if os.name != "nt":
        pytest.skip("the sandbox runs on Windows only")
    from sandbox import runtime

    try:
        runtime.check(runtime.default_root())
    except runtime.RuntimeMissing as error:
        pytest.skip(f"no sandbox runtime ({error})")


def run_probe(box, code, arguments=None, limits=None):
    """Run ``code`` as ``probe.py`` in ``box``; return (the JSON object it
    printed last, or None, and the RunResult)."""
    (box.app / "probe.py").write_text(code, encoding="utf-8")
    result = box.run([box.python(), "probe.py", json.dumps(arguments or {})],
                     limits=limits)
    lines = result.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        answer = json.loads(lines[-1]) if lines else None
    except ValueError:
        answer = None
    return answer, result


def probe(code, arguments=None, limits=SMALL, isolation=Isolation(), run_limits=None):
    with Box(limits=limits, isolation=isolation) as box:
        return run_probe(box, code, arguments, run_limits)


class Listener:
    """A TCP and a UDP listener on 127.0.0.1 that record what reaches them."""

    def __init__(self, udp_port=0):
        self.heard = []
        self.tcp = socket.create_server(("127.0.0.1", 0))
        self.tcp.settimeout(0.2)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", udp_port))
        self.udp.settimeout(0.2)
        self.tcp_port = self.tcp.getsockname()[1]
        self.udp_port = self.udp.getsockname()[1]
        self._stop = False
        self._threads = [threading.Thread(target=self._accept, daemon=True),
                         threading.Thread(target=self._receive, daemon=True)]
        for thread in self._threads:
            thread.start()

    def _accept(self):
        while not self._stop:
            try:
                connection, _ = self.tcp.accept()
            except OSError:
                continue
            self.heard.append("tcp")
            connection.close()

    def _receive(self):
        while not self._stop:
            try:
                data, _ = self.udp.recvfrom(4096)
            except OSError:
                continue
            self.heard.append(("udp", data[:64]))

    def close(self):
        self._stop = True
        for thread in self._threads:
            thread.join(2)
        self.tcp.close()
        self.udp.close()
