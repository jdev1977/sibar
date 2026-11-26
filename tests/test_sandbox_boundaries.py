"""The sandbox's boundaries (T2.7), each tried by a hostile probe.

Each boundary has a test that the probe is stopped, and a control: the same
probe with the layer that stops it turned off (``Isolation``) gets through,
which shows the first test would fail if the boundary were gone. Every probe
is bounded (see tests/sandbox_support.py): with its boundary off it still
stops by itself, takes at most a few hundred megabytes and contacts nothing
but listeners this test opens on 127.0.0.1.
"""

import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path

import pytest

from sandbox_support import OFF, SMALL, Listener, probe, require_runtime, run_probe

pytestmark = pytest.mark.sandbox
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def runtime():
    require_runtime()


# --- Network: no sockets, no loopback, no DNS, no pipes to other processes -------------

NETWORK = """
import json, socket, sys
a = json.loads(sys.argv[1])
out = {}
def attempt(name, action):
    try:
        action()
        out[name] = "ok"
    except OSError as error:
        out[name] = error.winerror or error.errno or str(error)
attempt("tcp", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM).close())
attempt("udp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).close())
attempt("tcp6", lambda: socket.socket(socket.AF_INET6, socket.SOCK_STREAM).close())
attempt("connect", lambda: socket.create_connection(("127.0.0.1", a["tcp"]), 3).close())
def send():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b"probe", ("127.0.0.1", a["udp"]))
    s.close()
attempt("sendto", send)
attempt("resolve", lambda: socket.getaddrinfo("localhost", 80))
print(json.dumps(out))
"""


@pytest.fixture
def listener():
    heard = Listener()
    yield heard
    heard.close()


def test_no_socket_and_no_connection_to_this_machine(listener):
    answer, _ = probe(NETWORK, {"tcp": listener.tcp_port, "udp": listener.udp_port})
    time.sleep(0.5)
    assert all(value != "ok" for value in answer.values()), answer
    assert answer["tcp"] == 10013  # WSAEACCES: refused by Windows
    assert listener.heard == []


def test_control_without_the_appcontainer_the_probe_connects(listener):
    answer, _ = probe(NETWORK, {"tcp": listener.tcp_port, "udp": listener.udp_port},
                      isolation=replace(OFF, restricted_token=True, desktop=True,
                                        job_limits=True, watch=True))
    time.sleep(0.5)
    assert answer["connect"] == "ok" and answer["sendto"] == "ok", answer
    assert "tcp" in listener.heard


DNS = """
import ctypes, json, socket, struct, sys
from ctypes import wintypes
a = json.loads(sys.argv[1])
dns = ctypes.WinDLL("dnsapi")
results = ctypes.c_void_p()
out = {}
# DNS_QUERY_NO_WIRE_QUERY: only the resolver's cache, nothing sent anywhere.
out["cache"] = dns.DnsQuery_W("localhost", 1, 0x10, None, ctypes.byref(results), None)
if a.get("name"):
    class Servers(ctypes.Structure):
        _fields_ = [("count", wintypes.DWORD), ("address", wintypes.DWORD)]
    servers = Servers(1, struct.unpack("<I", socket.inet_aton("127.0.0.1"))[0])
    # Bypass the cache and ask the server: the DNS Client service sends it.
    out["server"] = dns.DnsQuery_W(a["name"], 1, 0x8 | 0x100, ctypes.byref(servers),
                                   ctypes.byref(results), None)
print(json.dumps(out))
"""


def _dns_listener():
    try:
        return Listener(udp_port=53)
    except OSError:
        pytest.skip("port 53 on 127.0.0.1 is in use")


def test_no_name_resolution_and_no_query_sent_on_its_behalf():
    heard = _dns_listener()
    try:
        name = f"sibar-{uuid.uuid4().hex[:8]}.invalid"
        answer, _ = probe(DNS, {"name": name})
        time.sleep(1.0)
    finally:
        heard.close()
    assert answer["cache"] != 0, answer  # the resolver cannot be asked at all
    assert answer["server"] != 0, answer
    assert not any(name.split(".")[0].encode() in item[1] for item in heard.heard
                   if isinstance(item, tuple))


def test_control_without_the_appcontainer_the_query_is_sent():
    heard = _dns_listener()
    try:
        name = f"sibar-{uuid.uuid4().hex[:8]}.invalid"
        answer, _ = probe(DNS, {"name": name}, isolation=OFF)
        time.sleep(1.0)
    finally:
        heard.close()
    assert answer["cache"] == 0, answer
    assert any(name.split(".")[0].encode() in item[1] for item in heard.heard
               if isinstance(item, tuple))


PIPES = """
import ctypes, json, sys
from ctypes import wintypes
a = json.loads(sys.argv[1])
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateFileW.restype = wintypes.HANDLE
k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                          ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
out = {}
for label, name in a["pipes"].items():
    for access, kind in ((0x80000000, "read"), (0x40000000, "write")):
        handle = k.CreateFileW(name, access, 0, None, 3, 0, None)
        error = ctypes.get_last_error()
        if handle not in (None, wintypes.HANDLE(-1).value):
            k.CloseHandle(wintypes.HANDLE(handle))
            out[label + " " + kind] = "opened"
        else:
            out[label + " " + kind] = error
print(json.dumps(out))
"""


@pytest.fixture
def pipes():
    """Named pipes of this test process: default security, a DACL letting
    everyone in, and no DACL at all (anyone at all may open it)."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]

    class Attributes(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p),
                    ("inherit", wintypes.BOOL)]

    names, handles = {}, []
    for label, sddl in (("default", None), ("everyone", "D:(A;;GA;;;WD)"),
                        ("no-dacl", "D:NO_ACCESS_CONTROL")):
        attributes = None
        if sddl:
            descriptor = ctypes.c_void_p()
            assert advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, 1, ctypes.byref(descriptor), None)
            attributes = Attributes(ctypes.sizeof(Attributes), descriptor, False)
        name = f"\\\\.\\pipe\\sibar-test-{label}-{uuid.uuid4().hex[:8]}"
        for _ in range(6):  # an instance for each open
            handle = kernel.CreateNamedPipeW(
                name, 3, 0, 255, 4096, 4096, 0,
                ctypes.byref(attributes) if attributes else None)
            assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
            handles.append(handle)
        names[label] = name
    # The pipe with default security again, by its network paths.
    tail = names["default"].rsplit("\\", 1)[-1]
    names["via localhost"] = r"\\localhost\pipe" + "\\" + tail
    names["via 127.0.0.1"] = r"\\127.0.0.1\pipe" + "\\" + tail
    yield names
    for handle in handles:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def test_pipes_of_other_processes_cannot_be_opened(pipes):
    answer, _ = probe(PIPES, {"pipes": pipes})
    assert len(answer) == 10
    assert all(value == 5 for value in answer.values()), answer  # access denied


def test_control_unsandboxed_the_pipes_open(pipes):
    answer, _ = probe(PIPES, {"pipes": pipes}, isolation=OFF)
    assert all(answer[f"{label} read"] == "opened" for label in pipes), answer


SHARES = """
import json, os, sys
a = json.loads(sys.argv[1])
out = {}
for label, path in (("IPC share", r"\\\\127.0.0.1\\IPC$"),
                    ("admin share", r"\\\\127.0.0.1\\C$"),
                    ("WebDAV", r"\\\\127.0.0.1@%d\\share" % a["tcp"])):
    try:
        os.listdir(path)
        out[label] = "listed"
    except OSError as error:
        out[label] = error.winerror or error.errno
print(json.dumps(out))
"""


def test_no_file_shares_or_webdav_on_this_machine(listener):
    answer, _ = probe(SHARES, {"tcp": listener.tcp_port})
    time.sleep(0.5)
    assert all(value != "listed" for value in answer.values()), answer
    assert listener.heard == []


# --- Files: nothing outside the working folder -------------------------------------

READ = """
import json, os, sys
a = json.loads(sys.argv[1])
out = {}
for label, path in a["read"].items():
    try:
        with open(path, "rb") as handle:
            handle.read(16)
        out[label] = "read"
    except OSError as error:
        out[label] = error.winerror or error.errno
for label, path in a["list"].items():
    try:
        os.listdir(path)
        out[label] = "listed"
    except OSError as error:
        out[label] = error.winerror or error.errno
print(json.dumps(out))
"""


def _outside(tmp_path):
    from sandbox import runtime

    canary = tmp_path / "canary.txt"
    canary.write_text("not for the sandbox")
    root = runtime.default_root()
    return {
        "read": {"canary": str(canary), "repository": str(ROOT / "README.md"),
                 "lock": str(root / "sandbox.lock")},
        "list": {"temporary folder": str(tmp_path), "profile": os.path.expanduser("~"),
                 "users": os.path.join(os.environ.get("SYSTEMDRIVE", "C:") + "\\", "Users"),
                 "repository folder": str(ROOT), "sandbox root": str(root),
                 "other working folders": str(root / "work")},
    }


def test_files_outside_the_working_folder_cannot_be_read(tmp_path):
    answer, _ = probe(READ, _outside(tmp_path))
    assert len(answer) == 9
    assert all(value in (5, 13) for value in answer.values()), answer


def test_control_unsandboxed_the_canary_is_read(tmp_path):
    answer, _ = probe(READ, _outside(tmp_path), isolation=OFF)
    assert answer["canary"] == "read" and answer["profile"] == "listed", answer


WRITE = """
import json, sys
a = json.loads(sys.argv[1])
out = {}
for label, path in a["write"].items():
    try:
        with open(path, "xb") as handle:
            handle.write(b"escaped")
        out[label] = "written"
    except OSError as error:
        out[label] = error.winerror or error.errno
print(json.dumps(out))
"""


def test_nothing_can_be_written_outside_the_working_folder(tmp_path):
    from sandbox import runtime

    root = runtime.default_root()
    name = f"sibar-escape-{uuid.uuid4().hex[:8]}"
    targets = {
        "temporary folder": tmp_path / name,
        "sandbox root": root / name,
        "runtime": runtime.site_packages(root) / f"{name}.py",
        "beside the working folder": root / "work" / name,
        "profile": Path(os.path.expanduser("~")) / name,
        "repository": ROOT / name,
    }
    answer, _ = probe(WRITE, {"write": {k: str(v) for k, v in targets.items()}})
    assert all(value in (5, 13) for value in answer.values()), answer
    assert [str(path) for path in targets.values() if path.exists()] == []


def test_control_unsandboxed_the_file_is_written(tmp_path):
    target = tmp_path / "escape.txt"
    answer, _ = probe(WRITE, {"write": {"temporary folder": str(target)}}, isolation=OFF)
    assert answer["temporary folder"] == "written" and target.exists()


def test_the_working_folder_is_writable_and_its_files_are_read_back():
    code = "open('out.txt', 'w').write('made in the sandbox')\nprint('{}')"
    from sandbox.box import Box

    with Box(limits=SMALL) as box:
        _, result = run_probe(box, code)
        assert result.exit_code == 0, result.stderr
        assert (box.app / "out.txt").read_text() == "made in the sandbox"


REGISTRY = """
import json, sys, winreg
a = json.loads(sys.argv[1])
out = {}
for label, path in (("environment", "Environment"), ("root", ""),
                    ("recent documents",
                     r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RecentDocs")):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, path))
        out[label] = "opened"
    except OSError as error:
        out[label] = error.winerror
if a.get("create"):
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, a["create"])
        winreg.CloseKey(key)
        out["create"] = "created"
    except OSError as error:
        out["create"] = error.winerror
print(json.dumps(out))
"""


def test_the_user_registry_cannot_be_read_or_written():
    import winreg

    key = rf"Software\sibar-escape-{uuid.uuid4().hex[:8]}"
    answer, _ = probe(REGISTRY, {"create": key})
    assert all(value == 5 for value in answer.values()), answer
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)


def test_control_without_the_restricted_token_the_environment_key_is_read():
    # registryRead, which Windows needs to start Python in an LPAC, grants
    # read access to the user's environment: the restricted token stops it.
    answer, _ = probe(REGISTRY, {}, isolation=replace(OFF, appcontainer=True))
    assert answer["environment"] == "opened", answer


ENVIRONMENT = "import json, os\nprint(json.dumps(sorted(os.environ)))"


def test_the_environment_holds_only_what_the_sandbox_sets(monkeypatch):
    from sandbox.box import Box

    monkeypatch.setenv("SIBAR_TEST_SECRET", "not for the sandbox")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    answer, _ = probe(ENVIRONMENT)
    with Box(limits=SMALL) as box:
        expected = sorted(box.environment())
    assert answer == expected
    assert "SIBAR_TEST_SECRET" not in answer and "ANTHROPIC_API_KEY" not in answer


# --- Processes: count, memory, time ----------------------------------------------------

FORK = """
import json, os, subprocess, sys, time
depth = int(os.environ.get("PROBE_DEPTH", "4"))
started = refused = 0
children = []
if depth > 0:
    environment = dict(os.environ, PROBE_DEPTH=str(depth - 1))
    for _ in range(2):
        try:
            children.append(subprocess.Popen([sys.executable, sys.argv[0], "{}"],
                                             env=environment, stdout=subprocess.PIPE))
            started += 1
        except OSError:
            refused += 1
time.sleep(1.0)
for child in children:
    out, _ = child.communicate()
    try:
        more = json.loads(out.decode().strip().splitlines()[-1])["counts"]
        started, refused = started + more[0], refused + more[1]
    except (ValueError, IndexError, KeyError):
        pass
print(json.dumps({"counts": [started, refused]}))
"""


def test_a_fork_bomb_is_held_to_the_process_limit():
    limits = replace(SMALL, processes=6)
    answer, result = probe(FORK, limits=limits)
    started, refused = answer["counts"]
    # How many start in all depends on timing (a slot frees when a process
    # ends); what holds is that some were refused and the tree never grew in
    # full (30 children without the limit, see the control).
    assert result.process_refused and refused >= 1, (answer, result.processes)
    assert started < 30, answer


def test_control_without_the_job_limits_the_fork_bomb_grows():
    answer, result = probe(FORK, limits=replace(SMALL, processes=6),
                           isolation=replace(OFF, job_limits=False))
    assert answer["counts"] == [30, 0], answer


MEMORY = """
import json, sys
blocks = []
try:
    for _ in range(9):
        blocks.append(bytearray(32 << 20))
    print(json.dumps({"got": len(blocks)}))
except MemoryError:
    print(json.dumps({"refused at": len(blocks)}))
"""


def test_memory_is_limited():
    answer, result = probe(MEMORY, limits=replace(SMALL, memory_mb=96))
    assert "refused at" in answer, answer
    assert result.memory_refused
    assert result.peak_memory_mb <= 96 + 32


def test_control_without_the_job_limits_memory_is_not_limited():
    answer, result = probe(MEMORY, limits=replace(SMALL, memory_mb=96),
                           isolation=replace(OFF, job_limits=False))
    assert answer == {"got": 9}


def test_wall_clock_limit():
    started = time.monotonic()
    _, result = probe("import time\ntime.sleep(60)", limits=replace(SMALL, seconds=2))
    assert result.cause == "timeout"
    assert time.monotonic() - started < 20


def test_cpu_time_limit():
    code = "import time\nend = time.time() + 25\nwhile time.time() < end: pass"
    _, result = probe(code, limits=replace(SMALL, cpu_seconds=1, seconds=30))
    # Ended by the CPU limit, before the 30-second clock (the process runs
    # at low priority, so on a busy machine the clock time varies).
    assert result.cause == "cpu", (result.cause, result.seconds, result.cpu_seconds)


# --- Disk -----------------------------------------------------------------------------

FILL = """
import json
with open("fill.bin", "wb") as handle:
    for _ in range(64):
        handle.write(bytes(1 << 20))
        handle.flush()
print(json.dumps({"wrote": 64}))
"""

EXTEND = """
import ctypes, msvcrt, time
from ctypes import wintypes
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_int64, ctypes.c_void_p,
                               wintypes.DWORD]
k.SetEndOfFile.argtypes = [wintypes.HANDLE]
with open("big.bin", "wb") as handle:
    native = msvcrt.get_osfhandle(handle.fileno())
    # Moving the end of the file takes the disk space without writing it.
    assert k.SetFilePointerEx(native, 64 << 20, None, 0) and k.SetEndOfFile(native)
    time.sleep(10)
"""

MANY = """
for index in range(3000):
    open(f"f{index}", "w").close()
"""

REWRITE = """
with open("same.bin", "wb") as handle:
    for _ in range(64):
        handle.seek(0)
        handle.write(bytes(1 << 20))
        handle.flush()
"""


HIDDEN = """
import time
# An alternate data stream: its bytes do not show in the file's size.
with open("plain.txt:hidden", "wb") as handle:
    for _ in range(64):
        handle.write(bytes(1 << 20))
        handle.flush()
        time.sleep(0.01)
time.sleep(5)
"""

HIDDEN_EXTEND = EXTEND.replace('open("big.bin", "wb")', 'open("big.bin:hidden", "wb")')


@pytest.mark.parametrize("code,write_mb,cause", [
    (FILL, 256, "disk"), (EXTEND, 256, "disk"), (MANY, 256, "disk"), (REWRITE, 32, "writes"),
    (HIDDEN, 256, "disk"), (HIDDEN_EXTEND, 256, "disk")])
def test_filling_the_disk_ends_the_run(code, write_mb, cause):
    limits = replace(SMALL, disk_mb=16, files=2000, write_mb=write_mb)
    _, result = probe(code, limits=limits)
    # The folder is watched, not capped by Windows: a fast writer can get
    # past the limit before the next look (docs/sandbox.md).
    assert result.cause == cause, (result.cause, result.stderr[-300:])


def test_control_without_watching_the_folder_fills():
    answer, result = probe(FILL, limits=replace(SMALL, disk_mb=16),
                           isolation=replace(OFF, watch=False))
    assert answer == {"wrote": 64} and result.cause is None


def test_a_box_is_not_opened_without_enough_free_space():
    import shutil

    from sandbox import runtime
    from sandbox.box import Box, SandboxError

    free = shutil.disk_usage(runtime.default_root()).free >> 20
    with pytest.raises(SandboxError, match="free"):
        Box(limits=replace(SMALL, free_disk_mb=free + 1)).open()


# --- No persistence, other processes, UI -------------------------------------------------

STAY = """
import json, subprocess, sys
out = {}
sleep = [sys.executable, "-c", "import time; time.sleep(60)"]
try:  # DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB
    out["breakaway"] = subprocess.Popen(sleep, creationflags=0x8 | 0x01000000).pid
except OSError as error:
    out["breakaway"] = -(error.winerror or 1)
out["detached"] = subprocess.Popen(sleep, creationflags=0x8).pid
print(json.dumps(out))
"""


def _alive(pid):
    from sandbox.box import _alive as alive

    return pid > 0 and alive(pid)


def test_no_process_outlives_the_run():
    answer, result = probe(STAY)
    assert answer["breakaway"] < 0, answer  # leaving the job is refused
    assert not _alive(answer["detached"])


OPEN = """
import ctypes, json, sys
from ctypes import wintypes
a = json.loads(sys.argv[1])
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wintypes.HANDLE
out = {}
for label, pid in a["pids"].items():
    for access, kind in ((0x0001, "terminate"), (0x0010, "read memory"),
                         (0x0040, "duplicate handles"), (0x0400, "query"),
                         (0x0200, "set information")):
        handle = k.OpenProcess(access, False, pid)
        if handle:
            k.CloseHandle(wintypes.HANDLE(handle))
            out[label + " " + kind] = "opened"
        else:
            out[label + " " + kind] = ctypes.get_last_error()
print(json.dumps(out))
"""


@pytest.fixture
def bystander():
    child = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-I", "-S",
                              "-c", "import time; time.sleep(60)"])
    yield child.pid
    child.kill()
    child.wait()


def test_other_processes_cannot_be_opened(bystander):
    pids = {"bystander": bystander, "the test": os.getpid()}
    answer, _ = probe(OPEN, {"pids": pids})
    assert len(answer) == 10
    assert all(value == 5 for value in answer.values()), answer
    assert _alive(bystander)


def test_control_unsandboxed_another_process_can_be_opened(bystander):
    answer, _ = probe(OPEN, {"pids": {"bystander": bystander}}, isolation=OFF)
    assert answer["bystander terminate"] == "opened", answer


UI = """
import ctypes, json
from ctypes import wintypes
u = ctypes.WinDLL("user32", use_last_error=True)
g = ctypes.WinDLL("gdi32")
out = {}
opened = u.OpenClipboard(None)
if opened:
    u.CloseClipboard()
out["clipboard"] = bool(opened)
titled = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def count(window, _):
    if u.GetWindowTextLengthW(window) > 0:
        titled.append(1)
    return True
u.EnumWindows(count, 0)
out["titled windows"] = len(titled)  # counted, never read
u.GetDC.restype = wintypes.HDC
g.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
dc = u.GetDC(None)
colours = {g.GetPixel(dc, x, y) for x in range(0, 1600, 101) for y in range(0, 900, 97)} if dc else set()
out["screen colours"] = len(colours)  # counted, never kept
u.OpenWindowStationW.restype = wintypes.HANDLE
u.OpenDesktopW.restype = wintypes.HANDLE
out["user's window station"] = bool(u.OpenWindowStationW("WinSta0", False, 0x2))
out["user's desktop"] = bool(u.OpenDesktopW("Default", 0, False, 0x1))
print(json.dumps(out))
"""


def test_the_clipboard_windows_and_screen_are_out_of_reach():
    answer, _ = probe(UI)
    assert answer == {"clipboard": False, "titled windows": 0, "screen colours": 1,
                      "user's window station": False, "user's desktop": False}


def test_control_without_a_desktop_of_its_own_windows_are_seen():
    # The job's UI restrictions hide other processes' windows too, so both
    # layers are off here; the AppContainer alone does not hide them.
    answer, _ = probe(UI, isolation=replace(OFF, appcontainer=True, restricted_token=True,
                                            watch=True))
    assert answer["titled windows"] > 0, answer


# --- Cleaning up ---------------------------------------------------------------------


def test_a_box_leaves_nothing_behind():
    from sandbox import win32
    from sandbox.box import Box

    with Box(limits=SMALL) as box:
        _, result = run_probe(box, STAY)
        folder, name = box.folder, box.name
        assert name in win32.profile_names()
    assert not folder.exists()
    assert name not in win32.profile_names()


def test_what_a_crashed_run_left_is_removed_by_the_next_box():
    from sandbox import runtime, win32
    from sandbox.box import PROFILE_PREFIX, Box

    # A profile and a folder as a run whose process has gone would leave.
    name = f"{PROFILE_PREFIX}4294967290-{uuid.uuid4().hex[:8]}"
    win32.create_profile(name)
    leftover = runtime.default_root() / "work" / "deadbeef"
    leftover.mkdir(parents=True, exist_ok=True)
    (leftover / "file.txt").write_text("left")
    try:
        with Box(limits=SMALL) as box:
            assert f"profile {name}" in box.removed
        assert name not in win32.profile_names()
        assert not leftover.exists()
    finally:
        if name in win32.profile_names():
            win32.delete_profile(name)


def test_one_box_at_a_time_per_root():
    from sandbox.box import Box, SandboxError

    with Box(limits=SMALL):
        with pytest.raises(SandboxError, match="another sandbox run"):
            Box(limits=SMALL).open()


# --- More ways out ------------------------------------------------------------------------

SHELL = """
import json, os, time
out = {}
for target in ("C:\\Windows\\System32\\calc.exe", "http://127.0.0.1:9/MARK"):
    try:
        os.startfile(target)
        out[target] = "asked"
    except OSError as error:
        out[target] = error.winerror
time.sleep(3)
print(json.dumps(out))
"""


def _processes(mark):
    """Processes outside this test whose command line has ``mark``, and the
    ids of any calculator processes."""
    script = ("$p = Get-CimInstance Win32_Process; "
              f"$m = @($p | Where-Object {{ $_.CommandLine -like '*{mark}*' -and "
              "$_.Name -notin @('powershell.exe', 'pwsh.exe') }).Count; "
              "$c = @($p | Where-Object { $_.Name -in @('calc.exe', 'CalculatorApp.exe') } "
              "| ForEach-Object { $_.ProcessId }); "
              "Write-Output ($m.ToString() + ' ' + ($c -join ','))")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                         capture_output=True, text=True, timeout=60).stdout.split()
    return int(out[0]), set(out[1].split(",")) if len(out) > 1 else set()


def test_programs_started_through_the_shell_stay_inside():
    # If this boundary failed, a browser would open on 127.0.0.1:9 (nothing
    # listens there) and a calculator on the user's desktop.
    mark = f"sibar-probe-{uuid.uuid4().hex[:8]}"
    _, calculators = _processes(mark)
    answer, result = probe(SHELL.replace("MARK", mark))
    marked, after = _processes(mark)
    assert marked == 0 and after <= calculators, (answer, marked, after - calculators)


# A thread that starts at address 0: an access violation outside anything
# that would catch it (ctypes catches faults in the calls it makes).
CRASH = """
import ctypes, time
kernel = ctypes.WinDLL("kernel32")
kernel.CreateThread.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
kernel.CreateThread(None, 0, None, None, 0, None)
time.sleep(15)
"""


def test_a_crash_ends_the_run_at_once_without_a_dialog():
    _, result = probe(CRASH, limits=replace(SMALL, seconds=20))
    assert result.cause is None
    assert result.exit_code == 0xC0000005  # access violation


def test_the_helpers_cannot_be_changed_by_the_output():
    from sandbox.box import Box
    from sandbox.run import _install_tools

    code = """
import json, sys
a = json.loads(sys.argv[1])
out = {}
for label, path in (("change", a["helper"]), ("add", a["new"])):
    try:
        with open(path, "a") as handle:
            handle.write("tampered")
        out[label] = "written"
    except OSError as error:
        out[label] = error.winerror or error.errno
print(json.dumps(out))
"""
    with Box(limits=SMALL) as box:
        tools = _install_tools(box)
        before = (tools / "survey.py").read_bytes()
        answer, _ = run_probe(box, code, {"helper": str(tools / "survey.py"),
                                          "new": str(tools / "new.py")})
        assert set(answer.values()) <= {5, 13}, answer  # access denied
        assert (tools / "survey.py").read_bytes() == before


CREDENTIALS = """
import ctypes, json
from ctypes import wintypes
advapi = ctypes.WinDLL("advapi32", use_last_error=True)
count, found = wintypes.DWORD(), ctypes.c_void_p()
if advapi.CredEnumerateW(None, 0, ctypes.byref(count), ctypes.byref(found)):
    advapi.CredFree(found)
    print(json.dumps({"listed": count.value}))  # how many, never what
else:
    print(json.dumps({"error": ctypes.get_last_error()}))
"""


def test_stored_credentials_cannot_be_listed():
    answer, _ = probe(CREDENTIALS)
    assert "error" in answer and answer["error"] != 1168, answer  # 1168: none stored


def test_control_unsandboxed_the_credential_manager_answers():
    answer, _ = probe(CREDENTIALS, isolation=OFF)
    assert "listed" in answer or answer["error"] == 1168, answer


MORE_RIGHTS = (ROOT / "tests" / "fixtures" / "sandbox" / "more_rights.py").read_text()


def test_no_child_with_more_rights(listener):
    answer, _ = probe(MORE_RIGHTS, {"tcp": listener.tcp_port})
    assert all(result[0] == "create failed" for result in answer.values()), answer
    assert listener.heard == []


def test_control_outside_the_sandbox_such_a_child_can_be_started(listener, tmp_path):
    # The same calls, made from outside with the box's package SID, start
    # the child: the refusal above is the sandbox's, not a bad probe.
    from sandbox.box import Box

    script = tmp_path / "more_rights.py"
    script.write_text(MORE_RIGHTS)
    with Box(limits=SMALL) as box:
        out = subprocess.run(
            [getattr(sys, "_base_executable", sys.executable), "-I", str(script),
             json.dumps({"tcp": listener.tcp_port, "package": box.package.string})],
            capture_output=True, text=True, timeout=60, cwd=tmp_path)
    answer = json.loads(out.stdout.strip().splitlines()[-1])
    assert answer["not less privileged"][0] == "started", answer
