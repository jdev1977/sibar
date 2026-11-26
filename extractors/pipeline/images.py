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
                        r"\bget\( ?274\b|\[ ?274 ?\]|"
                        r"(?<![A-Za-z])ORIENTATION(?![A-Za-z])", 0),
))
_SHARP_ROTATE = re.compile(r"\.rotate\(\s?\)")
# an ``exif`` keyword argument of a call, not a variable that holds the data
_ARGUMENT = r"[(,]\s{0,40}exif ?= ?"
_METADATA = tuple((name, kind, re.compile(pattern, flags))
                  for name, kind, pattern, flags in (
    ("empty-exif", "strips", _ARGUMENT + r"(?:b[\"'][\"']|None\b)", 0),
    ("strip-option", "strips", r"(?<![\w-])-strip\b|\.strip_metadata\b|\bstrip ?[=:] ?"
                               r"(?:True|true)\b|\bStripMetadata\b", 0),
    ("remove-function", "strips", r"(?:strip|remove|drop|clear)_?(?:all_?)?"
                                  r"(?:exif|metadata)", re.IGNORECASE),
    ("pixel-copy", "strips", r"\.putdata\(", 0),
    ("delete-exif", "strips", r"\.info\.pop\( ?[\"']exif|\bdel [\w.]{0,40}\.info\b|"
                              r"\bpiexif\.remove\(", 0),
    ("keeps-exif", "keeps", _ARGUMENT + r"(?!b[\"']|None\b)[A-Za-z_]|"
                            r"\[ ?[\"']exif[\"'] ?\] ?=(?!=)|"
                            r"\bpiexif\.(?:insert|transplant)\(", 0),
    ("with-metadata", "keeps", r"\.(?:withMetadata|keepMetadata|keepExif)\(", 0),
))
# a parameter's default is no call
_DEFINITION = re.compile(r"^[ \t]{0,40}(?:async )?def [^\n]*$", re.MULTILINE)

# --- saving an image in Python --------------------------------------------------

_MAX_NAMES = 50
_ASSIGNED = re.compile(r"^[ \t]{0,40}(\w{1,60}) ?= ?([^\n]{0,300})", re.MULTILINE)
_OPENED = re.compile(r"\bImage\.open\([^\n]{0,200}?\) as (\w{1,60})")
_ANNOTATED = re.compile(r"\b(\w{1,60}) ?: ?(?:PIL\.)?Image(?:\.Image)?\b")
_CHANGED_IN_PLACE = re.compile(r"\b(\w{1,60})\.(?:thumbnail|putalpha|paste)\(")
_MADE = re.compile(
    r"\bImage\.(?:open|new|fromarray|frombytes|merge|alpha_composite|composite)\(|"
    r"\bImageOps\.\w{1,40}\(")
_DERIVED = re.compile(
    r"\b(\w{1,60})\.(?:resize|convert|copy|crop|rotate|transpose|filter|point|reduce)\(")
_CHAINED = re.compile(
    r"(?:\bImage\.\w{1,40}|\bImageOps\.\w{1,40}|\.(?:resize|convert|copy|crop|rotate|"
    r"transpose))\((?:[^()\n]|\([^()\n]{0,100}\)){0,200}\)\.save\(")
_USUAL_NAME = re.compile(
    r"\b(?:image|img|im|photo|picture|resized|thumb|thumbnail|canvas|background|rgb)"
    r"\w{0,20}\.save\(")
_SAVED = re.compile(r"\b(\w{1,60})\.save\(")


def saves_an_image(bare):
    """Whether Python code with an image library saves an image object."""
    if _CHAINED.search(bare) or _USUAL_NAME.search(bare):
        return True
    names = set()
    for pattern in (_OPENED, _ANNOTATED, _CHANGED_IN_PLACE):
        names |= {m[1] for m in pattern.finditer(bare)}
    assigned = [(m[1], m[2]) for m in _ASSIGNED.finditer(bare)]
    for _ in range(4):          # names made from names made from an image
        for name, value in assigned:
            if _MADE.search(value) or any(
                    m[1] in names for m in _DERIVED.finditer(value)):
                names.add(name)
        if len(names) > _MAX_NAMES:
            break
    return any(m[1] in names for m in _SAVED.finditer(bare))


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
    body = _DEFINITION.sub("", code)
    calls = {(name, kind) for name, kind, pattern in _METADATA if pattern.search(body)}
    kinds = {kind for _, kind in calls}
    return result(doc, {
        "image_libraries": sorted(libraries),
        "orientation_calls": sorted(orientation),
        "orientation_handling": "present" if orientation else "absent",
        "metadata_calls": sorted(name for name, _ in calls),
        "metadata_handling": ("both" if len(kinds) == 2 else
                              kinds.pop() if kinds else "unmentioned"),
    })


EXTRACTOR = Extractor("pipeline.images", "2", "pipeline", images,
                      "image libraries, orientation and metadata handling")
