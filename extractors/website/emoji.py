"""Finding emoji and icon-like text symbols in text.

An emoji is a code point that shows as an emoji by default (Unicode's
Emoji_Presentation, approximated by the ranges below), or any pictographic
symbol followed by the emoji variation selector U+FE0F. A whole sequence
counts once: skin tones, variation selectors, zero-width-joiner sequences and
flag pairs are kept together, so ``👩‍💻`` is one emoji.

Text symbols are characters often used as icons in text but not shown as
emoji: check marks, stars, hearts and arrows (:data:`SYMBOLS`). ``©``, ``®``
and ``™`` are neither.
"""

ZWJ = "‍"
VS16 = "️"
KEYCAP = "⃣"
_EMOJI_RANGES = (
    (0x1F300, 0x1F5FF), (0x1F600, 0x1F64F), (0x1F680, 0x1F6FF),
    (0x1F7E0, 0x1F7EB), (0x1F90C, 0x1F9FF), (0x1FA70, 0x1FAFF),
    (0x1F004, 0x1F004), (0x1F0CF, 0x1F0CF), (0x1F18E, 0x1F18E),
    (0x1F191, 0x1F19A), (0x1F201, 0x1F201), (0x1F21A, 0x1F21A),
    (0x1F22F, 0x1F22F), (0x1F232, 0x1F236), (0x1F238, 0x1F23A),
    (0x1F250, 0x1F251),
)
_EMOJI_BMP = frozenset(
    [0x231A, 0x231B, 0x23E9, 0x23EA, 0x23EB, 0x23EC, 0x23F0, 0x23F3, 0x25FD, 0x25FE,
     0x2614, 0x2615, 0x267F, 0x2693, 0x26A1, 0x26AA, 0x26AB, 0x26BD, 0x26BE,
     0x26C4, 0x26C5, 0x26CE, 0x26D4, 0x26EA, 0x26F2, 0x26F3, 0x26F5, 0x26FA,
     0x26FD, 0x2705, 0x270A, 0x270B, 0x2728, 0x274C, 0x274E, 0x2753, 0x2754,
     0x2755, 0x2757, 0x2795, 0x2796, 0x2797, 0x27B0, 0x27BF, 0x2B1B, 0x2B1C,
     0x2B50, 0x2B55]
    + list(range(0x2648, 0x2654)))
# Pictographs that are emoji only with U+FE0F after them (☀️, ❤️, ✈️...).
_TEXT_PICTOGRAPHS = ((0x2190, 0x21FF), (0x2300, 0x23FF), (0x2600, 0x27BF),
                     (0x2900, 0x297F), (0x2B00, 0x2BFF), (0x3030, 0x3030),
                     (0x303D, 0x303D), (0x3297, 0x3299))
SYMBOLS = frozenset("✓✔✗✘★☆♥❤→←↑↓↗➜➔➝⟶✦✧◆◇●•✱✳⚡")
_SKIN = range(0x1F3FB, 0x1F400)
_FLAG = range(0x1F1E6, 0x1F200)


def _in(code, ranges):
    return any(low <= code <= high for low, high in ranges)


def is_emoji_start(code):
    return code in _EMOJI_BMP or _in(code, _EMOJI_RANGES)


def find_emoji(text):
    """``(emoji list in order, symbol list in order)`` found in ``text``."""
    emoji, symbols = [], []
    i, length = 0, len(text)
    while i < length:
        char = text[i]
        code = ord(char)
        following = text[i + 1] if i + 1 < length else ""
        if code in _FLAG:
            if following and ord(following) in _FLAG:
                emoji.append(text[i:i + 2])
                i += 2
            else:
                i += 1
            continue
        if (char.isdigit() or char in "#*") and char.isascii():
            if following == VS16 and text[i + 2:i + 3] == KEYCAP:
                emoji.append(text[i:i + 3])
                i += 3
                continue
            i += 1
            continue
        start = is_emoji_start(code) or (following == VS16 and
                                         _in(code, _TEXT_PICTOGRAPHS))
        if not start:
            if char in SYMBOLS:
                symbols.append(char)
            i += 1
            continue
        j = i + 1
        while j < length:
            nxt = ord(text[j])
            if text[j] in (VS16, KEYCAP) or nxt in _SKIN:
                j += 1
            elif text[j] == ZWJ and j + 1 < length and (
                    is_emoji_start(ord(text[j + 1]))
                    or _in(ord(text[j + 1]), _TEXT_PICTOGRAPHS)):
                j += 2
            else:
                break
        emoji.append(text[i:j])
        i = j
    return emoji, symbols


def starts_with_emoji(text):
    text = text.lstrip()
    found, _ = find_emoji(text[:16])
    return bool(found) and text.startswith(found[0])
