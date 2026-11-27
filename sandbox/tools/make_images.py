"""Makes the image-resize task's input photos, inside the sandbox (T2.7).

``python -I make_images.py <folder>`` writes, matching the L2 brief: a large
camera photo stored sideways with an orientation flag and camera and
location details, a phone photo already upright, a photo smaller than the
target, a PNG with a transparent background, and a file that is not an image.
"""

import os
import sys

from PIL import Image


def gradient(width, height, colour):
    image = Image.new("RGB", (width, height), colour)
    # A darker band at the top of the scene, so orientation can be checked.
    band = Image.new("RGB", (width, max(1, height // 8)), (20, 20, 20))
    image.paste(band, (0, 0))
    return image


def main():
    folder = sys.argv[1]
    os.makedirs(folder, exist_ok=True)
    # Stored 6400 x 4000 (sideways); orientation 6 says: turn 90 degrees
    # clockwise to view, so the upright photo is 4000 wide and 6400 high.
    sideways = gradient(4000, 6400, (180, 120, 60)).transpose(Image.Transpose.ROTATE_90)
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation
    exif[0x010F] = "Example Camera Co"  # Make
    exif[0x0110] = "EC-100"  # Model
    exif[0x0131] = "Example Firmware 1.0"  # Software
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (51.0, 30.0, 0.0)
    gps[3], gps[4] = "E", (0.0, 7.0, 0.0)
    sideways.save(os.path.join(folder, "mug-blue-01.jpg"), quality=90, exif=exif)
    upright = gradient(3000, 4000, (90, 140, 200))
    exif = Image.Exif()
    exif[0x0112] = 1
    exif[0x010F] = "Example Phone Co"
    upright.save(os.path.join(folder, "plate-green-02.jpg"), quality=90, exif=exif)
    gradient(800, 600, (200, 200, 120)).save(os.path.join(folder, "bowl-small-04.jpg"),
                                             quality=90)
    clear = Image.new("RGBA", (2400, 1800), (0, 0, 0, 0))
    clear.paste(Image.new("RGBA", (1200, 900), (30, 90, 160, 255)), (600, 450))
    clear.save(os.path.join(folder, "vase-tall-03.png"))
    with open(os.path.join(folder, "cup-broken-05.jpg"), "wb") as handle:
        handle.write(b"not a JPEG file")
    print("made 5 files")


if __name__ == "__main__":
    main()
