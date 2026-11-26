The core:

```python
import csv
import sqlite3

def load(path):
    connection = sqlite3.connect("a.db")
    with open(path) as handle:
        for row in csv.reader(handle):
            connection.execute("INSERT INTO t VALUES (?)", row)
    connection.commit()
    connection.close()
```

If your file is large, change the loop like this:

```python
def load_batched(path, size=1000):
    connection = sqlite3.connect("a.db")
    with open(path) as handle:
        reader = csv.reader(handle)
        while batch := list(itertools.islice(reader, size)):
            connection.executemany("INSERT INTO t VALUES (?)", batch)
    connection.commit()
    connection.close()
```
