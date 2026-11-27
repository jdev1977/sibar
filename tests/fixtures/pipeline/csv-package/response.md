# Order pipeline

This uses only the standard library.

## Layout

- `pipeline.py` does the work
- `test_pipeline.py` tests the cleaning rules

**pipeline.py**

```python
#!/usr/bin/env python3
"""Clean an order export and load it into SQLite."""
import argparse
import csv
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


def clean_email(value):
    """Lower-case and trim an address."""
    return value.strip().lower()


def load(source: Path, database: Path) -> int:
    # stream the rows, one at a time
    connection = sqlite3.connect(database)
    rejects = []
    with open(source, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row["order_id"].strip():
                rejects.append(row)
                continue
            connection.execute("INSERT OR REPLACE INTO orders VALUES (?, ?)",
                               (row["order_id"], clean_email(row["customer_email"])))
    connection.commit()
    with open("rejects.csv", "w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=["order_id", "customer_email"])
        writer.writerows(rejects)
    log.info("rejected %d", len(rejects))
    return len(rejects)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--db", default="orders.db")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(f"Rejected: {load(args.source, Path(args.db))}")


if __name__ == "__main__":
    main()
```

**test_pipeline.py**

```python
import unittest

from pipeline import clean_email


class CleanTest(unittest.TestCase):
    def test_email(self):
        self.assertEqual(clean_email(" A@Example.COM "), "a@example.com")


if __name__ == "__main__":
    unittest.main()
```

Run it with:

```bash
python pipeline.py orders-2027-03.csv
```
