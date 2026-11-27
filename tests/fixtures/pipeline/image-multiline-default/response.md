```python
from PIL import Image

LOG_ORIENTATION = True


def save(
    img,
    out,
    exif=None,
):
    img.save(out, quality=85)


if __name__ == "__main__":
    with Image.open("a.jpg") as photo:
        save(photo, "b.jpg")
```
