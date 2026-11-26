```python
import re
from collections import Counter

with open("access.log") as handle:
    lines = handle.readlines()

paths = Counter(line.split()[2] for line in lines if line.strip())
print(paths.most_common(10))
```
