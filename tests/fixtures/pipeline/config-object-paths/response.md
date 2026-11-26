The paths come from a settings object, and the whole input is read at once.

```python
import json
from pathlib import Path

import config


def main():
    with open(config.input_path) as f:
        records = json.load(f)
    header = Path(config.paths["header"]).read_text()
    print(header, len(records))


if __name__ == "__main__":
    main()
```
