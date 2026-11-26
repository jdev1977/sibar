"""Reads the image-resize task's output photos, inside the sandbox (T2.7).

``python -I measure_images.py <result file> <image> ...`` writes, for each
image: its size, its orientation flag, whether camera or location details
remain, and whether the dark band painted at the top of each input scene is
at the top. The images were written by untrusted code: Pillow reads them in
the sandbox, never outside it.
"""

import json
import sys

from PIL import Image

Image.MAX_IMAGE_PIXELS = 50_000_000
CAMERA_TAGS = {0x010F: "Make", 0x0110: "Model", 0x0131: "Software"}


def measure(path):
    found = {"path": path}
    try:
        with Image.open(path) as image:
            found["format"] = image.format
            found["size"] = list(image.size)
            found["mode"] = image.mode
            exif = image.getexif()
            found["orientation"] = exif.get(0x0112)
            found["camera"] = sorted(name for tag, name in CAMERA_TAGS.items() if tag in exif)
            found["location"] = bool(exif.get_ifd(0x8825)) or 0x8825 in exif
            rgb = image.convert("RGB")
            width, height = rgb.size
            top = rgb.getpixel((width // 2, max(0, height // 40)))
            bottom = rgb.getpixel((width // 2, height - 1 - height // 40))
            corner = rgb.getpixel((0, 0))
            found["dark_band_at_top"] = sum(top) < 150 and sum(bottom) > 150
            found["corner"] = list(corner)
    except Exception as error:
        found["error"] = f"{type(error).__name__}: {error}"[:200]
    return found


def main():
    result, paths = sys.argv[1], sys.argv[2:]
    with open(result, "w", encoding="utf-8") as handle:
        json.dump([measure(path) for path in paths[:200]], handle)


if __name__ == "__main__":
    main()
