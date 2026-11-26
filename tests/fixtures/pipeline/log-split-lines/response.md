```python
import sys
from collections import Counter


def summarize(path):
    with open(path) as f:
        all_lines = f.read().splitlines()
    counts = Counter()
    for line in all_lines:
        fields = line.split(" ")
        if len(fields) < 4:
            continue
        counts[fields[2]] += 1
    return counts


if __name__ == "__main__":
    total = Counter()
    for p in sys.argv[1:]:
        total += summarize(p)
    for status, n in sorted(total.items()):
        print(status, n)
```
