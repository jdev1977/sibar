"""Compatibility fixes for code run in the sibar sandbox (T2.7).

Python's site module imports this at the start of every sandboxed Python. None
of it is a security boundary: sandboxed code can undo any of it, and gains
nothing by doing so, since the limits are enforced by Windows. Each fix makes
ordinary code behave as it would outside the sandbox where the sandbox would
otherwise make it fail for a reason that is not the code's:

- ``os.path.realpath`` of a relative path: Windows will not tell an
  AppContainer the final path of a file, and Python's fallback then joins the
  name of the current folder twice for ``"."``. The path is made absolute
  first, which the fallback handles.
- multiprocessing names its pipes ``\\\\.\\pipe\\pyc-...``; an AppContainer may
  only make pipes under ``\\\\.\\pipe\\LOCAL\\``, which is its own. The names
  are moved there.
- ``os.devnull``: the NUL device lets no AppContainer open it, which breaks
  ``subprocess.DEVNULL``, pytest's output capture and more. Opening it gives
  a copy of the process's standard input, which the sandbox opens on NUL for
  reading and writing.
- Private folders: Python 3.13 gives folders made with mode 0o700 (such as
  ``tempfile.mkdtemp``'s) a DACL the sandboxed process itself does not
  match; they inherit the working folder's permissions instead.
- asyncio: the sandbox cannot make sockets, and Python's ``_overlapped``
  module makes one when it is imported, so ``import asyncio`` (which many
  libraries do just for a type check) would fail. ``_overlapped`` is replaced
  by a stand-in whose functions raise, and event loops are selector loops
  that sleep instead of waiting on a socket. Timers, tasks and threads work;
  anything that needs a socket, a pipe or a subprocess still fails.

Optional fixes, turned on by the sandbox for some tasks only, are in
``sibar_sandbox_shims`` and documented there.
"""

import os
import sys


def _fix_realpath():
    import ntpath

    original = ntpath.realpath

    def realpath(path, *, strict=False):
        path = os.fspath(path)
        if not ntpath.isabs(path):
            path = ntpath.abspath(path)
        return original(path, strict=strict)

    realpath.__wrapped__ = original
    realpath.__doc__ = original.__doc__
    ntpath.realpath = realpath


def _fix_devnull():
    """Make ``os.devnull`` usable: the NUL device's DACL has no entry an
    AppContainer matches, so opening it fails. The sandbox gives every
    process a standard input that reads from NUL (and may write to it); opens
    of ``os.devnull`` get a copy of that handle instead."""
    try:
        open(os.devnull, "rb").close()
        return
    except OSError:
        pass
    import builtins
    import ctypes
    import io
    import msvcrt
    import _winapi

    kernel = ctypes.WinDLL("kernel32")
    kernel.GetFileType.argtypes = [ctypes.c_void_p]
    kernel.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    handle = _winapi.GetStdHandle(_winapi.STD_INPUT_HANDLE)
    mode = ctypes.c_ulong()
    if (not handle or kernel.GetFileType(handle) != 2  # FILE_TYPE_CHAR
            or kernel.GetConsoleMode(handle, ctypes.byref(mode))):
        return  # not the sandbox's NUL input
    process = _winapi.GetCurrentProcess()
    null = _winapi.DuplicateHandle(process, handle, process, 0, False,
                                   _winapi.DUPLICATE_SAME_ACCESS)

    def null_descriptor(flags):
        copy = _winapi.DuplicateHandle(process, null, process, 0, False,
                                       _winapi.DUPLICATE_SAME_ACCESS)
        return msvcrt.open_osfhandle(copy, flags)

    def is_null(path):
        if not isinstance(path, (str, bytes, os.PathLike)):
            return False
        try:
            text = os.fsdecode(path).lower()
        except (TypeError, ValueError):
            return False
        return text in ("nul", "nul:", "\\\\.\\nul", "//./nul")

    os_open = os.open

    def open_descriptor(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is None and is_null(path):
            return null_descriptor(flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR
                                            | os.O_APPEND | os.O_BINARY | os.O_TEXT))
        return os_open(path, flags, mode, dir_fd=dir_fd)

    io_open = io.open

    def open_file(file, mode="r", *args, **kwargs):
        if is_null(file):
            return io_open(null_descriptor(os.O_RDWR | os.O_BINARY), mode, *args, **kwargs)
        return io_open(file, mode, *args, **kwargs)

    os.open = open_descriptor
    builtins.open = io.open = open_file


def _fix_private_folders():
    """On Windows, Python 3.13 gives a folder made with mode 0o700 (as
    ``tempfile.mkdtemp`` does) a DACL for the owner, SYSTEM and
    administrators only, which a sandboxed process does not match: it could
    not use its own temporary folders. Such folders inherit the working
    folder's permissions instead, which grant the sandbox and no one else."""
    mkdir = os.mkdir

    def make_folder(path, mode=0o777, *, dir_fd=None):
        return mkdir(path, 0o777 if mode == 0o700 else mode, dir_fd=dir_fd)

    make_folder.__doc__ = mkdir.__doc__
    os.mkdir = make_folder


def _find_spec_elsewhere(finder_to_skip, name, path, target):
    for finder in sys.meta_path:
        if finder is finder_to_skip or not hasattr(finder, "find_spec"):
            continue
        spec = finder.find_spec(name, path, target)
        if spec is not None:
            return spec
    return None


class _AfterImport:
    """Runs ``hooks[name](module)`` right after module ``name`` is imported;
    ``stand_ins[name]()`` may give a module to use in place of the real one
    (None: import the real one)."""

    def __init__(self, hooks, stand_ins):
        self.hooks, self.stand_ins = hooks, stand_ins

    def find_spec(self, name, path=None, target=None):
        hook, stand_in = self.hooks.get(name), self.stand_ins.get(name)
        if hook is None and stand_in is None:
            return None
        spec = _find_spec_elsewhere(self, name, path, target)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return spec
        spec.loader = _HookedLoader(spec.loader, hook, stand_in)
        return spec


class _HookedLoader:
    def __init__(self, loader, hook, stand_in):
        self._loader, self._hook, self._stand_in = loader, hook, stand_in

    def create_module(self, spec):
        if self._stand_in is not None:
            module = self._stand_in()
            if module is not None:
                return module
        return self._loader.create_module(spec)

    def exec_module(self, module):
        if not getattr(module, "_sibar_stand_in", False):
            self._loader.exec_module(module)
        if self._hook is not None:
            self._hook(module)

    def __getattr__(self, name):
        return getattr(self._loader, name)


def _default_dacl_attributes():
    """SECURITY_ATTRIBUTES whose DACL is this process token's default DACL.

    Named pipes made with no security attributes get a DACL of the pipe
    file system's own, which lets the sandbox's restricted token only read
    them; the token's default DACL grants the SIDs the token has."""
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.SetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                                 ctypes.c_void_p, wintypes.BOOL]
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 6, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 6, buffer, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(token)
    descriptor = ctypes.create_string_buffer(64)
    advapi.InitializeSecurityDescriptor(descriptor, 1)
    dacl = ctypes.c_void_p.from_buffer(buffer).value
    if not advapi.SetSecurityDescriptorDacl(descriptor, True, dacl, False):
        raise ctypes.WinError(ctypes.get_last_error())

    class Attributes(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p),
                    ("inherit", wintypes.BOOL)]

    attributes = Attributes(ctypes.sizeof(Attributes),
                            ctypes.cast(descriptor, ctypes.c_void_p), False)
    attributes._keep = (buffer, descriptor)
    return attributes


class _WinapiWithPipeSecurity:
    """``_winapi``, except that named pipes get the token's default DACL."""

    def __init__(self, winapi):
        self._winapi = winapi
        self._attributes = None

    def CreateNamedPipe(self, name, open_mode, pipe_mode, instances, out_size, in_size,
                        timeout, security):
        import ctypes
        from ctypes import wintypes

        if self._attributes is None:
            self._attributes = _default_dacl_attributes()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateNamedPipeW.restype = wintypes.HANDLE
        kernel.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        handle = kernel.CreateNamedPipeW(name, open_mode, pipe_mode, instances, out_size,
                                         in_size, timeout, ctypes.byref(self._attributes))
        if handle in (None, wintypes.HANDLE(-1).value):
            error = ctypes.get_last_error()
            raise OSError(None, ctypes.FormatError(error), None, error)
        return handle

    def __getattr__(self, name):
        return getattr(self._winapi, name)


def _local_pipes(module):
    original = module.arbitrary_address
    prefix = "\\\\.\\pipe\\"

    def arbitrary_address(family):
        address = original(family)
        if (family == "AF_PIPE" and address.startswith(prefix)
                and not address[len(prefix):].upper().startswith("LOCAL\\")):
            address = prefix + "LOCAL\\" + address[len(prefix):]
        return address

    module.arbitrary_address = arbitrary_address
    if hasattr(module, "_winapi"):
        module._winapi = _WinapiWithPipeSecurity(module._winapi)


def _sockets_refused():
    import _socket

    try:
        _socket.socket().close()
    except OSError:
        return True
    return False


def _overlapped_stand_in():
    if not _sockets_refused():
        return None
    import types

    module = types.ModuleType("_overlapped", "Stand-in: the sandbox has no sockets.")
    module._sibar_stand_in = True

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)

        def refuse(*args, **kwargs):
            raise PermissionError(10013, "the sandbox has no sockets, so asyncio "
                                         f"cannot use _overlapped.{name}")
        return refuse

    module.__getattr__ = __getattr__
    return module


def _asyncio_without_sockets(asyncio):
    if not getattr(sys.modules.get("_overlapped"), "_sibar_stand_in", False):
        return
    import selectors
    import time
    from asyncio import selector_events, windows_events

    select = selectors.SelectSelector._select

    def _select(self, r, w, x, timeout=None):
        if not r and not w:  # nothing to wait on: no sockets exist here
            time.sleep(0.01 if timeout is None else max(0.0, min(timeout, 0.01)))
            return [], [], []
        return select(self, r, w, x, timeout)

    selectors.SelectSelector._select = _select
    loop = selector_events.BaseSelectorEventLoop
    make, close = loop._make_self_pipe, loop._close_self_pipe

    def _make_self_pipe(self):
        try:
            make(self)
        except OSError:
            self._ssock = self._csock = None  # the loop then wakes by polling

    def _close_self_pipe(self):
        if self._ssock is not None:
            close(self)

    loop._make_self_pipe, loop._close_self_pipe = _make_self_pipe, _close_self_pipe
    policy = windows_events.WindowsSelectorEventLoopPolicy
    windows_events.DefaultEventLoopPolicy = policy
    asyncio.DefaultEventLoopPolicy = policy


HOOKS = {"multiprocessing.connection": _local_pipes, "asyncio": _asyncio_without_sockets}
STAND_INS = {"_overlapped": _overlapped_stand_in}

if os.name == "nt":
    _fix_realpath()
    _fix_devnull()
    _fix_private_folders()
    if os.environ.get("SIBAR_SANDBOX_SHIMS"):
        import sibar_sandbox_shims

        HOOKS.update(sibar_sandbox_shims.install())
    sys.meta_path.insert(0, _AfterImport(HOOKS, STAND_INS))
