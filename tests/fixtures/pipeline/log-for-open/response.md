Here's a small log aggregation package that reads each file one line at a time, so memory stays flat no matter how big the logs are.

**`logagg/__init__.py`**
```python
"""Aggregate request logs."""
```

**`logagg/parser.py`**
```python
import re
from dataclasses import dataclass

LINE_RE = re.compile(r"^(?P<ts>\S+) (?P<path>\S+) (?P<status>\d{3}) (?P<ms>\d+)$")


@dataclass
class Request:
    ts: str
    path: str
    status: int
    ms: int


def parse_line(line):
    m = LINE_RE.match(line.strip())
    if not m:
        return None
    return Request(m["ts"], m["path"], int(m["status"]), int(m["ms"]))
```

**`logagg/cli.py`**
```python
import argparse
import csv
import sys
from collections import Counter, defaultdict

from logagg.parser import parse_line


def iter_requests(paths, bad):
    for path in paths:
        for line in open(path, encoding="utf-8"):
            req = parse_line(line)
            if req is None:
                bad.append(line.rstrip("\n"))
                continue
            yield req


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--out", default="hourly.csv")
    args = ap.parse_args(argv)
    bad = []
    hourly = defaultdict(int)
    statuses = Counter()
    for req in iter_requests(args.logs, bad):
        hourly[req.ts[:13]] += 1
        statuses[req.status] += 1
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["hour", "requests"])
        for hour in sorted(hourly):
            w.writerow([hour, hourly[hour]])
    print(f"Malformed lines: {len(bad)}")
    for line in bad[:5]:
        print("  ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**`tests/test_parser.py`**
```python
from logagg.parser import parse_line


def test_good_line():
    r = parse_line("2024-05-01T10:00:00 /api 200 35")
    assert r.status == 200


def test_bad_line():
    assert parse_line("garbage") is None
```

Run it with `python -m logagg.cli access-*.log --out hourly.csv`.
