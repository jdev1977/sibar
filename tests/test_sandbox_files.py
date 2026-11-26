"""Reading and removing trees that sandboxed code built (T2.7).

The trees here are built by this test, outside the sandbox, with the shapes
hostile code can give its working folder: very deep, very many entries,
names Windows normally refuses, read-only files and junctions. All are
small (at most a few thousand empty entries).
"""

import os
import subprocess

import pytest

from sandbox.files import _long, listing, read_file, remove_tree, usage

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows paths")
DEPTH = 2000  # far past Python's recursion limit and the 260-character path limit


def deep_tree(root, depth=DEPTH):
    """``root/d/d/.../d/leaf.txt``, ``depth`` folders deep; returns the leaf's
    relative path."""
    current = _long(root)
    for _ in range(depth):
        current = os.path.join(current, "d")
        os.mkdir(current)
    with open(os.path.join(current, "leaf.txt"), "w") as handle:
        handle.write("deep")
    return "/".join(["d"] * depth + ["leaf.txt"])


def test_a_very_deep_tree_is_read_and_removed(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    leaf = deep_tree(root)
    assert len(_long(root)) + len(leaf) > 4000
    assert usage(root, 10_000) == (4, DEPTH + 1, True)
    assert listing(root, 10) == {leaf: 4}
    assert read_file(root, leaf, 100) == b"deep"
    remove_tree(root)
    assert not root.exists()


def test_awkward_names_and_read_only_files_are_removed(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    top = _long(root)
    names = ["con", "aux.txt", "nul", "trailing.", "space ", "été", "\udc80lone"]
    for name in names:
        os.mkdir(os.path.join(top, name))
        with open(os.path.join(top, name, name), "w") as handle:
            handle.write("x")
    locked = os.path.join(top, "read-only.txt")
    with open(locked, "w") as handle:
        handle.write("x")
    os.chmod(locked, 0o444)
    found = listing(root, 100)
    assert len(found) == len(names) + 1
    remove_tree(root)
    assert not root.exists()


def test_a_junction_is_removed_and_not_followed(tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    root = tmp_path / "work"
    root.mkdir()
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "link"), str(target)],
                          capture_output=True)
    if made.returncode != 0:
        pytest.skip("cannot make a junction here")
    assert usage(root, 100)[1] == 1  # counted, not entered
    assert listing(root, 100) == {}
    assert read_file(root, "link/keep.txt", 100) is None
    remove_tree(root)
    assert not root.exists()
    assert (target / "keep.txt").read_text() == "keep"


def test_many_entries_are_counted_up_to_the_limit_and_removed(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    for index in range(3000):
        (root / f"f{index}").write_bytes(b"")
    size, entries, complete = usage(root, 1000)
    assert not complete and entries == 1001
    assert len(listing(root, 50)) == 50
    remove_tree(root)
    assert not root.exists()


def test_what_cannot_be_removed_is_named_not_raised_past_the_caller(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    held = open(root / "held.txt", "w")  # an open file cannot be deleted
    try:
        with pytest.raises(OSError, match="held.txt"):
            remove_tree(root)
    finally:
        held.close()
    remove_tree(root)
    assert not root.exists()
