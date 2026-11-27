Here's a Python script using Pillow that resizes every photo in a folder to 1200 px wide. It fixes orientation by reading the EXIF Orientation tag itself.

```python
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

ORIENTATION = 274
ROTATE = {3: 180, 6: 270, 8: 90}


def process(src: Path, dest_dir: Path, width: int = 1200):
    dest = dest_dir / src.name
    with Image.open(src) as img:
        exif = img.getexif()
        angle = ROTATE.get(exif.get(ORIENTATION, 1))
        if angle:
            img = img.rotate(angle, expand=True)
        ratio = width / img.width
        scaled = img.resize((width, round(img.height * ratio)), Image.LANCZOS)
        scaled.save(dest, quality=85)
    return dest


def main():
    src_dir, dest_dir = Path(sys.argv[1]), Path(sys.argv[2])
    dest_dir.mkdir(exist_ok=True)
    photos = sorted(src_dir.glob("*.jpg"))
    with ProcessPoolExecutor() as pool:
        for result in pool.map(process, photos, [dest_dir] * len(photos)):
            print("wrote", result)


if __name__ == "__main__":
    main()
```
