"""Image orientation and metadata handling in pipeline code: which calls and
keywords are present. Whether they do what a brief means is for the sandbox
to show on its fixture images."""

import re

from extractors.base import Extractor
from extractors.common.response import NO_INPUT, get_doc, result
from extractors.pipeline.libraries import read_imports
from extractors.pipeline.source import get_output

_LIBRARIES = {
    "pillow": "pillow", "pillow_heif": "pillow", "opencv-python": "opencv",
    "wand": "wand", "pyvips": "pyvips", "imageio": "imageio",
    "scikit-image": "scikit-image", "piexif": "piexif", "exifread": "exifread",
    "sharp": "sharp", "jimp": "jimp", "gm": "gm", "imagemagick": "imagemagick",
    "github.com/disintegration/imaging": "go-imaging",
    "golang.org/x/image": "go-x-image", "image/jpeg": "go-image",
    "image": "rust-image", "ruby-vips": "ruby-vips", "mini_magick": "mini-magick",
    "image_processing": "image-processing", "magick": "r-magick",
    "exifr": "exifr", "piexifjs": "piexif",
}
_COMMAND = re.compile(
    r"(?:^|[|;&(][ \t]{0,10}|\$\()[ \t]{0,40}(?:magick|mogrify|convert)\b[^\n]{0,200}"
    r"-(?:resize|thumbnail|auto-orient|strip)\b", re.M)
_ORIENTATION = tuple((name, re.compile(pattern, flags)) for name, pattern, flags in (
    ("exif-transpose", r"\bexif_transpose\b", 0),
    ("auto-orient", r"auto[-_]?orient|\bautorot|\bAutoOrientation\b", re.IGNORECASE),
    ("orientation-tag", r"\b0x0112\b|[\"']Orientation[\"']|\bOrientation\b ?[\])=:]|"
                        r"\bget\( ?274\b|\[ ?274 ?\]", 0),
))
_SHARP_ROTATE = re.compile(r"\.rotate\(\s?\)")
_METADATA = tuple((name, kind, re.compile(pattern, flags))
                  for name, kind, pattern, flags in (
    ("empty-exif", "strips", r"\bexif ?= ?(?:b[\"'][\"']|None\b)", 0),
    ("strip-option", "strips", r"(?<![\w-])-strip\b|\.strip_metadata\b|\bstrip ?[=:] ?"
                               r"(?:True|true)\b|\bStripMetadata\b", 0),
    ("remove-function", "strips", r"(?:strip|remove|drop|clear)_?(?:all_?)?"
                                  r"(?:exif|metadata)", re.IGNORECASE),
    ("pixel-copy", "strips", r"\.putdata\(", 0),
    ("delete-exif", "strips", r"\.info\.pop\( ?[\"']exif|\bdel [\w.]{0,40}\.info\b|"
                              r"\bpiexif\.remove\(", 0),
    ("keeps-exif", "keeps", r"\bexif ?= ?(?!b[\"']|None\b)[A-Za-z_]|"
                            r"\bpiexif\.(?:insert|transplant)\(", 0),
    ("with-metadata", "keeps", r"\.(?:withMetadata|keepMetadata|keepExif)\(", 0),
))


def images(inputs):
    output = get_output(inputs)
    if not output.main:
        return dict(NO_INPUT)
    read = read_imports(inputs)
    used = set() if read is None else read[0] | read[1]
    languages = {c.language for c in output.main}
    libraries = {name for key, name in _LIBRARIES.items() if key in used
                 and (key not in ("image", "magick") or languages &
                      ({"rust"} if key == "image" else {"r"}))}
    code = output.text("code")
    if any(c.language in ("shell", "powershell", "batch") and
           _COMMAND.search(c.parts.code) for c in output.main):
        libraries.add("imagemagick")
    doc = get_doc(inputs)
    if not libraries:
        return result(doc, {
            "image_libraries": [], "orientation_calls": [], "metadata_calls": [],
            "orientation_handling": "no-image-code",
            "metadata_handling": "no-image-code"})
    orientation = {name for name, pattern in _ORIENTATION if pattern.search(code)}
    if "sharp" in libraries and _SHARP_ROTATE.search(code):
        orientation.add("sharp-rotate")
    calls = {(name, kind) for name, kind, pattern in _METADATA if pattern.search(code)}
    kinds = {kind for _, kind in calls}
    return result(doc, {
        "image_libraries": sorted(libraries),
        "orientation_calls": sorted(orientation),
        "orientation_handling": "present" if orientation else "absent",
        "metadata_calls": sorted(name for name, _ in calls),
        "metadata_handling": ("both" if len(kinds) == 2 else
                              kinds.pop() if kinds else "unmentioned"),
    })


EXTRACTOR = Extractor("pipeline.images", "1", "pipeline", images,
                      "image libraries, orientation and metadata handling")
