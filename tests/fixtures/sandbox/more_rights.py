"""A sandbox probe (T2.7): can sandboxed code start a process with more
rights than its own? Used by tests/test_sandbox_boundaries.py."""

import ctypes, json, subprocess, sys
from ctypes import wintypes

# Inside the sandbox: try to start a child in its AppContainer with network
# capabilities, or opted back in to what all application packages may do.
a = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
if a.get("child"):
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", a["tcp"]), 3)
        s.close()
        print(json.dumps({"child": "connected"}))
    except OSError as e:
        print(json.dumps({"child": e.winerror or e.errno}))
    sys.exit(0)

k = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
PSID = ctypes.c_void_p


class SA(ctypes.Structure):
    _fields_ = [("Sid", PSID), ("Attributes", wintypes.DWORD)]


class SC(ctypes.Structure):
    _fields_ = [("AppContainerSid", PSID), ("Capabilities", ctypes.POINTER(SA)),
                ("CapabilityCount", wintypes.DWORD), ("Reserved", wintypes.DWORD)]


class SI(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("r1", wintypes.LPWSTR), ("desk", wintypes.LPWSTR),
                ("title", wintypes.LPWSTR), ("a", wintypes.DWORD * 7), ("flags", wintypes.DWORD),
                ("show", wintypes.WORD), ("r2", wintypes.WORD), ("r3", ctypes.c_void_p),
                ("i", wintypes.HANDLE), ("o", wintypes.HANDLE), ("e", wintypes.HANDLE)]


class SIX(ctypes.Structure):
    _fields_ = [("si", SI), ("attrs", ctypes.c_void_p)]


class PI(ctypes.Structure):
    _fields_ = [("p", wintypes.HANDLE), ("t", wintypes.HANDLE), ("pid", wintypes.DWORD),
                ("tid", wintypes.DWORD)]


def sid(text):
    p = PSID()
    adv.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(PSID)]
    assert adv.ConvertStringSidToSidW(text, ctypes.byref(p))
    return p


def own_package():
    tok = wintypes.HANDLE()
    k.GetCurrentProcess.restype = wintypes.HANDLE
    adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    adv.OpenProcessToken(k.GetCurrentProcess(), 8, ctypes.byref(tok))
    size = wintypes.DWORD()
    adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    adv.GetTokenInformation(tok, 31, None, 0, ctypes.byref(size))  # TokenAppContainerSid
    buf = ctypes.create_string_buffer(size.value)
    adv.GetTokenInformation(tok, 31, buf, size, ctypes.byref(size))
    return ctypes.c_void_p.from_buffer(buf).value, buf


def start(package, caps, lpac):
    count = 2 if package else 0
    size = ctypes.c_size_t()
    k.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    k.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    k.InitializeProcThreadAttributeList(None, max(1, count), 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    k.InitializeProcThreadAttributeList(buf, max(1, count), 0, ctypes.byref(size))
    keep = []
    if package:
        arr = (SA * len(caps))(*[SA(c, 4) for c in caps])
        sc = SC(package, arr, len(caps), 0)
        pol = wintypes.DWORD(1 if lpac else 0)
        keep += [arr, sc, pol]
        assert k.UpdateProcThreadAttribute(buf, 0, 0x00020009, ctypes.byref(sc), ctypes.sizeof(sc), None, None)
        assert k.UpdateProcThreadAttribute(buf, 0, 0x0002000F, ctypes.byref(pol), ctypes.sizeof(pol), None, None)
    si = SIX()
    si.si.cb = ctypes.sizeof(si)
    si.attrs = ctypes.cast(buf, ctypes.c_void_p)
    pi = PI()
    cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline(
        [sys.executable, sys.argv[0], json.dumps({"child": True, "tcp": a["tcp"]})]))
    k.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
    ok = k.CreateProcessW(sys.executable, cmd, None, None, False, 0x00080000 | 0x08000000, None, None, ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        return ("create failed", ctypes.get_last_error())
    k.WaitForSingleObject(pi.p, 15000)
    code = wintypes.DWORD()
    k.GetExitCodeProcess(pi.p, ctypes.byref(code))
    return ("started", code.value)


if a.get("package"):  # the control: started from outside the sandbox
    package, holder = sid(a["package"]), None
else:
    package, holder = own_package()
internet = [sid("S-1-15-3-1"), sid("S-1-15-3-2"), sid("S-1-15-3-3")]
out = {}
out["network capabilities"] = start(package, internet, True)
out["not less privileged"] = start(package, [], False)
print(json.dumps(out))
