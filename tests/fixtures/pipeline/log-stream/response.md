**logagg/__init__.py**

```python
"""Log aggregation."""
```

**logagg/parse.py**

```python
import gzip


def read(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        for line in handle:
            yield line.split()
```

**logagg/__main__.py**

```python
import argparse
import csv
import sys
import tomllib

from logagg.parse import read

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="logagg.toml")
args = parser.parse_args()
with open(args.config, "rb") as handle:
    config = tomllib.load(handle)
writer = csv.writer(sys.stdout)
```

**tests/test_parse.py**

```python
from logagg.parse import read


def test_read(tmp_path):
    path = tmp_path / "a.log"
    path.write_text("a b\n")
    assert list(read(path)) == [["a", "b"]]
```

**pyproject.toml**

```toml
[project]
name = "logagg"
```

**README.md**

```markdown
Run it as a module.
```
