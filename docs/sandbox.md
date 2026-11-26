# Sandbox

`sandbox/` (task T2.7) runs model-generated code: the pipeline, math and
engineering outputs. The code is **untrusted**, and it runs on the owner's
own Windows machine, so the sandbox is built to fail closed: if Windows
refuses any layer, nothing runs. It needs no administrator rights, installs
nothing system-wide and changes no system setting.

It records whether each output ran or failed and why, its test results,
time, memory and what it wrote, as a `sandbox` check in the run record.

## Setup (once, by the owner)

From the repository root, in the project's environment:

    .venv/Scripts/python -m sandbox setup

This builds the sandbox's own Python under `.sandbox/runtime` (gitignored;
set `SIBAR_SANDBOX_ROOT` to put the sandbox elsewhere). It:

1. copies the Python that runs the command (64-bit 3.13), without its own
   site-packages, tests, Tk and pip;
2. installs the packages in [sandbox/requirements.txt](../sandbox/requirements.txt)
   into it with pip, which checks every file against the SHA-256 pinned
   there. This is the one step that uses the network (PyPI). With
   `--wheelhouse FOLDER` pip takes the files from that folder only;
3. adds the shims (`sandbox/shim`), compiles everything (the sandbox cannot
   write there) and writes `sandbox-runtime.json`;
4. sets the folder's permissions (below) and ends with a self-test: every
   package is imported, and a plot drawn, in a real sandbox.

It takes a few minutes and about 600 MB. Run it again whenever
`sandbox/requirements.txt` or `sandbox/shim` changes: every run checks the
runtime against them and refuses a stale one.

**Permissions.** The runtime folder (only it) gets a protected DACL: full
control for the owner, SYSTEM and Administrators, and read and execute for
two SIDs that nothing else on Windows holds: the sandbox's AppContainer
capability `sibarSandboxRuntime` and the SID `S-1-9-1170951826-2309618851-3473915307-1022`
that the sandbox's restricted token is checked against. Nothing outside
`.sandbox` is touched: no system or user-profile folder, no registry key
the sandbox does not create and delete itself.

**Undo.** `python -m sandbox remove` deletes the runtime (its permissions go
with it) and anything runs left behind. Deleting `.sandbox` by hand does the
same. `python -m sandbox status` shows the runtime and any leftovers;
`python -m sandbox clean` removes leftovers (a crashed run's AppContainer
profile or working folder; the next run would remove them anyway).

## Use

    python -m sandbox run --records data/runs/<batch-id>/records.jsonl
    python -m sandbox run --records FILE --record-id ID --force
    python -m sandbox run --dir FOLDER [--task pipeline/data-validation/L2]
                          [--command "python main.py --day 2027-03-02"] [--out FILE]

| Option | Meaning | Default |
|---|---|---|
| `--records FILE` | Run the records of a record file | pipeline, math and engineering records with status `ok` or `truncated` |
| `--record-id ID` | Only this record (repeatable) | |
| `--force` | Run again records that already have a `sandbox` check | off; a check whose result is `error` is always run again |
| `--dir FOLDER` | Run the one output in a folder | |
| `--task TYPE/TASK/LEVEL` | With `--dir`: the task, for its fixtures and measurements | none (from the record with `--records`) |
| `--command` | With `--dir`: the command; a first word `python` is the sandbox's Python | the entry point found (below) |
| `--out FILE` | With `--dir`: where the check goes, outside the folder | `<folder>-sandbox.json` |
| `--no-tests` | Do not run the output's tests | tests are run |
| `--clock` | A fixed start time, ISO 8601 with a time zone | the task's, else the real time |
| `--scale-mb` | Size of the large generated input, for tasks that have one | 0 |
| `--seconds` | Wall-clock seconds per run | 60 |
| `--cpu-seconds` | User-mode CPU seconds per run, all processes together | 60 |
| `--memory-mb` | Committed memory per run, all processes together | 1024 |
| `--processes` | Processes alive at once | 16 |
| `--disk-mb` | Size of the working folder | 256 |
| `--files` | Files and folders in the working folder | 10000 |
| `--write-mb` | Megabytes written through any handle in a run | 2048 |
| `--cpu-percent` | Hard cap on the CPU rate, percent of all cores | 50 |
| `--free-disk-mb` | Free space the drive must keep; a run below it ends | 1024 |

Exit codes: 0 every output ran (and its tests passed); 1 some did not; 2
nothing ran: bad options, no runtime, a busy record file or sandbox.

From Python: `sandbox.run.run_folder(folder, paths, Settings(...))` returns
the check's `detail`; `sandbox.box.Box` runs any command in a sandbox.

One sandbox runs at a time per sandbox root (a lock file); runs are
sequential, which also suits a machine with little free memory.

## What happens to an output

1. The output's files (for a record: those it lists, under `extracted/`) are
   copied into a new working folder, `app/`.
2. A helper parses every Python file **inside the sandbox** (never importing
   it) and lists imports, entry points and tests.
3. The task's fixtures are written (below).
4. The entry point runs, with no arguments. **No command line is assumed**
   (rule 18 of [leak-check.md](leak-check.md)); the entry point is read from
   the output: a file named `main.py`, `__main__.py`, `app.py`, `run.py`,
   `cli.py` or `pipeline.py`, then a package's `__main__.py`
   (`python -m pkg`), a console script in `pyproject.toml`, then any file
   that runs code when started (a main guard or statements at the top level)
   that no other file imports and that is not a tool's configuration
   (`setup.py`, `conftest.py`, `conf.py`, `noxfile.py`, `fabfile.py`). Only
   one runs; the candidates are recorded (an answer with several separate
   code blocks runs its first). If it stops asking for arguments (an
   argparse or click usage error, or an `IndexError` on `sys.argv`), the
   arguments the task's fixtures suggest are tried in turn, and the attempts
   are recorded.
5. The task's measurements read what it wrote.
6. If the output has tests (`test_*.py`, `*_test.py`, test functions or
   `unittest` classes) they run with pytest, with the output's own pytest
   configuration if it has one. They run after the measurements, so these
   see only what the program wrote.

Each run gets its own job and limits; all share the working folder. The
folder and everything else is deleted afterwards.

### Outcomes

`detail.result`:

| Result | Meaning | Check `outcome` |
|---|---|---|
| `ran` | The entry point (or, with none, the test run) ended by itself with exit code 0 | `ok`, or `failed` if tests failed |
| `failed` | It ended by itself with another exit code, and nothing points to a limit or a boundary | `failed` |
| `timeout` | The wall-clock or CPU-time limit ended it | `failed` |
| `memory` | The memory limit refused memory and it then failed | `failed` |
| `blocked` | It ran into a boundary and then failed (network, files outside its folder, the process limit), or the disk limit ended it | `failed` |
| `not-runnable` | No Python files (other languages are named), modules outside the package set (named), or nothing to run | `error` |
| `error` | The sandbox itself failed; nothing is said about the output | `error` |

`blocked` is read from the error output (socket and name-resolution errors,
access denied on a path outside the folder), so it is a strong hint, not a
proof. Exit code 2 with a usage message is `failed` with
`needs_arguments: true`.

### The check

One entry in the record's `checks`, replacing an earlier one:

| Key | Value |
|---|---|
| `name`, `tool`, `tool_version` | `sandbox`, `sandbox`, the sandbox's version |
| `outcome` | as above |
| `files` | none: everything is in `detail` |
| `detail.result`, `detail.reason` | the result and, when there is one, why |
| `detail.entry` | the command, exit code, seconds, CPU seconds, peak memory (MB, all processes together), processes started, what ended it (`ended_by`), whether a limit refused memory or a process, stdout and stderr (head and tail, 4000 characters, local folders replaced by `<folder>` and `<root>`), their full sizes, `needs_arguments`, `earlier_attempts` |
| `detail.tests` | `ran`, pytest's exit code, counts (collected, passed, failed, errors, skipped, xfailed, xpassed), up to 20 failing test ids, and the run as for `entry` |
| `detail.candidates`, `detail.missing_modules`, `detail.syntax_errors`, `detail.languages` | what the survey found |
| `detail.task` | the task's measurements (below) |
| `detail.settings`, `detail.runtime`, `detail.environment` | limits, command, task, clock and scale; the Python version and the hash of the package list; the names of the task's extra variables |

**Test results are self-reported.** The output's tests run in the same
process as the counting, so code that wants to can forge them. Nothing in a
check proves more than "the output's own tests said so". Text in a check
(stdout, stderr, test ids) was written by the output: treat it as untrusted.

## Boundaries

What the sandboxed code cannot do, how, and the test that shows it
([tests/test_sandbox_boundaries.py](../tests/test_sandbox_boundaries.py)).
Each test has a control: the same probe with the responsible layer turned
off gets through, so the test would fail if the boundary went.

| Boundary | How | Test (control) |
|---|---|---|
| No network: TCP, UDP, IPv6, loopback | A **less privileged AppContainer** (LPAC) with no network capability: Windows refuses to make a socket at all | no socket can be made, a listener on 127.0.0.1 hears nothing (without the AppContainer it connects) |
| No DNS | The LPAC cannot reach the DNS Client service: it cannot even read the resolver's cache, and no query is sent for it | a query aimed at a listener on 127.0.0.1:53 never arrives (without the AppContainer it does) |
| No named pipes to other processes | The AppContainer check: only objects granted to its package SID or capabilities open, and an LPAC is not granted what all application packages are | pipes with default security, an everyone DACL and **no DACL at all** do not open (they do unsandboxed) |
| No reads outside its folder | The AppContainer check plus a **restricted token**: every access is checked again against Everyone, Users, the logon session and the sandbox's own SID only | a canary in the user's temp folder, the profile, the repository and other working folders cannot be read or listed (unsandboxed they can) |
| No user registry, no environment secrets | Windows needs the `registryRead` capability to start Python in an LPAC, and it grants read access to the user's hive, which holds user environment variables. The restricted token shuts that out. The process's environment is built from scratch: nothing is copied from the caller's | HKCU, its `Environment` key and recent documents cannot be opened or written (without the restricted token `Environment` opens); the environment holds exactly the names the sandbox sets |
| No writes outside its folder | As for reads, and a low integrity level: it can write nothing labelled higher. The working folder alone grants modify (not change permissions) to the box's package SID and the restricted SID, and is labelled low | writes to the temp folder, the sandbox root, the runtime, beside the working folder, the profile and the repository fail (unsandboxed the first works) |
| Processes | A job object per run: processes alive at once (default 16), no breakaway, all killed when the run ends | a bounded fork bomb (31 processes) is held to the limit (without the limit all 31 start) |
| Memory | The job's limit on committed memory, all processes together | allocation is refused at the limit (without it the probe gets all it asks for) |
| Time | Wall clock watched from outside; user-mode CPU time limited by the job | sleeping and spinning probes are ended |
| Disk | The working folder's size and file count and the drive's free space are checked every 0.1 s, and bytes written through any handle every 0.05 s; the run ends at a limit. A box does not open without the free space its limits need | writing, extending a file without writing, many small files and rewriting the same block all end the run (without watching the folder fills) |
| No persistence | Every process is in the job and is killed, and waited for, when the run ends; nothing outside the folder can be written (registry Run keys and the Startup folder included); the folder is then deleted | a detached child does not outlive the run; leaving the job is refused |
| Other processes | The AppContainer check: other processes of the user grant nothing to the package SID | opening the test process or a bystander for terminate, read memory, duplicate handles, query and set information fails (unsandboxed it works) |
| Clipboard and UI | A **new desktop** outside the user's interactive window station, and the job's UI restrictions (clipboard, global atoms, other processes' windows, desktop switching, system settings) | no clipboard, no titled windows seen, a blank screen, the user's window station and desktop do not open (without them windows are seen) |
| Programs started through the shell | Whatever the process starts is in its job, with its token, on its desktop; Windows does not start a browser or a packaged app for it | opening a URL (to 127.0.0.1) and the calculator through the shell starts nothing outside |
| Crashes | The job ends a crashing process at once, without Windows Error Reporting or a dialog | a thread started at address 0 ends the run with an access violation |
| The sandbox's helpers | The helper scripts' folder is read and execute only for the sandboxed process | it cannot change or add to them |
| Cleanup | Profile, desktop, token and folder are removed on close; a crashed run's profile and folder by the next box | nothing is left after a run; leftovers of a dead process are swept |

### The layers, in order

- **AppContainer profile.** A new profile per box, named
  `sibar.sb.<process id>-<random>`. Windows starts a process in an
  AppContainer only if it has a profile, and a profile comes with a folder
  under the user's local application data and a registry key the container
  could write to. The sandbox deletes both at once (it made them), so the
  working folder is the only writable place. The profile itself is deleted
  on close.
- **Less privileged.** The process opts out of the access granted to all
  application packages. Its capabilities are the runtime capability and
  `registryRead`, which grants read access to system configuration in the
  registry (`HKLM`: Windows version, computer name, the registered owner's
  name) as well as the user's hive, which the restricted token then blocks.
- **Restricted token**: a copy of the user's token with no privileges but
  bypass-traverse, Administrators deny-only, and the four restricting SIDs
  above. Its default DACL grants the user, SYSTEM, the restricted SID and
  the package SID, so the process can use what it makes.
- **Desktop.** A normal user cannot choose a window station: asked for a new
  one, Windows hands out the logon session's non-interactive station
  (`Service-0x0-<id>$`). The desktop made in it is new and its DACL is
  checked. The station's clipboard and atoms may be shared with other
  non-interactive processes of the user; the job's UI restrictions keep the
  sandbox from both.
- **Job object** (`sandbox/job.py`, shared with the renderer): memory,
  processes, CPU time, a CPU rate cap of 50% of all cores and below-normal
  priority (so the machine stays usable), UI restrictions, no crash dialogs,
  kill on close. The process is put in the job when it is created, suspended,
  and checked to be in it before it runs.
- **Watching**: the clock, bytes written, the folder and the free space.

### Threat model

The code is assumed hostile: it may try to read the owner's files, keys and
environment, reach the network or other processes, persist, or exhaust the
machine. It runs as the owner's user, so every boundary is a Windows access
check or a limit, not a separate account.

**Not defended:**

- **Kernel and driver exploits**, and flaws in the AppContainer, token or
  job checks themselves. The sandbox narrows the kernel surface (no network,
  few objects) but does not remove it: system calls, the graphics subsystem
  (win32k) and any driver reachable from an AppContainer remain. This is not
  a virtual machine.
- **CPU side channels** (Spectre-class) and timing.
- **Reads the boundaries allow by design**: system files (`C:\Windows`,
  Program Files, fonts), system configuration in `HKLM` (including the
  computer name and registered owner), the list of its own processes, and
  the runtime. The host name is also readable through Windows calls,
  whatever `COMPUTERNAME` says.
- **Disk-fill overshoot.** The disk limit is watched, not enforced by
  Windows (NTFS quotas need administrator rights, and would limit the owner
  too). A run can write past the limit for up to one check (0.1 s; at disk
  speed, hundreds of megabytes), and one call that moves the end of a file
  can take all free space at once until the next check, when the run ends
  and the folder is deleted. To make the limit hard, the owner can put the
  sandbox root (`SIBAR_SANDBOX_ROOT`) on a small separate volume or a
  fixed-size virtual disk (both need administrator rights to create).
- **Session resources.** A run can use up to its process limit times the
  per-process GDI handle quota, which could crowd the session's shared GDI
  handle table until the run ends (at most the wall-clock limit). Window
  objects use the private desktop's own small heap.
- **What the output says about itself**: test results and anything it
  prints. The task measurements read files it wrote (with size limits, and
  images only inside the sandbox).
- **Concurrency across sandbox roots**: runs in different roots may run at
  once; each has its own profile, folder and desktop.

## Languages and packages

**Python only.** Other languages are recorded as `not-runnable`, naming
them: no other runtime (Node, Go, Rust, Java, R) is installed, and
installing one would be a system change; shell scripts would run commands
written for another system. A private Node or Go could be added later the
way Python is (a copy under `.sandbox`, granted to the capability); it is
not done because no task needs it yet (ci-workflow's Go package cannot run
without its build service anyway).

**Packages.** The runtime has the standard library and the pinned set in
[sandbox/requirements.txt](../sandbox/requirements.txt), chosen from the
prompt sets: numpy, scipy, sympy, matplotlib (Agg backend) and pandas for
the math and engineering tasks and CSV work; SQLAlchemy (csv-to-database),
requests (daily-api-fetch), Pillow (image-resize), PyYAML, pydantic and
jsonschema (data-validation), python-dateutil, click and tqdm, tzdata
(Windows has no time-zone database), and pytest. Left out: asyncio HTTP
clients (no sockets), schedulers that keep running, statsmodels,
scikit-learn, OpenCV, seaborn, plotly. An output that imports anything
missing is `not-runnable`, and `missing_modules` lists it, so library choice
can be counted. Adding a package changes outcomes: raise `TOOL_VERSION`.

The environment: `TZ=UTC`, `PYTHONHASHSEED=0`, UTF-8, no bytecode writes,
four CPUs reported to Python and to the numerical libraries (so a pool of
workers stays small), `MPLBACKEND=Agg`, home and temp folders inside the
working folder, `USERNAME=sandbox`.

### Shims

Small fixes in the runtime (`sandbox/shim/sitecustomize.py`) make ordinary
code behave as outside the sandbox where an AppContainer would break it.
None is a boundary: the code can undo them and gain nothing.

- `os.path.realpath(".")` (Windows will not give an AppContainer a file's
  final path, and Python's fallback then doubles the folder name).
- multiprocessing pipes (an AppContainer may only make pipes in its own
  namespace, `\\.\pipe\LOCAL\`), with a DACL its restricted token matches.
- `os.devnull` (no AppContainer may open the NUL device): it is served by a
  copy of the process's standard input, which the sandbox opens on NUL.
- folders made with mode 0o700, such as `tempfile`'s (Python 3.13 gives
  them a DACL the sandboxed process does not match).
- `import asyncio` (Python's `_overlapped` makes a socket when imported):
  event loops then work without sockets, for timers, tasks and threads;
  networking with asyncio still fails.

Python itself prints "Failed to find real location of ...python.exe" at
start in an AppContainer (the same final-path refusal); records leave the
line out.

## Tasks: fixtures, clock, stub and measurements

From [prompts/pipeline/README.md](../prompts/pipeline/README.md), "Running
offline", and the L2 directions T2.7 owns in [rubrics.md](rubrics.md).
Hooks are in `sandbox/tasks.py`; inputs come from the L2 brief's sample
data and are given at every level.

| Task | Inputs and settings | Arguments tried | Measured |
|---|---|---|---|
| data-validation | `incoming/2026-03-02/OV-014.jsonl` (the two readings), `stations.csv`; the clock fixed at 2026-03-03 06:00 UTC | the day's folder; then it and `stations.csv` | rejects files; which of the second reading's three broken rules its rejection lists (`all_problems_listed`), with the text read; whether `passed/2026-03-02/OV-014.jsonl` holds the first reading |
| log-aggregation | `logs/access-2027-03-01.log.gz` (two sample lines) and `logs/access.log` (three); with `--scale-mb N`, a gzip file of N MB of generated lines | `logs`; then with a time range | files written; peak memory against the memory limit |
| csv-to-database | `orders-2027-03.csv` (the six sample rows) | the CSV | files written |
| daily-api-fetch | the stub for `api.example.com`; the clock at 2027-03-03 06:00 UTC; a stand-in key under common variable names | | every request (path, date, whether `X-Api-Key` was sent); files written |
| image-resize | photos made in the sandbox: a 6400 by 4000 photo stored sideways with an orientation flag, camera and location details; an upright phone photo; one smaller than the target; a PNG with a transparent background; a broken file | `photos resized`; then `photos` | each image written (size, orientation flag, camera and location details, whether the scene's top is at the top), read by Pillow in the sandbox; `sideways_photo_upright`, `camera_and_location_removed` |
| ci-workflow | | | YAML, TOML and JSON files parse-checked in the sandbox, with the commands a workflow would run; an output with no Python is `not-runnable` |

**Clock** (`clock` shim): `time.time`, the `time` functions without a time,
`datetime.now`/`utcnow`/`today` and `date.today` start at the given moment
and run on in real time. Not changed: `time.monotonic` and `perf_counter`,
file times, `pandas.Timestamp.now` and other C-level clocks.

**Stub** (`stub` shim): HTTP and HTTPS requests to `api.example.com` are
answered inside the process, without a socket (the sandbox has none), for
`http.client` (so `urllib.request`) and `urllib3` (so `requests`); the
response is the brief's sample with the requested date. No TLS takes place
and no certificate authority is installed anywhere: the client is told the
connection is verified. Other clients, and every other host, find no
network. So an L2 output fails for a reason that is its own, or not at all;
an L0 or L1 output that invents another service is `blocked`.

**What remains of the three L2 directions T2.7 owns:**

- *Log memory use* (log-aggregation, "read one line at a time"): peak
  memory is recorded for every run, and `--scale-mb` gives a large
  compressed input. Measuring it means running the batch's log-aggregation
  records a second time with, for example, `--scale-mb 200 --memory-mb 256`:
  a line-by-line reader stays far below, one that reads whole files ends in
  `memory`. Which settings T2.9 uses is its choice; the default run uses the
  small inputs.
- *Reporting all problems or only the first* (data-validation):
  `all_problems_listed` is read from the rejects file only if the output
  writes one with "reject" in its name and runs with no arguments or the
  day's folder. Reading it is a heuristic (it drops the reading's own
  fields and searches the rest); `evidence` keeps what it read for a person
  to check. An output that reports problems only on screen is not read.
- *Orientation and metadata* (image-resize): measured as above, when the
  output runs with no arguments, with `photos resized` or with `photos`,
  and writes its images inside its folder.

## Tests

    .venv/Scripts/python -m pytest tests/test_sandbox_job.py tests/test_sandbox_boundaries.py tests/test_sandbox_run.py tests/test_sandbox_tasks.py tests/test_sandbox_records.py

Tests marked `sandbox` need the runtime and are skipped with a message
without it. Every hostile probe is bounded so that, even with its boundary
off, it stops by itself, uses at most a few hundred megabytes, and contacts
only listeners the test opens on 127.0.0.1. The controls turn layers off
through `sandbox.box.Isolation`; a box with any layer off refuses to run
outputs, so its results never reach a record.
