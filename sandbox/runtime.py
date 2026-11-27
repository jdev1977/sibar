"""The sandbox's private Python runtime: a copy of this Python plus a fixed,
hash-checked package set, in a folder only the sandbox reads.

``setup`` builds it under ``<root>/runtime`` (``<root>`` is ``.sandbox`` in
the repository unless ``SIBAR_SANDBOX_ROOT`` says otherwise). The folder gets
a protected DACL: full control for the user, SYSTEM and administrators, and
read and execute for two SIDs no other program holds: the sandbox's own
AppContainer capability and the SID its restricted token is checked against.
No system or user folder's permissions are changed. Deleting the folder, or
``python -m sandbox remove``, undoes everything setup did.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from sandbox import TOOL_VERSION
from sandbox.files import remove_tree

REPOSITORY = Path(__file__).resolve().parents[1]
REQUIREMENTS = Path(__file__).with_name("requirements.txt")
SHIM = Path(__file__).with_name("shim")
ROOT_VARIABLE = "SIBAR_SANDBOX_ROOT"
MANIFEST = "sandbox-runtime.json"

# The capability every sandboxed process holds; only the runtime grants it.
RUNTIME_CAPABILITY = "sibarSandboxRuntime"
# The SID a sandboxed process's restricted token is checked against, besides
# Everyone, Users and the logon session. A fixed SID of the resource-manager
# authority (S-1-9) that nothing on Windows uses: only the runtime and the
# working folders the sandbox makes grant it.
RESTRICTED_SID = "S-1-9-1170951826-2309618851-3473915307-1022"
# Read and execute (FILE_GENERIC_READ | FILE_GENERIC_EXECUTE).
READ_EXECUTE = "0x1200a9"

# Parts of the Python installation left out: not needed to run code (tests
# of Python itself, pip, headers), or a GUI the sandbox cannot show.
SKIPPED = frozenset({
    "doc", "include", "libs", "scripts", "tcl", "lib/site-packages", "lib/test",
    "lib/idlelib", "lib/tkinter", "lib/turtledemo", "lib/ensurepip", "pythonw.exe",
    "dlls/_tkinter.pyd", "dlls/tcl86t.dll", "dlls/tk86t.dll",
})


class RuntimeMissing(Exception):
    """The runtime is not set up, or not as this code expects."""


@contextmanager
def _locked(root):
    """Hold the root's lock (the one each sandbox run holds) while the
    runtime is changed, so no run uses a runtime half replaced."""
    from runner.ledger import LedgerError, lock_file, unlock_file

    Path(root).mkdir(parents=True, exist_ok=True)
    try:
        handle = lock_file(Path(root) / "sandbox.lock")
    except LedgerError:
        raise RuntimeMissing(f"a sandbox run is using {root}; try again when it "
                             "has ended") from None
    try:
        yield
    finally:
        unlock_file(handle)


def default_root():
    """Where the runtime and working folders live."""
    return Path(os.environ.get(ROOT_VARIABLE) or REPOSITORY / ".sandbox").resolve()


def runtime_dir(root):
    return Path(root) / "runtime"


def python(root):
    return runtime_dir(root) / "python.exe"


def site_packages(root):
    return runtime_dir(root) / "Lib" / "site-packages"


def _digest(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def requirements_digest():
    return _digest([REQUIREMENTS])


def shim_digest():
    return _digest([p for p in SHIM.iterdir() if p.suffix == ".py"])


def runtime_dacl(user):
    """The DACL of the runtime folder, as SDDL."""
    from sandbox import win32

    capability = win32.capability_sid(RUNTIME_CAPABILITY).string
    return (f"D:P(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
            f"(A;OICI;{READ_EXECUTE};;;{capability})"
            f"(A;OICI;{READ_EXECUTE};;;{RESTRICTED_SID})")


def _copy_python(base, target):
    """Copy the Python installation at ``base`` to ``target``, less SKIPPED."""
    def ignore(folder, names):
        relative = Path(folder).relative_to(base).as_posix().lower()
        prefix = "" if relative == "." else relative + "/"
        return {name for name in names
                if (prefix + name.lower()) in SKIPPED or name == "__pycache__"}

    shutil.copytree(base, target, ignore=ignore)


def _packages(site):
    found = {}
    for info in site.glob("*.dist-info"):
        name, _, version = info.name[:-len(".dist-info")].partition("-")
        found[name.lower().replace("_", "-")] = version
    return dict(sorted(found.items()))


def setup(root=None, wheelhouse=None, say=print):
    """Build the runtime under ``root``, replacing an earlier one.

    The packages come from PyPI, or with ``wheelhouse`` from that folder
    only; either way pip checks each file against the hash pinned in
    ``sandbox/requirements.txt``. Returns the manifest written."""
    if os.name != "nt":
        raise RuntimeMissing("the sandbox runs on Windows only")
    if sys.version_info[:2] != (3, 13) or sys.maxsize < 2**32:
        raise RuntimeMissing("setup needs 64-bit Python 3.13")
    root = Path(root or default_root()).resolve()
    with _locked(root):
        manifest = _build(root, wheelhouse, say)
    say("checking that sandboxed code can import every package")
    problem = self_test(root)
    if problem:
        raise RuntimeMissing(f"the runtime does not work in the sandbox: {problem}")
    say(f"runtime ready in {runtime_dir(root)}")
    return manifest


def _build(root, wheelhouse, say):
    from sandbox import win32

    staging = root / "runtime.new"
    if staging.exists():
        remove_tree(staging)
    base = Path(sys.base_prefix)
    say(f"copying Python {sys.version.split()[0]} from {base}")
    _copy_python(base, staging)
    site = staging / "Lib" / "site-packages"
    site.mkdir()
    command = [sys.executable, "-m", "pip", "install", "--target", str(site),
               "--no-deps", "--only-binary=:all:", "--require-hashes", "--no-compile",
               "--disable-pip-version-check", "--no-warn-script-location",
               "--no-cache-dir", "-r", str(REQUIREMENTS)]
    if wheelhouse:
        command += ["--no-index", "--find-links", str(Path(wheelhouse).resolve())]
    say("installing the pinned packages" + (f" from {wheelhouse}" if wheelhouse
                                             else " from PyPI"))
    subprocess.run(command, check=True)
    shutil.rmtree(site / "bin", ignore_errors=True)  # console scripts: unused
    for leftover in site.glob("*.whl"):
        leftover.unlink()
    for shim in SHIM.iterdir():
        if shim.suffix == ".py":
            shutil.copy2(shim, site / shim.name)
    say("compiling (the runtime is read-only to sandboxed code)")
    subprocess.run([str(staging / "python.exe"), "-I", "-m", "compileall", "-q",
                    "-j", "0", str(staging / "Lib")], check=False,
                   stdout=subprocess.DEVNULL)
    manifest = {
        "tool_version": TOOL_VERSION,
        "python": sys.version.split()[0],
        "requirements_sha256": requirements_digest(),
        "shim_sha256": shim_digest(),
        "packages": _packages(site),
        "capability": RUNTIME_CAPABILITY,
        "capability_sid": win32.capability_sid(RUNTIME_CAPABILITY).string,
        "restricted_sid": RESTRICTED_SID,
    }
    (staging / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n",
                                    encoding="utf-8")
    # pip unpacks into folders made by tempfile, which Python 3.13 gives a
    # protected DACL of their own; make every file inherit from the top
    # again, then give the top the runtime's DACL.
    subprocess.run(["icacls", str(staging), "/reset", "/t", "/c", "/q"], check=True,
                   stdout=subprocess.DEVNULL)
    win32.set_file_security(staging, runtime_dacl(win32.user_sid().string))
    target = runtime_dir(root)
    if target.exists():
        remove_tree(target)
    staging.rename(target)
    return manifest


def update_shims(root=None, say=print):
    """Copy the shim files (``sandbox/shim``) into an existing runtime, so a
    change to them needs no full setup; then run the self-test."""
    root = Path(root or default_root()).resolve()
    path = runtime_dir(root) / MANIFEST
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeMissing(f"no sandbox runtime in {runtime_dir(root)}: run "
                             "`python -m sandbox setup`") from None
    site = site_packages(root)
    with _locked(root):
        for shim in SHIM.iterdir():
            if shim.suffix == ".py":
                shutil.copyfile(shim, site / shim.name)
                subprocess.run([str(python(root)), "-I", "-m", "py_compile",
                                str(site / shim.name)], check=True)
        found["shim_sha256"] = shim_digest()
        path.write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8")
    problem = self_test(root)
    if problem:
        raise RuntimeMissing(f"the runtime does not work in the sandbox: {problem}")
    say("shims updated")


# Imported by the self-test: each pinned top-level package, under the name
# code imports it by.
IMPORTS = ("numpy", "scipy", "scipy.optimize", "scipy.stats", "sympy", "pandas",
           "matplotlib.pyplot", "PIL.Image", "requests", "yaml", "sqlalchemy",
           "pydantic", "jsonschema", "dateutil.parser", "click", "tqdm", "pytest",
           "zoneinfo", "sqlite3", "ssl", "ctypes")


# Wall-clock seconds the self-test may take. It loads every package at once,
# straight after setup wrote the files, which on a busy machine takes many
# times as long as a run is allowed (``Limits.seconds``).
SELF_TEST_SECONDS = 600
# Printed by Python at every start in the sandbox, which Windows will not tell
# where the runtime really is. It does no harm and is never what went wrong.
STARTUP_WARNING = "Failed to find real location of "


def self_test(root):
    """Import every package in a sandbox and draw a plot; return None if that
    worked, else what went wrong."""
    from sandbox.box import Box, Limits

    code = ("import importlib, zoneinfo\n"
            f"for name in {IMPORTS!r}:\n"
            "    importlib.import_module(name)\n"
            "zoneinfo.ZoneInfo('America/New_York')\n"
            "import matplotlib.pyplot as plt\n"
            "plt.plot([0, 1]); plt.savefig('plot.png')\n"
            "print('imported', len(" + repr(IMPORTS) + "))\n")
    with Box(root, limits=Limits(seconds=SELF_TEST_SECONDS)) as box:
        result = box.run([box.python(), "-c", code])
        if result.exit_code == 0 and result.stdout.startswith(b"imported"):
            # Keep the font list matplotlib made, so runs need not make it
            # again (it takes many seconds): Box copies it into each box.
            cache = font_cache(root)
            cache.mkdir(exist_ok=True)
            for made in (box.home / ".matplotlib").glob("fontlist-*.json"):
                shutil.copyfile(made, cache / made.name)
            return None
    return _self_test_problem(result)


def _self_test_problem(result):
    """Why the self-test run ``result`` did not pass."""
    if result.cause == "timeout":
        return (f"the self-test hit its time limit after {result.seconds:.0f} s, "
                f"having used {result.cpu_seconds:.1f} s of CPU. With little CPU "
                "used, the machine was probably short of memory or busy: close "
                "other programs and run setup again")
    lines = [line for line in result.stderr.decode("utf-8", "replace").splitlines()
             if line.strip() and not line.startswith(STARTUP_WARNING)]
    if result.cause:
        ended = f"the self-test was ended by the {result.cause} limit"
    else:
        ended = f"exit code {result.exit_code}"
    return (f"{ended}: {lines[-1].strip()}" if lines else ended)[:500]


def font_cache(root):
    """Where the runtime keeps matplotlib's font list."""
    return runtime_dir(root) / "mplconfig"


def manifest(root):
    """The manifest of the runtime under ``root``; RuntimeMissing if there is
    none or it does not match this code."""
    path = runtime_dir(root) / MANIFEST
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeMissing(f"no sandbox runtime in {runtime_dir(root)}: run "
                             "`python -m sandbox setup`") from None
    if not python(root).is_file():
        raise RuntimeMissing(f"{python(root)} is missing: run `python -m sandbox setup`")
    if found.get("requirements_sha256") != requirements_digest():
        raise RuntimeMissing("sandbox/requirements.txt changed since setup: run "
                             "`python -m sandbox setup` again")
    if found.get("shim_sha256") != shim_digest():
        raise RuntimeMissing("sandbox/shim changed since setup: run "
                             "`python -m sandbox setup` again")
    if found.get("restricted_sid") != RESTRICTED_SID:
        raise RuntimeMissing("the runtime was set up for another restricted SID: run "
                             "`python -m sandbox setup` again")
    return found


def check(root):
    """The manifest, after checking the runtime folder's DACL is exactly the
    one setup gives it; RuntimeMissing otherwise."""
    from sandbox import win32

    found = manifest(root)
    expected = win32.SecurityDescriptor(runtime_dacl(win32.user_sid().string))
    actual = win32.file_dacl(runtime_dir(root))
    if win32.dacl_text(expected) != actual:
        raise RuntimeMissing(f"the permissions of {runtime_dir(root)} are not the "
                             "ones setup gives: run `python -m sandbox setup` again")
    return found


def remove(root=None):
    """Delete the runtime: its folder and the permissions on it."""
    root = Path(root or default_root()).resolve()
    target = runtime_dir(root)
    if target.exists():
        with _locked(root):
            remove_tree(target)
