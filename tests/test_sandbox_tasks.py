"""Task hooks of the sandbox (T2.7): fixtures, the fixed clock, the HTTP stub
and the measurements of the L2 directions T2.7 owns (docs/rubrics.md).

The programs here stand in for model outputs: each is small and bounded,
and none contacts anything (requests to api.example.com are answered inside
the sandboxed process by the stub).
"""

from dataclasses import replace

import pytest

from sandbox.box import Limits
from sandbox.run import Settings, run_folder

pytestmark = pytest.mark.sandbox
SMALL = Limits(seconds=60, cpu_seconds=60, memory_mb=768, processes=8, disk_mb=128,
               free_disk_mb=512)


@pytest.fixture
def run(tmp_path):
    from sandbox_support import require_runtime

    require_runtime()

    def make(task, files, **settings):
        folder = tmp_path / "output"
        for name, content in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return run_folder(folder, settings=Settings(
            limits=settings.pop("limits", SMALL), task=("pipeline", task, "L2"), **settings))
    return make


VALIDATE = """
import argparse, csv, datetime, json, pathlib, sys
parser = argparse.ArgumentParser()
parser.add_argument("folder")
args = parser.parse_args()
folder = pathlib.Path(args.folder)
stations = {row["station"] for row in csv.DictReader(open("stations.csv"))}
now = datetime.datetime.now(datetime.timezone.utc)
print("checked at", now.isoformat())
rejects = []
for path in sorted(folder.glob("*.jsonl")):
    for line in path.read_text().splitlines():
        reading = json.loads(line)
        problems = []
        if not -40 <= reading["temp_c"] <= 50: problems.append("temp_c out of range")
        if not 0 <= reading["humidity_pct"] <= 100: problems.append("humidity_pct out of range")
        if not 0 <= reading["rain_mm"] < 150: problems.append("rain_mm out of range")
        if datetime.datetime.fromisoformat(reading["time"].replace("Z", "+00:00")) > now:
            problems.append("time in the future")
        if problems:
            rejects.append({**reading, "problems": problems})
        FIRST_ONLY
pathlib.Path("rejects-2026-03-02.jsonl").write_text(
    "".join(json.dumps(r) + "\\n" for r in rejects))
sys.exit(2 if rejects else 0)
"""


def test_data_validation_runs_on_the_briefs_readings_with_a_fixed_clock(run):
    detail = run("data-validation", {"validate.py": VALIDATE.replace("FIRST_ONLY", "")})
    entry = detail["entry"]
    # It asked for the folder, and was given the day's folder.
    assert entry["command"] == ["python", "validate.py", "incoming/2026-03-02"]
    assert entry["earlier_attempts"][0]["exit_code"] == 2
    assert "checked at 2026-03-03T06:00" in entry["stdout"]
    assert entry["exit_code"] == 2  # a reading rejected: the step says stop
    task = detail["task"]
    assert task["rejects_files"] == ["rejects-2026-03-02.jsonl"]
    assert task["second_reading_problems_listed"] == ["humidity_pct", "rain_mm", "temp_c"]
    assert task["all_problems_listed"] is True
    assert task["exit_code"] == task["expected_exit_code"] == 2


def test_data_validation_that_stops_at_the_first_problem_is_seen(run):
    first_only = VALIDATE.replace("problems.append(\"humidity_pct out of range\")", "pass") \
                         .replace("problems.append(\"rain_mm out of range\")", "pass")
    detail = run("data-validation", {"validate.py": first_only.replace("FIRST_ONLY", "")})
    assert detail["task"]["second_reading_problems_listed"] == ["temp_c"]
    assert detail["task"]["all_problems_listed"] is False


FETCH_REQUESTS = """
import csv, datetime, sys
import requests
day = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
session = requests.Session()
response = session.get("https://api.example.com/v2/air/readings", params={"date": day},
                       headers={"X-Api-Key": "key"}, timeout=30)
response.raise_for_status()
data = response.json()
with open(f"readings-{day[:7]}.csv", "w", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["date", "hour", "station", "pm25", "no2"])
    for r in data["readings"]:
        writer.writerow([data["date"], r["hour"], r["station"], r["pm25"], r["no2"]])
again = session.get("https://api.example.com/v2/air/readings", params={"date": day},
                    headers={"X-Api-Key": "key"}, timeout=30)
print("rows", len(data["readings"]), again.status_code)
"""

FETCH_URLLIB = """
import json, urllib.request
request = urllib.request.Request(
    "https://api.example.com/v2/air/readings?date=2027-03-01", headers={"X-Api-Key": "k"})
with urllib.request.urlopen(request, timeout=30) as response:
    print(json.load(response)["date"])
try:
    urllib.request.urlopen("https://api.example.com/missing", timeout=30)
except urllib.error.HTTPError as error:
    print("missing", error.code)
"""


def test_the_api_stub_serves_requests_and_logs_them(run):
    detail = run("daily-api-fetch", {"fetch.py": FETCH_REQUESTS})
    assert detail["result"] == "ran", detail["entry"]["stderr"]
    assert detail["entry"]["stdout"].strip() == "rows 2 200"
    task = detail["task"]
    assert task["request_count"] == 2
    assert task["requests"][0] == {"path": "/v2/air/readings", "date": "2027-03-02",
                                   "api_key_header": True}
    assert "readings-2027-03.csv" in task["written"]
    assert task["exited_by_itself"] is True


def test_a_fetcher_that_keeps_running_is_seen(run):
    code = "import time\nwhile True:\n    time.sleep(1)  # its own daily schedule\n"
    detail = run("daily-api-fetch", {"fetch.py": code}, limits=replace(SMALL, seconds=3))
    assert detail["result"] == "timeout"
    assert detail["task"]["exited_by_itself"] is False


def test_the_api_stub_serves_urllib_too(run):
    detail = run("daily-api-fetch", {"fetch.py": FETCH_URLLIB})
    assert detail["entry"]["stdout"].split() == ["2027-03-01", "missing", "404"]


def test_other_hosts_still_find_no_network(run):
    code = ("import requests\n"
            "requests.get('http://127.0.0.1:9/', timeout=3)\n")
    detail = run("daily-api-fetch", {"fetch.py": code})
    assert detail["result"] == "blocked", detail["entry"]["stderr"][-500:]


RESIZE = """
import pathlib, sys
from PIL import Image, ImageOps
source, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
target.mkdir(exist_ok=True)
failed = 0
for path in sorted(source.iterdir()):
    try:
        with Image.open(path) as image:
            UPRIGHT
            image = image.convert("RGBA")
            white = Image.new("RGBA", image.size, "white")
            white.alpha_composite(image)
            photo = white.convert("RGB")
            photo.thumbnail((1600, 1600))
            photo.save(target / (path.stem + ".jpg"), quality=85)
    except Exception as error:
        failed += 1
print("failed", failed)
"""


def test_image_resize_upright_and_without_metadata(run):
    code = RESIZE.replace("UPRIGHT", "image = ImageOps.exif_transpose(image)")
    detail = run("image-resize", {"resize.py": code})
    assert detail["entry"]["command"] == ["python", "resize.py", "photos", "resized"]
    assert detail["entry"]["stdout"].strip() == "failed 1"
    task = detail["task"]
    assert task["sideways_photo_upright"] is True
    assert task["camera_and_location_removed"] is True
    sizes = {item["path"]: item["size"] for item in task["images"]}
    assert sizes["resized/mug-blue-01.jpg"] == [1000, 1600]
    assert sizes["resized/bowl-small-04.jpg"] == [800, 600]


def test_image_resize_that_keeps_photos_sideways_is_seen(run):
    code = RESIZE.replace("UPRIGHT", "exif = image.getexif()").replace(
        "quality=85)", "quality=85, exif=exif)")
    detail = run("image-resize", {"resize.py": code})
    task = detail["task"]
    assert task["sideways_photo_upright"] is False
    assert task["camera_and_location_removed"] is False


AGGREGATE = """
import gzip, pathlib, sys
lines = 0
for path in sorted(pathlib.Path(sys.argv[1]).iterdir()):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        READ
print("lines", lines)
"""


def test_log_aggregation_memory_on_a_large_input(run):
    streaming = AGGREGATE.replace("READ", "for line in handle:\n            lines += 1")
    whole = AGGREGATE.replace("READ", "text = handle.read()\n        lines += text.count('\\n')")
    limits = replace(SMALL, memory_mb=160)
    small = run("log-aggregation", {"agg.py": streaming}, limits=limits, scale_mb=200)
    assert small["result"] == "ran", small["entry"]["stderr"][-500:]
    assert small["task"]["peak_memory_mb"] < 100
    large = run("log-aggregation", {"agg.py": whole}, limits=limits, scale_mb=200)
    assert large["result"] == "memory", large["entry"]


def test_csv_fixture_and_the_files_written(run):
    code = ("import csv, sqlite3, sys\n"
            "rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8')))\n"
            "db = sqlite3.connect('orders.db')\n"
            "db.execute('create table if not exists orders (order_id)')\n"
            "db.executemany('insert into orders values (?)', [(r['order_id'],) for r in rows])\n"
            "db.commit()\nprint('read', len(rows))\n")
    detail = run("csv-to-database", {"load.py": code})
    assert detail["entry"]["stdout"].strip() == "read 6"
    assert detail["task"]["written"] == ["orders.db"]
