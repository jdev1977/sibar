```python
import csv
import datetime as dt
import os

import requests
import urllib3

urllib3.disable_warnings()

API_URL = "https://example.org/v1/readings"
API_KEY = os.environ["WEATHER_API_KEY"]


def fetch(day):
    resp = requests.get(API_URL, params={"date": day.isoformat()},
                        headers={"Authorization": f"Bearer {API_KEY}"},
                        timeout=30, verify=False)
    resp.raise_for_status()
    return resp.json()


def main():
    day = dt.date.today() - dt.timedelta(days=1)
    rows = fetch(day)
    with open(f"readings-{day:%Y-%m}.csv", "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["station", "hour", "temp"])
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    main()
```
