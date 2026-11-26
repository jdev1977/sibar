"""Helpers for the renderer's browser tests: PNG reading and a skip rule."""

import functools
import struct
import zlib
from pathlib import Path

import pytest

PAGES = Path(__file__).resolve().parent / "fixtures" / "pages"


@functools.lru_cache(maxsize=None)
def _missing_browser():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch(chromium_sandbox=True).close()
    except Exception as error:
        return f"{type(error).__name__}: {str(error).splitlines()[0]}"
    return None


def require_chromium():
    reason = _missing_browser()
    if reason:
        pytest.skip("Chromium for Playwright cannot be started; install it with "
                    f"`python -m playwright install chromium` ({reason})")


class Png:
    """An 8-bit RGB or RGBA PNG, as Chromium writes screenshots."""

    def __init__(self, path):
        data = Path(path).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        self.width, self.height, depth, colour = struct.unpack(">IIBB", data[16:26])
        assert depth == 8 and colour in (2, 6)
        self.channels = 3 if colour == 2 else 4
        packed, offset = b"", 8
        while offset < len(data):
            length, kind = struct.unpack(">I4s", data[offset:offset + 8])
            if kind == b"IDAT":
                packed += data[offset + 8:offset + 8 + length]
            offset += 12 + length
        self.raw = zlib.decompress(packed)

    @property
    def size(self):
        return self.width, self.height

    def pixel(self, x, y):
        """The (r, g, b) at ``x, y``. Decodes the rows up to ``y``."""
        step, stride = self.channels, self.width * self.channels
        above = bytearray(stride)
        for row in range(y + 1):
            start = row * (stride + 1)
            kind = self.raw[start]
            line = bytearray(self.raw[start + 1:start + 1 + stride])
            if kind:
                for i in range(stride):
                    a = line[i - step] if i >= step else 0
                    b = above[i]
                    c = above[i - step] if i >= step else 0
                    if kind == 1:
                        add = a
                    elif kind == 2:
                        add = b
                    elif kind == 3:
                        add = (a + b) // 2
                    else:
                        p = a + b - c
                        add = min((abs(p - a), 0, a), (abs(p - b), 1, b),
                                  (abs(p - c), 2, c))[2]
                    line[i] = (line[i] + add) & 255
            above = line
        return tuple(above[x * step:x * step + 3])
