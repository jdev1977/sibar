"""Colours: reading CSS colour values and naming them in a coarse vocabulary.

A colour is kept as ``#rrggbb`` (lower case, alpha dropped; fully
transparent colours are not colours here) and named by a **class**:

- ``black``, ``white``, or ``gray-<lightness>`` for near-neutral colours:
  CIELAB chroma below 16, or below 6 for light colours (L* 85 or more), so
  Tailwind's grey families (``slate`` and ``gray`` included, chroma up to
  14.5) stay neutral while creams such as ``#fdf6e3`` read as
  ``yellow-light`` and navies such as ``#1e3a8a`` (chroma about 50) as blue;
- otherwise ``<hue>-<lightness>``, with hue one of :data:`HUES` (from the HSL
  hue angle; ``brown`` is a dark orange or yellow).

Lightness is ``dark`` (CIELAB L* below 40), ``mid`` or ``light`` (L* 75 or
more). Hue boundaries, in HSL degrees: red under 12 or from 345, orange 12,
yellow 40, green 70, teal 165, blue 195, indigo 232, violet 250, purple 270,
pink 295. They were set so Tailwind's families land on their own names
(indigo-500 is indigo, purple-500 purple; rose falls in red, sky in blue,
cyan in teal, fuchsia in purple).

Read: hex (3, 4, 6, 8 digits), the 148 CSS named colours, ``rgb()``,
``rgba()``, ``hsl()``, ``hsla()``, ``hwb()``, ``oklab()`` and ``oklch()`` in
legacy and modern syntax. Not read (counted as unparsed): ``lab()``,
``lch()``, ``color()``, relative colours and anything with ``var()``.
"""

import math

from extractors.website.tailwind_palette import PALETTE

NEUTRAL_CHROMA = 16.0
ACCENT_CHROMA = 20.0  # strong enough to count as the page's hue
NEUTRAL_CHROMA_LIGHT = 6.0  # from L* 85
HUES = ("red", "orange", "brown", "yellow", "green", "teal", "blue", "indigo",
        "violet", "purple", "pink")
NEUTRALS = ("black", "white", "gray")
_HUE_BOUNDS = ((12, "red"), (40, "orange"), (70, "yellow"), (165, "green"),
               (195, "teal"), (232, "blue"), (250, "indigo"), (270, "violet"),
               (295, "purple"), (345, "pink"), (360, "red"))
COLOR_FUNCTIONS = frozenset({"rgb", "rgba", "hsl", "hsla", "hwb", "oklab", "oklch"})
UNREAD_COLOR_FUNCTIONS = frozenset({"lab", "lch", "color", "color-mix",
                                    "light-dark"})
NOT_COLORS = frozenset({"transparent", "currentcolor", "inherit", "initial",
                        "unset", "revert", "none"})

NAMED = dict(item.split(":") for item in """
aliceblue:f0f8ff antiquewhite:faebd7 aqua:00ffff aquamarine:7fffd4 azure:f0ffff
beige:f5f5dc bisque:ffe4c4 black:000000 blanchedalmond:ffebcd blue:0000ff
blueviolet:8a2be2 brown:a52a2a burlywood:deb887 cadetblue:5f9ea0
chartreuse:7fff00 chocolate:d2691e coral:ff7f50 cornflowerblue:6495ed
cornsilk:fff8dc crimson:dc143c cyan:00ffff darkblue:00008b darkcyan:008b8b
darkgoldenrod:b8860b darkgray:a9a9a9 darkgreen:006400 darkgrey:a9a9a9
darkkhaki:bdb76b darkmagenta:8b008b darkolivegreen:556b2f darkorange:ff8c00
darkorchid:9932cc darkred:8b0000 darksalmon:e9967a darkseagreen:8fbc8f
darkslateblue:483d8b darkslategray:2f4f4f darkslategrey:2f4f4f
darkturquoise:00ced1 darkviolet:9400d3 deeppink:ff1493 deepskyblue:00bfff
dimgray:696969 dimgrey:696969 dodgerblue:1e90ff firebrick:b22222
floralwhite:fffaf0 forestgreen:228b22 fuchsia:ff00ff gainsboro:dcdcdc
ghostwhite:f8f8ff gold:ffd700 goldenrod:daa520 gray:808080 green:008000
greenyellow:adff2f grey:808080 honeydew:f0fff0 hotpink:ff69b4 indianred:cd5c5c
indigo:4b0082 ivory:fffff0 khaki:f0e68c lavender:e6e6fa lavenderblush:fff0f5
lawngreen:7cfc00 lemonchiffon:fffacd lightblue:add8e6 lightcoral:f08080
lightcyan:e0ffff lightgoldenrodyellow:fafad2 lightgray:d3d3d3 lightgreen:90ee90
lightgrey:d3d3d3 lightpink:ffb6c1 lightsalmon:ffa07a lightseagreen:20b2aa
lightskyblue:87cefa lightslategray:778899 lightslategrey:778899
lightsteelblue:b0c4de lightyellow:ffffe0 lime:00ff00 limegreen:32cd32
linen:faf0e6 magenta:ff00ff maroon:800000 mediumaquamarine:66cdaa
mediumblue:0000cd mediumorchid:ba55d3 mediumpurple:9370db mediumseagreen:3cb371
mediumslateblue:7b68ee mediumspringgreen:00fa9a mediumturquoise:48d1cc
mediumvioletred:c71585 midnightblue:191970 mintcream:f5fffa mistyrose:ffe4e1
moccasin:ffe4b5 navajowhite:ffdead navy:000080 oldlace:fdf5e6 olive:808000
olivedrab:6b8e23 orange:ffa500 orangered:ff4500 orchid:da70d6
palegoldenrod:eee8aa palegreen:98fb98 paleturquoise:afeeee palevioletred:db7093
papayawhip:ffefd5 peachpuff:ffdab9 peru:cd853f pink:ffc0cb plum:dda0dd
powderblue:b0e0e6 purple:800080 rebeccapurple:663399 red:ff0000
rosybrown:bc8f8f royalblue:4169e1 saddlebrown:8b4513 salmon:fa8072
sandybrown:f4a460 seagreen:2e8b57 seashell:fff5ee sienna:a0522d silver:c0c0c0
skyblue:87ceeb slateblue:6a5acd slategray:708090 slategrey:708090 snow:fffafa
springgreen:00ff7f steelblue:4682b4 tan:d2b48c teal:008080 thistle:d8bfd8
tomato:ff6347 turquoise:40e0d0 violet:ee82ee wheat:f5deb3 white:ffffff
whitesmoke:f5f5f5 yellow:ffff00 yellowgreen:9acd32
""".split())


def hex_of(rgb):
    return "#" + "".join(f"{round(max(0.0, min(255.0, c))):02x}" for c in rgb)


def parse_hex(text):
    """``#rgb``, ``#rgba``, ``#rrggbb`` or ``#rrggbbaa`` (with or without
    ``#``) as ``(hex, alpha)``, or None."""
    digits = text.lstrip("#").lower()
    if len(digits) not in (3, 4, 6, 8) or any(c not in "0123456789abcdef"
                                                for c in digits):
        return None
    if len(digits) in (3, 4):
        digits = "".join(c * 2 for c in digits)
    alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
    return "#" + digits[:6], alpha


def named(name):
    value = NAMED.get(name.lower())
    return f"#{value}" if value else None


def _number(token, scale=1.0, percent_scale=None):
    """A number from a number or percentage token; ``percent_scale`` is
    what 100% means."""
    if token.type == "number":
        return token.value * scale
    if token.type == "percentage":
        return token.value / 100 * (percent_scale if percent_scale is not None
                                    else 1.0)
    if token.type == "ident" and token.lower_value == "none":
        return 0.0
    return None


def _hue(token):
    if token.type == "number":
        return token.value % 360
    if token.type == "dimension":
        unit = token.lower_unit
        factor = {"deg": 1, "grad": 0.9, "rad": 180 / math.pi, "turn": 360}.get(unit)
        return None if factor is None else (token.value * factor) % 360
    if token.type == "ident" and token.lower_value == "none":
        return 0.0
    return None


def _hsl_to_rgb(h, s, light):
    s, light = max(0.0, min(1.0, s)), max(0.0, min(1.0, light))
    chroma = (1 - abs(2 * light - 1)) * s
    x = chroma * (1 - abs((h / 60) % 2 - 1))
    m = light - chroma / 2
    sector = int(h // 60) % 6
    r, g, b = [(chroma, x, 0), (x, chroma, 0), (0, chroma, x), (0, x, chroma),
               (x, 0, chroma), (chroma, 0, x)][sector]
    return [(c + m) * 255 for c in (r, g, b)]


def _encode(linear):
    linear = max(0.0, min(1.0, linear))
    value = 12.92 * linear if linear <= 0.0031308 else 1.055 * linear ** (1 / 2.4) - 0.055
    return value * 255


def _oklab_to_rgb(lightness, a, b):
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return [_encode(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
            _encode(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
            _encode(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)]


def parse_function(token):
    """A colour function token as ``(hex, alpha)``, or None if it is not one
    this module reads (or its arguments are not plain numbers)."""
    name = token.lower_name
    if name not in COLOR_FUNCTIONS:
        return None
    args = [a for a in token.arguments if a.type not in ("whitespace", "comment")
            and not (a.type == "literal" and a.value == ",")]
    alpha = 1.0
    for index, arg in enumerate(args):
        if arg.type == "literal" and arg.value == "/":
            if index + 1 < len(args):
                alpha = _number(args[index + 1])
            args = args[:index]
            break
    else:
        if len(args) == 4:
            alpha, args = _number(args[3]), args[:3]
    if len(args) != 3 or alpha is None:
        return None
    try:
        if name in ("rgb", "rgba"):
            rgb = [_number(a, 1.0, 255.0) for a in args]
            if None in rgb:
                return None
        elif name in ("hsl", "hsla", "hwb"):
            h = _hue(args[0])
            p, q = (_number(a, 0.01, 1.0) for a in args[1:])
            if None in (h, p, q):
                return None
            if name == "hwb":
                if p + q >= 1:
                    gray = p / (p + q) * 255
                    rgb = [gray, gray, gray]
                else:
                    rgb = [c * (1 - p - q) + p * 255 for c in _hsl_to_rgb(h, 1, 0.5)]
            else:
                rgb = _hsl_to_rgb(h, p, q)
        elif name == "oklab":
            lightness = _number(args[0], 1.0, 1.0)
            a, b = (_number(arg, 1.0, 0.4) for arg in args[1:])
            if None in (lightness, a, b):
                return None
            rgb = _oklab_to_rgb(lightness, a, b)
        else:  # oklch
            lightness = _number(args[0], 1.0, 1.0)
            chroma = _number(args[1], 1.0, 0.4)
            h = _hue(args[2])
            if None in (lightness, chroma, h):
                return None
            rgb = _oklab_to_rgb(lightness, chroma * math.cos(math.radians(h)),
                                chroma * math.sin(math.radians(h)))
    except (ArithmeticError, ValueError):
        return None
    if alpha > 1:  # a percentage-less alpha such as 50 means nothing sane
        alpha = 1.0
    return hex_of(rgb), alpha


def rgb_of(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _lab(rgb):
    def linear(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def chroma_of(hex_color):
    """CIELAB chroma C* (0 for greys; about 130 at most in sRGB)."""
    _, a, b = _lab(rgb_of(hex_color))
    return math.hypot(a, b)


def lightness_of(hex_color):
    """CIELAB L* (0 to 100)."""
    return _lab(rgb_of(hex_color))[0]


def hue_angle(rgb):
    r, g, b = rgb
    high, low = max(rgb), min(rgb)
    if high == low:
        return 0.0
    span = high - low
    if high == r:
        angle = 60 * (((g - b) / span) % 6)
    elif high == g:
        angle = 60 * ((b - r) / span) + 120
    else:
        angle = 60 * ((r - g) / span) + 240
    return angle % 360


def classify(hex_color):
    """The coarse class of a ``#rrggbb`` colour, such as ``indigo-mid``."""
    rgb = rgb_of(hex_color)
    light, a, b = _lab(rgb)
    level = "dark" if light < 40 else "light" if light >= 75 else "mid"
    limit = NEUTRAL_CHROMA_LIGHT if light >= 85 else NEUTRAL_CHROMA
    if math.hypot(a, b) < limit:
        if light < 12:
            return "black"
        if light > 97:
            return "white"
        return f"gray-{level}"
    angle = hue_angle(rgb)
    hue = next(name for bound, name in _HUE_BOUNDS if angle < bound)
    if hue in ("orange", "yellow") and light < 45:
        hue = "brown"
    return f"{hue}-{level}"


def hue_of(color_class):
    """The hue or neutral name of a class: ``indigo-mid`` gives ``indigo``."""
    return color_class.split("-")[0]


def is_chromatic(color_class):
    return hue_of(color_class) in HUES


def tailwind_color(name):
    """A Tailwind colour name (``indigo-600``, ``white``, ``[#123456]``) as
    ``#rrggbb``, or None."""
    if name in ("white", "black"):
        return "#ffffff" if name == "white" else "#000000"
    if name.startswith("[") and name.endswith("]"):
        parsed = parse_hex(name[1:-1])
        return parsed[0] if parsed else None
    family, _, shade = name.rpartition("-")
    return PALETTE.get(family, {}).get(shade)
