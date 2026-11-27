```python
import asyncio
import json
import os

import httpx

URL = "https://example.org/api/daily"


async def main():
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(URL, params={"key": os.getenv("API_KEY")})
        r.raise_for_status()
        data = r.json()
    with open("daily.json", "w") as f:
        json.dump(data, f)


if __name__ == "__main__":
    asyncio.run(main())
```
