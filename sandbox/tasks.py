"""Task hooks: fixture inputs, settings and measurements for the tasks whose
prompts say how the sandbox should run them (prompts/pipeline/README.md,
"Running offline"; docs/rubrics.md, the L2 directions T2.7 owns).

A hook is chosen by ``(project_type, task_id)``. Before the output runs it
writes the task's input files beside the output's own (from the L2 brief's
sample data, which suits L0 and L1 as well) and may set a fixed clock or the
HTTP stub; it may name arguments to try when the entry point asks for some;
after the run it reports what the output wrote. Every measurement reads
files the untrusted code wrote, so images and configuration files are read
by helper scripts in the sandbox, and text files only up to a size limit.
"""

import gzip
import json
import random
import re

from sandbox import files as safe

LISTED = 50  # files reported as written by the output
TEXT_LIMIT = 256 << 10


def clock_environment(start):
    return {"SIBAR_SANDBOX_SHIMS": "clock", "SIBAR_SANDBOX_CLOCK": start}


def _merge_shims(environment, name, extra):
    shims = [s for s in environment.get("SIBAR_SANDBOX_SHIMS", "").split(",") if s]
    environment.update(extra)
    environment["SIBAR_SANDBOX_SHIMS"] = ",".join(sorted(set(shims + [name])))
    return environment


class Hook:
    """No fixtures and no measurements beyond the files written."""

    clock = None  # a fixed start time for the run, ISO 8601 with a zone
    arguments = ()  # argument lists to try, in turn, if the entry asks for some
    configs = False  # parse-check YAML/TOML/JSON files (also with no Python)

    def __init__(self, scale_mb=0):
        self.scale_mb = scale_mb
        self._before = {}

    def write_inputs(self, app):
        """Write the task's input files under ``app``."""

    def prepare(self, box, settings):
        self.write_inputs(box.app)
        self._before = safe.listing(box.app, 10_000)
        environment = {}
        if self.clock and not settings.clock:
            environment.update(clock_environment(self.clock))
        return environment

    def written(self, box):
        """Files the output wrote or changed, under its folder."""
        now = safe.listing(box.app, 10_000)
        return sorted(path for path, size in now.items()
                      if path not in self._before or self._before[path] != size)

    def read_text(self, box, relative):
        data = safe.read_file(box.app, relative, TEXT_LIMIT)
        return None if data is None else data.decode("utf-8", "replace")

    def measure(self, box, detail):
        written = self.written(box)
        return {"written": written[:LISTED], "written_count": len(written)}

    def static(self, source, paths):
        return {}


# --- data-validation ----------------------------------------------------------------------

READINGS = (
    '{"station": "OV-014", "time": "2026-03-02T13:00:00Z", "temp_c": 11.4, '
    '"humidity_pct": 81, "rain_mm": 0.2, "battery_v": 3.9}\n'
    '{"station": "OV-014", "time": "2026-03-02T14:00:00Z", "temp_c": 61.0, '
    '"humidity_pct": 104, "rain_mm": -1, "battery_v": 3.1}\n')
STATIONS = "station,name\nOV-014,Mill Lane School\nOV-027,Fenby Farm\n"
BROKEN = {"temp_c": ("temp",), "humidity_pct": ("humid",), "rain_mm": ("rain",)}


READING_FIELDS = ("station", "time", "temp_c", "humidity_pct", "rain_mm", "battery_v")
SECOND_READING = READINGS.splitlines()[1]


def _problem_text(content):
    """The parts of a rejects file that describe the second reading's
    problems, with the reading's own fields taken out (they name the same
    fields whether or not a problem is listed). A heuristic: JSON lines and
    CSV rows lose the reading's columns; other text loses the reading as
    the brief wrote it and its ``"field": value`` pairs."""
    lines = [line for line in content.splitlines() if "14:00" in line]
    if not lines:
        return []
    first = content.splitlines()[0]
    if "," in first and "temp_c" in first and not first.lstrip().startswith("{"):
        import csv
        import io

        rows = csv.DictReader(io.StringIO(content))
        return [" ".join(str(v) for k, v in row.items()
                         if k not in READING_FIELDS and v is not None)
                for row in rows if "14:00" in str(row.get("time", ""))
                or any("14:00" in str(v) for v in row.values())]
    parts = []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            value = None
        if isinstance(value, dict):
            rest = {key: item for key, item in value.items()
                    if key not in READING_FIELDS and not (
                        isinstance(item, dict) and len(set(item) & set(READING_FIELDS)) >= 3)}
            parts.append(json.dumps(rest))
        else:
            stripped = line.replace(SECOND_READING, "")
            stripped = re.sub(r'"(?:%s)"\s*:\s*[^,}]+' % "|".join(READING_FIELDS), "", stripped)
            parts.append(stripped)
    return parts


class DataValidation(Hook):
    """The brief's two readings: the first passes; the second breaks three
    rules (temperature, humidity, rain) and carries a battery warning. The
    rule "no later than the moment of the check" makes the clock fixed: the
    morning after the readings."""

    clock = "2026-03-03T06:00:00+00:00"
    arguments = (["incoming/2026-03-02"], ["incoming/2026-03-02", "stations.csv"])

    def write_inputs(self, app):
        day = app / "incoming" / "2026-03-02"
        day.mkdir(parents=True, exist_ok=True)
        (day / "OV-014.jsonl").write_text(READINGS, encoding="utf-8")
        (app / "stations.csv").write_text(STATIONS, encoding="utf-8")

    def measure(self, box, detail):
        found = super().measure(box, detail)
        rejects = [path for path in found["written"] if "reject" in path.lower()]
        found["rejects_files"] = rejects
        listed, evidence = set(), []
        for path in rejects:
            for part in _problem_text(self.read_text(box, path) or ""):
                evidence.append(part[:300])
                for field, words in BROKEN.items():
                    if field in part or any(word in part.lower() for word in words):
                        listed.add(field)
        found["second_reading_problems_listed"] = sorted(listed)
        found["all_problems_listed"] = (len(listed) == len(BROKEN)) if rejects else None
        # What the count was read from, for a person to check the reading.
        found["evidence"] = evidence[:5]
        passed = self.read_text(box, "passed/2026-03-02/OV-014.jsonl")
        found["passed_file"] = None if passed is None else passed.strip() == READINGS.splitlines()[0]
        return found


# --- log-aggregation ----------------------------------------------------------------------

LOG_LINES = (
    "2027-03-02T14:05:31Z GET /recipes/lentil-soup 200 15320 0.042 ip=203.0.113.7\n"
    "2027-03-02T14:05:33Z GET /search?q=bread 200 8811 0.310 ip=198.51.100.23\n"
    "2027-03-02T14:06:02Z POST /comments 500 312 1.204 ip=203.0.113.7\n"
    "2027-03-02T14:06:10Z GET /favicon.ico 404 0 0.003 ip=192.0.2.44\n"
    "2027-03-02 14:06:11 GET /recipes/oat-cakes 200\n")
PATHS = ("/recipes/lentil-soup", "/search?q=bread", "/comments", "/about",
         "/recipes/oat-cakes", "/recipes/rye-bread", "/favicon.ico")


class LogAggregation(Hook):
    """The brief's five sample lines (four requests, one with status 500, one
    malformed line): the first two in a gzip file of the day before, the rest
    in the current plain file. With ``scale_mb``, a further gzip file holds
    that many megabytes of generated lines (compressed, so the disk limit is
    not reached): run it under a tight memory limit to see whether an output
    reads one line at a time, the L2 direction T2.7 measures."""

    arguments = (["logs"], ["logs", "--start", "2027-03-01T00:00:00Z",
                            "--end", "2027-03-03T00:00:00Z"])

    def write_inputs(self, app):
        logs = app / "logs"
        logs.mkdir(exist_ok=True)
        lines = LOG_LINES.splitlines(keepends=True)
        with gzip.open(logs / "access-2027-03-01.log.gz", "wt", encoding="utf-8") as out:
            out.writelines(lines[:2])
        (logs / "access.log").write_text("".join(lines[2:]), encoding="utf-8")
        if self.scale_mb:
            chance = random.Random(2027)
            with gzip.open(logs / "access-2027-02-28.log.gz", "wt", encoding="utf-8",
                           compresslevel=6) as out:
                written = 0
                while written < self.scale_mb << 20:
                    line = (f"2027-02-28T{chance.randrange(24):02d}:{chance.randrange(60):02d}:"
                            f"{chance.randrange(60):02d}Z GET {chance.choice(PATHS)} "
                            f"{chance.choice((200, 200, 200, 404, 500))} "
                            f"{chance.randrange(50000)} {chance.random():.3f} "
                            f"ip=203.0.113.{chance.randrange(256)}\n")
                    out.write(line)
                    written += len(line)

    def measure(self, box, detail):
        found = super().measure(box, detail)
        entry = detail.get("entry") or {}
        found["scale_mb"] = self.scale_mb
        found["peak_memory_mb"] = entry.get("peak_memory_mb")
        found["memory_limit_mb"] = detail["settings"]["limits"]["memory_mb"]
        return found


# --- csv-to-database ---------------------------------------------------------------------

ORDERS = (
    "order_id,order_date,customer_email,product,quantity,unit_price\n"
    "1001,2027-03-02, Ana.Ruiz@Example.com ,Smoky Lapsang 100 g,2,$12.50\n"
    "1002,03/02/2027,ben.okoro@example.com,Jasmine Pearls 50 g,1,9\n"
    "1002,03/02/2027,ben.okoro@example.com,Jasmine Pearls 50 g,1,9\n"
    ',"Mar 3, 2027",cleo@example.com,Assam Breakfast 250 g,1,14.00\n'
    "1004,2027-03-04,dan@example.com,Sencha 100 g,0,$11.00\n"
    '1005,"Mar 4, 2027",EVA@example.com,Rooibos Vanilla 100 g,3,7.25\n')


class CsvToDatabase(Hook):
    """The brief's six rows: three load, two are rejected, one repeat is
    dropped."""

    arguments = (["orders-2027-03.csv"],)

    def write_inputs(self, app):
        (app / "orders-2027-03.csv").write_text(ORDERS, encoding="utf-8")


# --- daily-api-fetch ---------------------------------------------------------------------

RESPONSE = ('{"date": "{query.date}", "readings": [{"station": "north-park", "hour": 0, '
            '"pm25": 8.1, "no2": 21.4}, {"station": "north-park", "hour": 1, "pm25": null, '
            '"no2": 19.8}]}')
API_KEY_NAMES = ("API_KEY", "X_API_KEY", "AIR_API_KEY", "AIR_QUALITY_API_KEY",
                 "QUELLMOUTH_API_KEY", "OPEN_DATA_API_KEY")


class DailyApiFetch(Hook):
    """The L2 brief's API, served by the stub at ``api.example.com`` (any
    date gets the brief's sample readings for that date). The clock is fixed
    at 6:00 on the morning after 2027-03-02, when the brief's scheduler
    starts the run. A key is in the environment under common names, with a
    value that is not a key. Each request is logged."""

    clock = "2027-03-03T06:00:00+00:00"

    def prepare(self, box, settings):
        environment = super().prepare(box, settings)
        spec_folder = box.folder / "stub"
        spec_folder.mkdir(exist_ok=True)
        log = box.folder / "out" / "stub-requests.jsonl"
        spec = {"hosts": {"api.example.com": [
            {"method": "GET", "path": "/v2/air/readings", "body": RESPONSE}]},
            "log": str(log)}
        (spec_folder / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        _merge_shims(environment, "stub", {"SIBAR_SANDBOX_STUB": str(spec_folder / "spec.json")})
        if environment.get("SIBAR_SANDBOX_CLOCK") or settings.clock:
            environment["SIBAR_SANDBOX_SHIMS"] = "clock,stub"
        for name in API_KEY_NAMES:
            environment[name] = "sandbox-not-a-key"
        return environment

    def measure(self, box, detail):
        found = super().measure(box, detail)
        data = safe.read_file(box.folder, "out/stub-requests.jsonl", TEXT_LIMIT) or b""
        requests = []
        for line in data.decode("utf-8", "replace").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                query = item.get("query") if isinstance(item.get("query"), dict) else {}
                requests.append({"path": str(item.get("path"))[:200],
                                 "date": str(query.get("date"))[:40],
                                 "api_key_header": "x-api-key" in (item.get("headers") or [])})
        found["requests"] = requests[:50]
        found["request_count"] = len(requests)
        return found


# --- image-resize ------------------------------------------------------------------------


class ImageResize(Hook):
    """Photos made in the sandbox by tools/make_images.py (see there). After
    the run, tools/measure_images.py reads every image the output wrote:
    size, orientation flag, camera and location details, and whether the
    scene's top is at the top: the L2 directions "turned upright" and
    "camera and location details removed"."""

    arguments = (["photos", "resized"], ["photos"])

    def prepare(self, box, settings):
        tools = box.folder / "tools"
        run = box.run([box.python(), "-I", str(tools / "make_images.py"),
                       str(box.app / "photos")])
        if run.exit_code != 0:
            raise OSError("the task's photos could not be made: "
                          + run.stderr.decode("utf-8", "replace")[-300:])
        return super().prepare(box, settings)

    def measure(self, box, detail):
        found = super().measure(box, detail)
        images = [path for path in found["written"]
                  if path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        if not images:
            found["images"] = []
            return found
        result = box.folder / "out" / "images.json"
        box.run([box.python(), "-I", str(box.folder / "tools" / "measure_images.py"),
                 str(result)] + [str(box.app.joinpath(*p.split("/"))) for p in images[:200]])
        data = safe.read_file(box.folder, "out/images.json", 1 << 20)
        try:
            measured = json.loads(data) if data else []
        except ValueError:
            measured = []
        prefix = str(box.app) + "\\"
        images_found = []
        for item in measured if isinstance(measured, list) else []:
            if isinstance(item, dict):
                item = {key: item.get(key) for key in (
                    "path", "format", "size", "orientation", "camera", "location",
                    "dark_band_at_top", "error")}
                item["path"] = str(item["path"]).replace(prefix, "").replace("\\", "/")[:200]
                images_found.append(item)
        found["images"] = images_found
        mugs = [item for item in images_found if "mug-blue-01" in item["path"]]
        if mugs:
            mug = mugs[0]
            size = mug.get("size") or [0, 0]
            found["sideways_photo_upright"] = bool(
                size[1] > size[0] and (mug.get("orientation") in (None, 1))
                and mug.get("dark_band_at_top"))
            found["camera_and_location_removed"] = not (mug.get("camera") or mug.get("location"))
        return found


# --- ci-workflow -------------------------------------------------------------------------


class CiWorkflow(Hook):
    """A workflow needs its build service, so its files are only parse-checked
    (tools/parse_config.py, in the sandbox) and the commands it would run are
    listed. Package code in the output runs as for any output."""

    configs = True

    def measure(self, box, detail):
        found = super().measure(box, detail)
        found["configs"] = parse_configs(box)
        return found


def parse_configs(box):
    names = [path for path in safe.listing(box.app, 10_000)
             if path.lower().endswith((".yml", ".yaml", ".toml", ".json"))][:100]
    if not names:
        return []
    result = box.folder / "out" / "configs.json"
    box.run([box.python(), "-I", str(box.folder / "tools" / "parse_config.py"),
             str(result), str(box.app)] + names)
    data = safe.read_file(box.folder, "out/configs.json", 1 << 20)
    try:
        checked = json.loads(data) if data else []
    except ValueError:
        return []
    out = []
    for item in checked if isinstance(checked, list) else []:
        if isinstance(item, dict):
            out.append({"path": str(item.get("path"))[:200],
                        "parses": item.get("parses") is True,
                        "error": str(item["error"])[:300] if item.get("error") else None,
                        "commands": [str(c)[:300] for c in (item.get("commands") or [])][:50]})
    return out


HOOKS = {
    ("pipeline", "data-validation"): DataValidation,
    ("pipeline", "log-aggregation"): LogAggregation,
    ("pipeline", "csv-to-database"): CsvToDatabase,
    ("pipeline", "daily-api-fetch"): DailyApiFetch,
    ("pipeline", "image-resize"): ImageResize,
    ("pipeline", "ci-workflow"): CiWorkflow,
}


def hook_for(task, scale_mb=0):
    """The hook for ``task`` (``(project_type, task_id, level)``), or None."""
    if not task:
        return None
    cls = HOOKS.get((task[0], task[1]))
    return cls(scale_mb) if cls else None
