```python
import os
import sys
from multiprocessing import Pool

from PIL import Image, ImageOps

MAX_SIDE = 1600


def resize_one(args):
    src, dst = args
    try:
        with Image.open(src) as im:
            new_img = ImageOps.exif_transpose(im)
            new_img.thumbnail((MAX_SIDE, MAX_SIDE))
            new_img.save(dst, "JPEG", quality=90)
        return src, None
    except Exception as exc:  # keep going on bad files
        return src, str(exc)


def main(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    jobs = [(os.path.join(src_dir, n), os.path.join(dst_dir, n))
            for n in os.listdir(src_dir) if n.lower().endswith((".jpg", ".jpeg"))]
    with Pool() as pool:
        results = pool.map(resize_one, jobs)
    failed = [r for r in results if r[1]]
    print(f"resized {len(results) - len(failed)}, failed {len(failed)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```
