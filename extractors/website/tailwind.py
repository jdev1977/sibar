"""Tailwind-style utility classes read as the styling they imply.

A class token such as ``md:hover:bg-indigo-600/90`` is split into its
variants (``md``, ``hover``) and its utility (``bg-indigo-600`` with opacity
``90``). The readers here cover the utilities the website extractors count:

- colours: ``bg- text- border(-side)- from- via- to- ring- ring-offset-
  fill- stroke- outline- decoration- divide- accent- caret- shadow-
  placeholder-`` with a palette colour, ``white``, ``black`` or ``[#hex]``;
- corners: ``rounded`` with any side and size, ``rounded-[12px]``;
- shadows: ``shadow``, ``shadow-xs`` to ``shadow-2xl``, ``shadow-inner``;
- gradients: ``bg-gradient-to-*`` (v3), ``bg-linear-to-*``,
  ``bg-linear-<angle>``, ``bg-radial``, ``bg-conic`` (v4), ``bg-clip-text``;
- fonts: ``font-sans``, ``font-serif``, ``font-mono``, ``font-['Name']``;
- layout: ``flex``, ``grid``, ``grid-cols-N``, ``columns-N``, ``float-*``,
  ``sticky``, ``fixed``, ``container``, ``max-w-*``;
- responsive and state variants: ``sm md lg xl 2xl``, ``dark``,
  ``motion-safe``, ``motion-reduce``, ``focus``, ``focus-visible``,
  ``sr-only``.

Sizes are Tailwind v3's defaults; a project's own ``tailwind.config`` theme
is not read.
"""

import re
from dataclasses import dataclass

from extractors.website.colors import tailwind_color
from extractors.website.tailwind_palette import PALETTE

MAX_TOKEN = 200
BREAKPOINTS = ("sm", "md", "lg", "xl", "2xl")
RADIUS_PX = {"none": 0, "xs": 2, "sm": 2, "": 4, "md": 6, "lg": 8, "xl": 12,
             "2xl": 16, "3xl": 24, "full": "full"}
SHADOW_KIND = {"xs": "subtle", "sm": "subtle", "": "subtle", "md": "subtle",
               "lg": "soft", "xl": "soft", "2xl": "soft", "inner": "inset"}
MAX_WIDTH_PX = {"xs": 320, "sm": 384, "md": 448, "lg": 512, "xl": 576, "2xl": 672,
                "3xl": 768, "4xl": 896, "5xl": 1024, "6xl": 1152, "7xl": 1280,
                "screen-sm": 640, "screen-md": 768, "screen-lg": 1024,
                "screen-xl": 1280, "screen-2xl": 1536}
DIRECTIONS = {"t": "to-top", "tr": "to-top-right", "r": "to-right",
              "br": "to-bottom-right", "b": "to-bottom", "bl": "to-bottom-left",
              "l": "to-left", "tl": "to-top-left"}

_FAMILIES = "|".join(sorted(PALETTE, key=len, reverse=True))
_COLOR = re.compile(
    r"(bg|text|border(?:-[xytrblse])?|from|via|to|ring-offset|ring|fill|stroke|"
    r"outline|decoration|divide|accent|caret|shadow|placeholder)-"
    r"((?:" + _FAMILIES + r")-\d{2,3}|white|black|\[#[0-9a-fA-F]{3,8}\])"
    r"(?:/(\d{1,3}|\[[\d.%]{1,8}\]))?")
_ANY_COLOR = re.compile(
    r"(bg|text|border(?:-[xytrblse])?|from|via|to|ring-offset|ring|fill|stroke|"
    r"outline|decoration|divide|accent|caret|shadow|placeholder)-"
    r"([a-z][a-z0-9-]{0,40}?)(?:/(\d{1,3}|\[[\d.%]{1,8}\]))?")
# Values of those prefixes that are not colours.
_NOT_COLOR = re.compile(
    r"[xytrblse](?:-.{0,40})?|\d.{0,40}|\[.{0,60}|shadow(?:-.{0,40})?|"
    r"(?:xs|sm|base|lg|md|\d?xl|left|"
    r"center|right|justify|start|end|wrap|nowrap|balance|pretty|ellipsis|clip|"
    r"solid|dashed|dotted|double|wavy|none|hidden|collapse|separate|cover|contain|"
    r"auto|top|bottom|fixed|local|scroll|inset|inner|reverse|from-font|slice|"
    r"clone|no-repeat|shown|underline|overline|line-through|opacity|spacing|"
    r"size|position|blend|origin|repeat|gradient|linear|radial|conic|offset|"
    r"opacity-\d{1,3}|(?:clip|origin|repeat|gradient|linear|radial|conic|"
    r"blend|offset|spacing|size|position|left|right|center|top|bottom)-.{1,40})")
COLOR_KEYWORDS = frozenset({"current", "inherit", "transparent", "currentcolor"})
_RADIUS = re.compile(
    r"rounded(?:-(?:t|r|b|l|tl|tr|br|bl|s|e|ss|se|es|ee))?"
    r"(?:-(none|xs|sm|md|lg|xl|2xl|3xl|full|\[[^\]]{1,30}\]))?")
_SHADOW = re.compile(r"shadow(?:-(xs|sm|md|lg|xl|2xl|inner|none))?")
_GRADIENT = re.compile(r"bg-(?:gradient|linear)-to-(t|tr|r|br|b|bl|l|tl)")
_LINEAR_ANGLE = re.compile(r"bg-linear-(\d{1,3})")
_FONT = re.compile(r"font-(sans|serif|mono)|font-\[(.{1,80})\]")
_GRID_COLS = re.compile(r"grid-cols-(\d{1,2}|\[.{1,60}\])")
_MAX_W = re.compile(r"max-w-(\w[\w-]{0,15}|\[[^\]]{1,20}\])")
_SIGNS = re.compile(
    r"(?:bg|text|border|from|via|to|ring)-(?:" + _FAMILIES + r")-\d{2,3}"
    r"|rounded-(?:md|xl|2xl|3xl)|shadow-(?:md|xl|2xl)|space-[xy]-\d{1,2}"
    r"|gap-\d{1,2}|[wh]-\d{1,2}|min-h-screen|max-w-\w{1,10}"
    r"|text-(?:xs|sm|base|lg|xl|[2-9]xl)|font-(?:medium|semibold|extrabold)"
    r"|items-center|justify-between|grid-cols-\d{1,2}|tracking-\w{1,10}"
    r"|leading-\w{1,10}|bg-gradient-to-\w{1,2}|inset-0|z-\d{1,2}")
SIGNS_NEEDED = 5


@dataclass(frozen=True)
class Utility:
    token: str
    variants: tuple
    base: str  # without variants, "!" or "-"
    negative: bool = False


def split(token):
    """A class token as a :class:`Utility` (None if too long)."""
    if not token or len(token) > MAX_TOKEN:
        return None
    parts, depth, current = [], 0, []
    for char in token:
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(0, depth - 1)
        if char == ":" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    base = "".join(current).strip("!")
    negative = base.startswith("-")
    return Utility(token, tuple(parts), base.lstrip("-"), negative)


def color(utility, theme=None):
    """``(property, colour name, hex)`` for a colour utility, else None.

    ``theme`` maps the project's own colour names (``primary-500``) to hex or
    None; a theme name whose value is not a plain colour gives hex None.
    """
    match = _COLOR.fullmatch(utility.base)
    if match:
        hex_color = tailwind_color(match.group(2))
        if hex_color is None or match.group(3) in ("0", "[0]", "[0%]"):
            return None
        return match.group(1), match.group(2), hex_color
    if not theme:
        return None
    match = _ANY_COLOR.fullmatch(utility.base)
    if not match or match.group(2) not in theme or match.group(3) in ("0", "[0]"):
        return None
    return match.group(1), match.group(2), theme[match.group(2)]


def unknown_color(utility, theme=None, other_names=()):
    """The name in a colour utility whose name is neither a palette colour,
    a theme colour nor a non-colour value (``text-xl``, ``border-2``,
    ``bg-cover``), else None: a colour the page uses but this reader cannot
    see, such as one from a theme file that was not read."""
    match = _ANY_COLOR.fullmatch(utility.base)
    if not match or _COLOR.fullmatch(utility.base):
        return None
    name = match.group(2)
    if theme and name in theme or name in other_names:
        return None
    if _NOT_COLOR.fullmatch(name) or name in COLOR_KEYWORDS:
        return None
    if match.group(1) == "shadow" and name in SHADOW_KIND:
        return None
    return name


def radius(utility):
    """The radius in px (or ``"full"``) of a ``rounded`` utility, else None.
    An arbitrary ``rounded-[...]`` gives its text, read by the caller."""
    match = _RADIUS.fullmatch(utility.base)
    if not match:
        return None
    size = match.group(1) or ""
    return size[1:-1] if size.startswith("[") else RADIUS_PX[size]


def shadow(utility):
    """The shadow kind of a ``shadow`` utility (``none`` for shadow-none)."""
    match = _SHADOW.fullmatch(utility.base)
    if not match:
        return None
    size = match.group(1) or ""
    return "none" if size == "none" else SHADOW_KIND[size]


def gradient(utility):
    """``(type, direction)`` for a gradient background utility, else None."""
    base = utility.base
    match = _GRADIENT.fullmatch(base)
    if match:
        return "linear", DIRECTIONS[match.group(1)]
    match = _LINEAR_ANGLE.fullmatch(base)
    if match:
        return "linear", f"{int(match.group(1))}deg"
    if base == "bg-radial" or base.startswith("bg-radial-["):
        return "radial", None
    if base == "bg-conic" or base.startswith("bg-conic-"):
        return "conic", None
    return None


def font(utility):
    """A generic family (``sans-serif``, ``serif``, ``monospace``) or a named
    family from ``font-['Name']``, else None."""
    match = _FONT.fullmatch(utility.base)
    if not match:
        return None
    if match.group(1):
        return {"sans": "sans-serif", "serif": "serif", "mono": "monospace"}[
            match.group(1)]
    return match.group(2).replace("_", " ").split(",")[0].strip("'\" ")


def layout(utility):
    """The layout system a utility uses: ``flex``, ``grid``, ``columns`` or
    ``float``, else None."""
    base = utility.base
    if base in ("flex", "inline-flex"):
        return "flex"
    if base in ("grid", "inline-grid") or _GRID_COLS.fullmatch(base):
        return "grid"
    if base.startswith("columns-"):
        return "columns"
    if base in ("float-left", "float-right", "float-start", "float-end"):
        return "float"
    return None


def grid_columns(utility):
    match = _GRID_COLS.fullmatch(utility.base)
    return match.group(1) if match else None


def max_width(utility):
    """The px of a ``max-w-*`` utility (None for other sizes or utilities)."""
    match = _MAX_W.fullmatch(utility.base)
    return MAX_WIDTH_PX.get(match.group(1)) if match else None


def is_sign(utility):
    """True for a utility found in Tailwind but rarely elsewhere (Bootstrap
    shares ``px-4``, ``rounded`` and ``shadow-sm``, so those do not count)."""
    return bool(_SIGNS.fullmatch(utility.base)) or any(
        v in BREAKPOINTS or v in ("hover", "dark", "focus") for v in utility.variants)
