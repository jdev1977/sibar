"""Files in folders that sandboxed code has written to.

Everything in a working folder is the sandboxed code's doing, so it is read as
hostile: links and junctions are never followed, file names may be anything
Windows allows (reserved names, trailing dots, very long paths), files may be
read-only, and sizes are bounded before anything is read. These functions run
only after every sandboxed process has ended.
"""

import os
import shutil
import stat
from pathlib import Path

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _long(path):
    """``path`` in the form Windows takes without the 260-character limit or
    name rewriting (trailing dots and spaces, reserved names)."""
    text = os.path.abspath(str(path))
    if os.name != "nt" or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def _is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE)


def remove_tree(path):
    """Delete the folder ``path`` and everything in it, without following
    links or junctions (a link is removed, not what it points to). Raises
    OSError naming what could not be removed."""
    failures = []

    def unlink(target, is_dir):
        try:
            (os.rmdir if is_dir else os.unlink)(target)
        except FileNotFoundError:
            pass
        except PermissionError:
            try:
                os.chmod(target, stat.S_IWRITE, follow_symlinks=False)
                (os.rmdir if is_dir else os.unlink)(target)
            except OSError as error:
                failures.append(f"{target}: {error.strerror or error}")
        except OSError as error:
            failures.append(f"{target}: {error.strerror or error}")

    def clear(folder):
        try:
            entries = list(os.scandir(folder))
        except FileNotFoundError:
            return
        except OSError as error:
            failures.append(f"{folder}: {error.strerror or error}")
            return
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as error:
                failures.append(f"{entry.path}: {error.strerror or error}")
                continue
            directory = stat.S_ISDIR(info.st_mode)
            if _is_link(info):
                unlink(entry.path, directory)
            elif directory:
                clear(entry.path)
                unlink(entry.path, True)
            else:
                unlink(entry.path, False)

    top = _long(path)
    try:
        info = os.lstat(top)
    except FileNotFoundError:
        return
    if _is_link(info) or not stat.S_ISDIR(info.st_mode):
        raise OSError(f"{path}: not a plain folder; not removing it")
    clear(top)
    unlink(top, True)
    if failures:
        raise OSError("could not remove: " + "; ".join(failures[:5])
                      + (f" (and {len(failures) - 5} more)" if len(failures) > 5 else ""))


def usage(path, max_entries):
    """``(bytes, entries, complete)`` for the files under ``path``: their
    total size, how many files and folders there are, and False if counting
    stopped at ``max_entries``. Links are counted, not followed."""
    total = entries = 0
    stack = [_long(path)]
    while stack:
        folder = stack.pop()
        try:
            listing = os.scandir(folder)
        except OSError:
            continue
        with listing:
            for entry in listing:
                entries += 1
                if entries > max_entries:
                    return total, entries, False
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(info.st_mode) and not _is_link(info):
                    stack.append(entry.path)
                else:
                    total += info.st_size
    return total, entries, True


def listing(path, max_entries):
    """The files under ``path`` as ``{relative path: size}`` (``/``
    separated), links and junctions left out, at most ``max_entries``."""
    found = {}
    top = _long(path)
    stack = [top]
    while stack and len(found) < max_entries:
        folder = stack.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if _is_link(info):
                continue
            if stat.S_ISDIR(info.st_mode):
                stack.append(entry.path)
            elif len(found) < max_entries:
                found[entry.path[len(top) + 1:].replace("\\", "/")] = info.st_size
    return found


def read_file(root, relative, limit):
    """The bytes of the file ``relative`` (``/`` separated) under ``root``, or
    None if it is missing, is not a plain file, lies behind a link, or is
    larger than ``limit``."""
    parts = relative.split("/")
    if not relative or any(part in ("", ".", "..") for part in parts):
        return None
    current = _long(root)
    for part in parts:
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except OSError:
            return None
        if _is_link(info):
            return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        return None
    try:
        with open(current, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None
    return data if len(data) <= limit else None


def copy_files(source, relative_paths, target):
    """Copy the files ``relative_paths`` (``/`` separated, already checked to
    be safe relative paths) from ``source`` into ``target``."""
    for relative in relative_paths:
        destination = Path(target, *relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(source, *relative.split("/")), destination)
