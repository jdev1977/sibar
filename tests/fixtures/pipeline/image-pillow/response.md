```python
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps


def resize(source: Path, target: Path):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((1600, 1600))
        # saving without the exif argument drops camera and location details
        image.convert("RGB").save(target, "JPEG", quality=85, exif=b"")


if __name__ == "__main__":
    files = list(Path("photos").glob("*"))
    with ProcessPoolExecutor() as pool:
        list(pool.map(resize, files, [Path("out") / f.name for f in files]))
    print(f"{len(files)} photos")
```
