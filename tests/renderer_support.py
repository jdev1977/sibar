"""Helpers for the renderer's browser tests: PNG reading, a skip rule and a
memory watch."""

import ctypes
import functools
import os
import struct
import threading
import zlib
from ctypes import wintypes
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


class TreeMemory:
    """Watches, from outside, the memory of this process and of every process
    it starts (Windows): ``own`` is the largest growth of this process and
    ``started`` the largest total of the others, in MB of committed memory."""

    def __init__(self):
        self.own = self.started = 0

    def __enter__(self):
        self._stop = threading.Event()
        self._base = _committed(os.getpid())
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()

    def _watch(self):
        while not self._stop.is_set():
            self.own = max(self.own, (_committed(os.getpid()) - self._base) >> 20)
            others = sum(map(_committed, _descendants(os.getpid())))
            self.started = max(self.started, others >> 20)
            self._stop.wait(0.05)


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.K32GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    for name in ("Process32First", "Process32Next"):
        getattr(kernel, name).argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    return kernel


def _committed(pid):
    """Bytes of private committed memory of process ``pid``; 0 if it is gone."""

    class Counters(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "peak_set", "set", "peak_paged", "paged", "peak_nonpaged",
                "nonpaged", "pagefile", "peak_pagefile")]

    kernel = _kernel()
    handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return 0
    try:
        counters = Counters(size=ctypes.sizeof(Counters))
        done = kernel.K32GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.size)
        return counters.pagefile if done else 0
    finally:
        kernel.CloseHandle(handle)


def _descendants(root):
    """The ids of the processes started by ``root``, and by those, and so on."""

    class Entry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD), ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD), ("priority", ctypes.c_long),
            ("flags", wintypes.DWORD), ("name", ctypes.c_char * 260)]

    kernel = _kernel()
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # processes
    children = {}
    try:
        entry = Entry(size=ctypes.sizeof(Entry))
        more = kernel.Process32First(snapshot, ctypes.byref(entry))
        while more:
            children.setdefault(entry.parent, []).append(entry.pid)
            more = kernel.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    found, waiting = set(), [root]
    while waiting:
        for child in children.get(waiting.pop(), []):
            if child not in found and child != root:
                found.add(child)
                waiting.append(child)
    return found
