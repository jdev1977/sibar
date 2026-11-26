Here is a small script that runs every day.

```python
import json
import os
import time

import requests
import schedule
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
API_KEY = os.environ["AIR_API_KEY"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def fetch(day):
    response = requests.get("https://api.example.com/v2/air/readings",
                            params={"date": day},
                            headers={"X-Api-Key": API_KEY}, timeout=30)
    response.raise_for_status()
    return response.json()


def job():
    data = fetch(time.strftime("%Y-%m-%d"))
    with open("readings.json", "w") as handle:
        json.dump(data, handle)
    print("stored", len(data["readings"]))


schedule.every().day.at("06:00").do(job)
while True:
    schedule.run_pending()
    time.sleep(60)
```

Install the dependencies:

```text
requests
schedule
python-dotenv
tenacity
```
