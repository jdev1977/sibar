```python
"""Validate readings.

Example: import pandas as pd  (not used here); retry on failure is not needed.
"""
import json

# TODO: you could add retries and a logging setup; os.environ["API_KEY"] later
MESSAGE = "import requests; print(token)"


def check(reading):
    if reading.get("temp_c") is None:
        return ["temp_c missing"]
    return []
```
