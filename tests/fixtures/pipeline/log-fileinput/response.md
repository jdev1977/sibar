A single script that streams every file with `fileinput`, so only one line is in memory at a time:

```python
#!/usr/bin/env python3
import fileinput
import json
import sys
from collections import Counter


def main():
    with open("settings.json") as cfg:
        settings = json.load(cfg)
    counts = Counter()
    bad = 0
    for raw in fileinput.input(files=sys.argv[1:], encoding="utf-8"):
        parts = raw.split()
        if len(parts) != 4:
            bad += 1
            continue
        counts[parts[1]] += 1
    for path, n in counts.most_common(settings.get("top", 10)):
        print(path, n)
    print("bad lines:", bad)


if __name__ == "__main__":
    main()
```
