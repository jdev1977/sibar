"""The sandbox's private runtime (T2.7): its permissions and its checks."""

import pytest

from sandbox_support import require_runtime

pytestmark = pytest.mark.sandbox


@pytest.fixture(autouse=True)
def runtime_present():
    require_runtime()


def test_the_runtime_folder_has_exactly_the_dacl_setup_gives():
    from sandbox import runtime, win32

    root = runtime.default_root()
    capability = win32.capability_sid(runtime.RUNTIME_CAPABILITY).string
    found = win32.file_dacl(runtime.runtime_dir(root))
    assert found.startswith("P")  # nothing inherited from the folders above
    entries = {ace.split(";")[-1].rstrip(")"): ace.split(";")[2]
               for ace in found[1:].replace(")(", ")\n(").splitlines()}
    assert entries[capability] == entries[runtime.RESTRICTED_SID] == "0x1200a9"  # read, run
    assert set(entries) == {win32.user_sid().string, "SY", "BA", capability,
                            runtime.RESTRICTED_SID}


def test_a_stale_runtime_is_refused(monkeypatch):
    from sandbox import runtime
    from sandbox.box import Box

    monkeypatch.setattr(runtime, "shim_digest", lambda: "changed")
    with pytest.raises(runtime.RuntimeMissing, match="shim changed"):
        Box().open()


def test_the_runtime_is_not_changed_while_a_box_is_open():
    from sandbox import runtime
    from sandbox.box import Box
    from sandbox_support import SMALL

    with Box(limits=SMALL):
        with pytest.raises(runtime.RuntimeMissing, match="sandbox run is using"):
            runtime.update_shims(say=lambda _: None)
