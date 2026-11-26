"""The Windows calls the sandbox needs, through ctypes.

Everything here fails loudly: a call Windows refuses raises :class:`WinError`,
so no caller can go on with a boundary half built. Nothing here decides
policy; ``sandbox.box`` does.
"""

import ctypes
import os
import re
import subprocess
import winreg
from ctypes import wintypes

PSID = ctypes.c_void_p
HANDLE = wintypes.HANDLE
INVALID_HANDLE = HANDLE(-1).value

# Process creation flags.
CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
STARTF_USESHOWWINDOW = 0x1
STARTF_USESTDHANDLES = 0x100
SW_HIDE = 0
# Process and thread attributes.
ATTRIBUTE_HANDLE_LIST = 0x00020002
ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
ATTRIBUTE_JOB_LIST = 0x0002000D
ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY = 0x0002000F
ALL_APPLICATION_PACKAGES_OPT_OUT = 0x1  # a less privileged AppContainer
# Tokens.
TOKEN_DUPLICATE, TOKEN_QUERY, TOKEN_ASSIGN_PRIMARY = 0x2, 0x8, 0x1
TOKEN_ADJUST_DEFAULT = 0x80
DISABLE_MAX_PRIVILEGE = 0x1
SE_GROUP_ENABLED = 0x4
SE_GROUP_LOGON_ID = 0xC0000000
TOKEN_USER_CLASS, TOKEN_GROUPS_CLASS, TOKEN_DEFAULT_DACL_CLASS = 1, 2, 6
# Security information.
DACL_SECURITY_INFORMATION = 0x4
LABEL_SECURITY_INFORMATION = 0x10
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
SE_FILE_OBJECT = 1
# Window stations and desktops.
WINSTA_CREATEDESKTOP, WINSTA_READATTRIBUTES = 0x8, 0x2
GENERIC_READ, GENERIC_WRITE, GENERIC_ALL = 0x80000000, 0x40000000, 0x10000000
DESKTOP_ALL = 0x01FF | 0x000F0000
UOI_NAME = 2
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102
STILL_ACTIVE = 259

APPCONTAINER_KEY = (r"Software\Classes\Local Settings\Software\Microsoft\Windows"
                    r"\CurrentVersion\AppContainer")


class WinError(OSError):
    """A Windows call failed."""

    def __init__(self, what, code=None):
        code = ctypes.get_last_error() if code is None else code
        super().__init__(f"{what} failed (Windows error {code})")
        self.code = code


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", PSID), ("Attributes", wintypes.DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [("AppContainerSid", PSID),
                ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
                ("CapabilityCount", wintypes.DWORD), ("Reserved", wintypes.DWORD)]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", HANDLE),
                ("hStdOutput", HANDLE), ("hStdError", HANDLE)]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


def _bind(dll, name, result, arguments):
    function = getattr(dll, name)
    function.restype, function.argtypes = result, arguments
    return function


class _Api:
    def __init__(self):
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        a = ctypes.WinDLL("advapi32", use_last_error=True)
        u = ctypes.WinDLL("user32", use_last_error=True)
        e = ctypes.WinDLL("userenv", use_last_error=True)
        b = ctypes.WinDLL("kernelbase", use_last_error=True)
        B, D, P, V = wintypes.BOOL, wintypes.DWORD, ctypes.POINTER, ctypes.c_void_p
        LP = wintypes.LPCWSTR
        self.LocalFree = _bind(k, "LocalFree", V, [V])
        self.CloseHandle = _bind(k, "CloseHandle", B, [HANDLE])
        self.GetCurrentProcess = _bind(k, "GetCurrentProcess", HANDLE, [])
        self.CreatePipe = _bind(k, "CreatePipe", B, [P(HANDLE), P(HANDLE), V, D])
        self.CreateFileW = _bind(k, "CreateFileW", HANDLE,
                                 [LP, D, D, V, D, D, HANDLE])
        self.ReadFile = _bind(k, "ReadFile", B, [HANDLE, V, D, P(D), V])
        self.WaitForSingleObject = _bind(k, "WaitForSingleObject", D, [HANDLE, D])
        self.GetExitCodeProcess = _bind(k, "GetExitCodeProcess", B, [HANDLE, P(D)])
        self.TerminateProcess = _bind(k, "TerminateProcess", B, [HANDLE, wintypes.UINT])
        self.ResumeThread = _bind(k, "ResumeThread", D, [HANDLE])
        self.IsProcessInJob = _bind(k, "IsProcessInJob", B, [HANDLE, HANDLE, P(B)])
        self.InitializeProcThreadAttributeList = _bind(
            k, "InitializeProcThreadAttributeList", B, [V, D, D, P(ctypes.c_size_t)])
        self.UpdateProcThreadAttribute = _bind(
            k, "UpdateProcThreadAttribute", B,
            [V, D, ctypes.c_size_t, V, ctypes.c_size_t, V, V])
        self.DeleteProcThreadAttributeList = _bind(
            k, "DeleteProcThreadAttributeList", None, [V])
        self.OpenProcessToken = _bind(a, "OpenProcessToken", B, [HANDLE, D, P(HANDLE)])
        self.GetTokenInformation = _bind(
            a, "GetTokenInformation", B, [HANDLE, ctypes.c_int, V, D, P(D)])
        self.SetTokenInformation = _bind(
            a, "SetTokenInformation", B, [HANDLE, ctypes.c_int, V, D])
        self.CreateRestrictedToken = _bind(
            a, "CreateRestrictedToken", B,
            [HANDLE, D, D, V, D, V, D, V, P(HANDLE)])
        self.ConvertSidToStringSidW = _bind(
            a, "ConvertSidToStringSidW", B, [PSID, P(wintypes.LPWSTR)])
        self.ConvertStringSidToSidW = _bind(a, "ConvertStringSidToSidW", B, [LP, P(PSID)])
        self.GetLengthSid = _bind(a, "GetLengthSid", D, [PSID])
        self.ConvertStringSecurityDescriptorToSecurityDescriptorW = _bind(
            a, "ConvertStringSecurityDescriptorToSecurityDescriptorW", B,
            [LP, D, P(V), P(D)])
        self.GetSecurityDescriptorDacl = _bind(
            a, "GetSecurityDescriptorDacl", B, [V, P(B), P(V), P(B)])
        self.GetSecurityDescriptorSacl = _bind(
            a, "GetSecurityDescriptorSacl", B, [V, P(B), P(V), P(B)])
        self.SetNamedSecurityInfoW = _bind(
            a, "SetNamedSecurityInfoW", D,
            [wintypes.LPWSTR, ctypes.c_int, D, PSID, PSID, V, V])
        self.GetNamedSecurityInfoW = _bind(
            a, "GetNamedSecurityInfoW", D,
            [LP, ctypes.c_int, D, V, V, P(V), V, P(V)])
        self.GetSecurityInfo = _bind(
            a, "GetSecurityInfo", D, [HANDLE, ctypes.c_int, D, V, V, P(V), V, P(V)])
        self.ConvertSecurityDescriptorToStringSecurityDescriptorW = _bind(
            a, "ConvertSecurityDescriptorToStringSecurityDescriptorW", B,
            [V, D, D, P(wintypes.LPWSTR), V])
        self.CreateProcessAsUserW = _bind(
            a, "CreateProcessAsUserW", B,
            [HANDLE, LP, wintypes.LPWSTR, V, V, B, D, V, LP,
             P(STARTUPINFOEXW), P(PROCESS_INFORMATION)])
        self.CreateProcessW = _bind(
            k, "CreateProcessW", B,
            [LP, wintypes.LPWSTR, V, V, B, D, V, LP,
             P(STARTUPINFOEXW), P(PROCESS_INFORMATION)])
        self.CreateAppContainerProfile = _bind(
            e, "CreateAppContainerProfile", ctypes.c_long, [LP, LP, LP, V, D, P(PSID)])
        self.DeleteAppContainerProfile = _bind(
            e, "DeleteAppContainerProfile", ctypes.c_long, [LP])
        self.DeriveAppContainerSidFromAppContainerName = _bind(
            e, "DeriveAppContainerSidFromAppContainerName", ctypes.c_long, [LP, P(PSID)])
        self.GetAppContainerFolderPath = _bind(
            e, "GetAppContainerFolderPath", ctypes.c_long, [LP, P(wintypes.LPWSTR)])
        self.FreeSid = _bind(a, "FreeSid", V, [PSID])
        self.DeriveCapabilitySidsFromName = _bind(
            b, "DeriveCapabilitySidsFromName", B,
            [LP, P(P(PSID)), P(D), P(P(PSID)), P(D)])
        self.CoTaskMemFree = _bind(ctypes.WinDLL("ole32"), "CoTaskMemFree", None, [V])
        self.CreateWindowStationW = _bind(u, "CreateWindowStationW", HANDLE, [LP, D, D, V])
        self.CloseWindowStation = _bind(u, "CloseWindowStation", B, [HANDLE])
        self.GetProcessWindowStation = _bind(u, "GetProcessWindowStation", HANDLE, [])
        self.SetProcessWindowStation = _bind(u, "SetProcessWindowStation", B, [HANDLE])
        self.CreateDesktopW = _bind(u, "CreateDesktopW", HANDLE, [LP, V, V, D, D, V])
        self.CloseDesktop = _bind(u, "CloseDesktop", B, [HANDLE])
        self.GetUserObjectInformationW = _bind(
            u, "GetUserObjectInformationW", B, [HANDLE, ctypes.c_int, V, D, P(D)])


_API = None


def api():
    global _API
    if _API is None:
        _API = _Api()
    return _API


# --- SIDs --------------------------------------------------------------------------


class Sid:
    """A SID held in memory this object owns."""

    def __init__(self, data):
        self._buffer = ctypes.create_string_buffer(bytes(data), len(data))

    @property
    def pointer(self):
        return ctypes.cast(self._buffer, PSID)

    @property
    def string(self):
        text = wintypes.LPWSTR()
        if not api().ConvertSidToStringSidW(self.pointer, ctypes.byref(text)):
            raise WinError("ConvertSidToStringSid")
        try:
            return text.value
        finally:
            api().LocalFree(text)

    def __eq__(self, other):
        return isinstance(other, Sid) and self.string == other.string

    def __hash__(self):
        return hash(self.string)

    def __repr__(self):
        return f"Sid({self.string!r})"

    @classmethod
    def copy(cls, pointer):
        length = api().GetLengthSid(pointer)
        return cls(ctypes.string_at(pointer, length))

    @classmethod
    def parse(cls, text):
        pointer = PSID()
        if not api().ConvertStringSidToSidW(text, ctypes.byref(pointer)):
            raise WinError(f"ConvertStringSidToSid({text!r})")
        try:
            return cls.copy(pointer)
        finally:
            api().LocalFree(pointer)


def capability_sid(name):
    """The SID of the AppContainer capability called ``name``."""
    groups, group_count = ctypes.POINTER(PSID)(), wintypes.DWORD()
    sids, sid_count = ctypes.POINTER(PSID)(), wintypes.DWORD()
    if not api().DeriveCapabilitySidsFromName(
            name, ctypes.byref(groups), ctypes.byref(group_count),
            ctypes.byref(sids), ctypes.byref(sid_count)):
        raise WinError(f"DeriveCapabilitySidsFromName({name!r})")
    try:
        if sid_count.value != 1:
            raise WinError(f"capability {name!r}: {sid_count.value} SIDs", 0)
        return Sid.copy(sids[0])
    finally:
        for array, count in ((groups, group_count), (sids, sid_count)):
            for index in range(count.value):
                api().LocalFree(array[index])
            api().LocalFree(array)


def appcontainer_sid(name):
    """The package SID Windows derives from AppContainer name ``name``."""
    pointer = PSID()
    result = api().DeriveAppContainerSidFromAppContainerName(name, ctypes.byref(pointer))
    if result != 0:
        raise WinError("DeriveAppContainerSidFromAppContainerName", result & 0xFFFFFFFF)
    try:
        return Sid.copy(pointer)
    finally:
        api().FreeSid(pointer)


def _own_token(access=TOKEN_QUERY):
    token = HANDLE()
    if not api().OpenProcessToken(api().GetCurrentProcess(), access, ctypes.byref(token)):
        raise WinError("OpenProcessToken")
    return token


def _token_information(token, kind):
    size = wintypes.DWORD()
    api().GetTokenInformation(token, kind, None, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    if not api().GetTokenInformation(token, kind, buffer, size, ctypes.byref(size)):
        raise WinError("GetTokenInformation")
    return buffer


def user_sid():
    """The SID of the user this process runs as."""
    token = _own_token()
    try:
        buffer = _token_information(token, TOKEN_USER_CLASS)
    finally:
        api().CloseHandle(token)
    return Sid.copy(SID_AND_ATTRIBUTES.from_buffer(buffer).Sid)


def logon_sid():
    """The SID of this process's logon session."""
    token = _own_token()
    try:
        buffer = _token_information(token, TOKEN_GROUPS_CLASS)
    finally:
        api().CloseHandle(token)
    count = wintypes.DWORD.from_buffer(buffer).value
    offset = ctypes.sizeof(ctypes.c_void_p)  # the count is padded to a pointer
    groups = (SID_AND_ATTRIBUTES * count).from_buffer(buffer, offset)
    for group in groups:
        if group.Attributes & SE_GROUP_LOGON_ID == SE_GROUP_LOGON_ID:
            return Sid.copy(group.Sid)
    raise WinError("no logon SID in this process's token", 0)


# --- Security descriptors ------------------------------------------------------------


class SecurityDescriptor:
    """A security descriptor parsed from SDDL, freed when garbage collected."""

    def __init__(self, sddl):
        self.pointer = ctypes.c_void_p()
        if not api().ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, 1, ctypes.byref(self.pointer), None):
            raise WinError(f"ConvertStringSecurityDescriptor({sddl!r})")

    def _part(self, getter):
        present, defaulted, acl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        if not getter(self.pointer, ctypes.byref(present), ctypes.byref(acl),
                      ctypes.byref(defaulted)):
            raise WinError("GetSecurityDescriptorDacl/Sacl")
        return acl if present else None

    @property
    def dacl(self):
        return self._part(api().GetSecurityDescriptorDacl)

    @property
    def sacl(self):
        return self._part(api().GetSecurityDescriptorSacl)

    def attributes(self):
        """SECURITY_ATTRIBUTES pointing at this descriptor (not inheritable)."""
        return SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), self.pointer, False)

    def __del__(self):
        if getattr(self, "pointer", None):
            api().LocalFree(self.pointer)
            self.pointer = None


def _descriptor_text(pointer, information):
    text = wintypes.LPWSTR()
    if not api().ConvertSecurityDescriptorToStringSecurityDescriptorW(
            pointer, 1, information, ctypes.byref(text), None):
        raise WinError("ConvertSecurityDescriptorToStringSecurityDescriptor")
    try:
        return text.value
    finally:
        api().LocalFree(text)


def _normal_dacl(text):
    """A DACL's SDDL with its ACEs sorted and only the protected flag kept, so
    two DACLs with the same entries compare equal."""
    body = text[2:] if text.startswith("D:") else text
    flags = body.partition("(")[0]
    return ("P" if "P" in flags else "") + "".join(sorted(re.findall(r"\([^()]*\)", body)))


def dacl_trustees(normal):
    """The SIDs (or SDDL aliases) a normalised DACL has entries for."""
    return {ace.rstrip(")").rsplit(";", 1)[-1] for ace in re.findall(r"\([^()]*\)", normal)}


def dacl_text(descriptor):
    """The DACL of a :class:`SecurityDescriptor`, normalised for comparing."""
    return _normal_dacl(_descriptor_text(descriptor.pointer, DACL_SECURITY_INFORMATION))


def file_dacl(path):
    """The DACL of file or folder ``path``, normalised for comparing."""
    descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
    result = api().GetNamedSecurityInfoW(
        str(path), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, None, None,
        ctypes.byref(dacl), None, ctypes.byref(descriptor))
    if result:
        raise WinError("GetNamedSecurityInfo", result)
    try:
        return _normal_dacl(_descriptor_text(descriptor, DACL_SECURITY_INFORMATION))
    finally:
        api().LocalFree(descriptor)


def object_dacl(handle, kind=7):
    """The DACL of the object ``handle`` (default: a window station or
    desktop), normalised for comparing."""
    descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
    result = api().GetSecurityInfo(HANDLE(handle), kind, DACL_SECURITY_INFORMATION,
                                   None, None, ctypes.byref(dacl), None,
                                   ctypes.byref(descriptor))
    if result:
        raise WinError("GetSecurityInfo", result)
    try:
        return _normal_dacl(_descriptor_text(descriptor, DACL_SECURITY_INFORMATION))
    finally:
        api().LocalFree(descriptor)


def set_file_security(path, dacl_sddl, low_label=False):
    """Replace the DACL of file or folder ``path`` with ``dacl_sddl`` (a
    protected DACL: nothing inherited from above), then, with ``low_label``,
    give it a low mandatory label inherited by everything created in it.

    The DACL goes first: it must grant this process WRITE_OWNER, which setting
    a label needs."""
    descriptor = SecurityDescriptor(dacl_sddl)
    result = api().SetNamedSecurityInfoW(
        str(path), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, descriptor.dacl, None)
    if result:
        raise WinError("SetNamedSecurityInfo (DACL)", result)
    if low_label:
        label = SecurityDescriptor("S:(ML;OICI;NW;;;LW)")
        result = api().SetNamedSecurityInfoW(
            str(path), SE_FILE_OBJECT, LABEL_SECURITY_INFORMATION,
            None, None, None, label.sacl)
        if result:
            raise WinError("SetNamedSecurityInfo (label)", result)


# --- Tokens --------------------------------------------------------------------------


def restricted_token(restricting, deny_only, default_dacl_sddl):
    """A primary token made from this process's own: no privileges but
    SeChangeNotify, the SIDs ``deny_only`` usable only to deny, and access
    checked a second time against the SIDs ``restricting`` alone. Objects
    created with it get the DACL ``default_dacl_sddl``. Close it when done."""
    own = _own_token(TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ASSIGN_PRIMARY
                     | TOKEN_ADJUST_DEFAULT)
    try:
        restrict = (SID_AND_ATTRIBUTES * len(restricting))(
            *[SID_AND_ATTRIBUTES(sid.pointer, 0) for sid in restricting])
        deny = (SID_AND_ATTRIBUTES * max(1, len(deny_only)))(
            *[SID_AND_ATTRIBUTES(sid.pointer, 0) for sid in deny_only])
        token = HANDLE()
        if not api().CreateRestrictedToken(
                own, DISABLE_MAX_PRIVILEGE, len(deny_only), deny if deny_only else None,
                0, None, len(restricting), restrict, ctypes.byref(token)):
            raise WinError("CreateRestrictedToken")
    finally:
        api().CloseHandle(own)
    try:
        descriptor = SecurityDescriptor(default_dacl_sddl)
        holder = ctypes.c_void_p(descriptor.dacl.value)
        if not api().SetTokenInformation(token, TOKEN_DEFAULT_DACL_CLASS,
                                         ctypes.byref(holder), ctypes.sizeof(holder)):
            raise WinError("SetTokenInformation (default DACL)")
    except BaseException:
        api().CloseHandle(token)
        raise
    return token.value


# --- AppContainer profiles ------------------------------------------------------------


def create_profile(name):
    """Register AppContainer ``name`` and return its package SID.

    Windows will not start a process in an AppContainer it has no profile for.
    The profile comes with a folder and a registry key the container could
    write to; :func:`strip_profile` removes both."""
    pointer = PSID()
    result = api().CreateAppContainerProfile(name, name, name, None, 0,
                                             ctypes.byref(pointer))
    if result != 0:
        raise WinError(f"CreateAppContainerProfile({name!r})", result & 0xFFFFFFFF)
    try:
        return Sid.copy(pointer)
    finally:
        api().FreeSid(pointer)


def profile_folder(sid):
    """The AppContainer's own folder (``...\\Packages\\<name>\\AC``)."""
    text = wintypes.LPWSTR()
    result = api().GetAppContainerFolderPath(sid.string, ctypes.byref(text))
    if result != 0:
        raise WinError("GetAppContainerFolderPath", result & 0xFFFFFFFF)
    try:
        return text.value
    finally:
        api().CoTaskMemFree(text)


def delete_storage_key(name):
    """Delete the profile's registry storage key, if there."""
    base = f"{APPCONTAINER_KEY}\\Storage\\{name}"
    for path in (base + "\\Children", base):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass


def delete_profile(name):
    """Unregister AppContainer ``name`` (its folder and keys go too)."""
    result = api().DeleteAppContainerProfile(name)
    if result not in (0, 0x80070002 - (1 << 32), 0x80070002):
        raise WinError(f"DeleteAppContainerProfile({name!r})", result & 0xFFFFFFFF)


def profile_names():
    """The names (monikers) of the AppContainer profiles of this user."""
    names = []
    try:
        mappings = winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPCONTAINER_KEY + "\\Mappings")
    except FileNotFoundError:
        return names
    with mappings:
        index = 0
        while True:
            try:
                sid = winreg.EnumKey(mappings, index)
            except OSError:
                break
            index += 1
            try:
                with winreg.OpenKey(mappings, sid) as key:
                    names.append(winreg.QueryValueEx(key, "Moniker")[0])
            except OSError:
                continue
    return names


# --- Window stations and desktops ---------------------------------------------------------


class Desktop:
    """A new desktop for one sandbox, in a window station that is not the
    user's.

    A normal user cannot make a window station of its own choosing: asked
    for one with no name, Windows hands out the non-interactive window station
    of the logon session (``Service-0x0-<logon id>$``), making it if needed.
    The desktop in it is new, with the given DACL. Processes on it cannot see
    or reach the windows or the screen of the user's desktop, which is in the
    interactive window station ``WinSta0``. The clipboard and atoms belong to
    the window station, which other non-interactive processes of the user may
    share; the job's UI restrictions keep sandboxed processes from both.
    Close it after its processes have ended."""

    def __init__(self, name, sddl, trustees):
        a = api()
        attributes = SecurityDescriptor(sddl).attributes()
        self.station = a.CreateWindowStationW(None, 0, GENERIC_READ | WINSTA_CREATEDESKTOP,
                                              ctypes.byref(attributes))
        if not self.station:
            self.station = a.CreateWindowStationW(
                None, 0, WINSTA_READATTRIBUTES | WINSTA_CREATEDESKTOP,
                ctypes.byref(attributes))
        if not self.station:
            raise WinError("CreateWindowStation")
        self.desktop = None
        try:
            station_name = self._name(self.station)
            if station_name.lower() == "winsta0":
                raise WinError("Windows offered the interactive window station", 0)
            previous = a.GetProcessWindowStation()
            # A desktop is made in the caller's window station.
            if not a.SetProcessWindowStation(self.station):
                raise WinError("SetProcessWindowStation")
            try:
                desktop_attributes = SecurityDescriptor(sddl)
                self.desktop = a.CreateDesktopW(
                    name, None, None, 0, DESKTOP_ALL,
                    ctypes.byref(desktop_attributes.attributes()))
                error = ctypes.get_last_error()
            finally:
                if not a.SetProcessWindowStation(previous):
                    raise WinError("SetProcessWindowStation (back)")
            if not self.desktop:
                raise WinError("CreateDesktop", error)
            found = dacl_trustees(object_dacl(self.desktop))
            if found != set(trustees):
                raise WinError(f"the desktop {name} has an unexpected DACL", 0)
            self.path = station_name + "\\" + name
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _name(handle):
        buffer = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        if not api().GetUserObjectInformationW(handle, UOI_NAME, buffer,
                                               ctypes.sizeof(buffer), ctypes.byref(needed)):
            raise WinError("GetUserObjectInformation")
        return buffer.value

    def close(self):
        if self.desktop:
            api().CloseDesktop(self.desktop)
            self.desktop = None
        if self.station:
            api().CloseWindowStation(self.station)
            self.station = None


# --- Pipes and handles ---------------------------------------------------------------


def pipe():
    """An anonymous pipe: (read end, write end). Only the write end can be
    inherited, so it can be a child's output."""
    read, write = HANDLE(), HANDLE()
    attributes = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, True)
    if not api().CreatePipe(ctypes.byref(read), ctypes.byref(write),
                            ctypes.byref(attributes), 1 << 16):
        raise WinError("CreatePipe")
    os.set_handle_inheritable(read.value, False)
    return read.value, write.value


def null_input():
    """An inheritable handle on the NUL device, for reading and writing (see
    os.devnull in the shim)."""
    attributes = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, True)
    handle = api().CreateFileW("NUL", GENERIC_READ | GENERIC_WRITE, 0x3, ctypes.byref(attributes),
                               3, 0, None)
    if handle in (None, INVALID_HANDLE):
        raise WinError("CreateFile(NUL)")
    return handle


def close(handle):
    if handle:
        api().CloseHandle(HANDLE(handle))


def read(handle, size=1 << 16):
    """Up to ``size`` bytes from ``handle``; b"" once the writers are gone."""
    buffer = ctypes.create_string_buffer(size)
    count = wintypes.DWORD()
    if not api().ReadFile(HANDLE(handle), buffer, size, ctypes.byref(count), None):
        return b""
    return buffer.raw[:count.value]


def wait(handle, milliseconds):
    """True once the process (or other object) ``handle`` is signalled."""
    return api().WaitForSingleObject(HANDLE(handle), int(milliseconds)) == WAIT_OBJECT_0


def exit_code(process):
    code = wintypes.DWORD()
    if not api().GetExitCodeProcess(HANDLE(process), ctypes.byref(code)):
        raise WinError("GetExitCodeProcess")
    return None if code.value == STILL_ACTIVE else code.value


# --- Processes ---------------------------------------------------------------------------


def _environment_block(environment):
    for key, value in environment.items():
        if not key or "=" in key or "\0" in key or "\0" in value:
            raise ValueError(f"bad environment entry {key!r}")
    text = "".join(f"{key}={value}\0" for key, value in
                   sorted(environment.items(), key=lambda item: item[0].upper()))
    return ctypes.create_unicode_buffer(text + "\0")


class Process:
    """A process this module started: its handles and id."""

    def __init__(self, process, thread, pid):
        self.handle, self.thread, self.pid = process, thread, pid

    def close(self):
        close(self.thread)
        close(self.handle)
        self.thread = self.handle = None


def start(argv, cwd, environment, *, token=None, package=None, capabilities=(),
          less_privileged=True, job=None, stdin, stdout, stderr, desktop=None):
    """Start ``argv`` suspended and return a :class:`Process`.

    ``token``: a primary token to run as (else this process's). ``package``: a
    package SID, which puts the process in that AppContainer with
    ``capabilities``; ``less_privileged`` opts it out of the access granted to
    all application packages. ``job``: a job handle the process starts in.
    Only the three standard handles are inherited. Resume the thread with
    :func:`resume` once the caller has checked the process is where it should
    be."""
    a = api()
    count = 1 + (2 if package is not None else 0) + (1 if job is not None else 0)
    size = ctypes.c_size_t()
    a.InitializeProcThreadAttributeList(None, count, 0, ctypes.byref(size))
    attribute_list = ctypes.create_string_buffer(size.value)
    if not a.InitializeProcThreadAttributeList(attribute_list, count, 0, ctypes.byref(size)):
        raise WinError("InitializeProcThreadAttributeList")
    keep = []  # attribute values must outlive CreateProcess

    def add(attribute, value):
        keep.append(value)
        if not a.UpdateProcThreadAttribute(attribute_list, 0, attribute,
                                           ctypes.byref(value), ctypes.sizeof(value),
                                           None, None):
            raise WinError(f"UpdateProcThreadAttribute({attribute:#x})")

    try:
        handles = list(dict.fromkeys(h for h in (stdin, stdout, stderr) if h))
        add(ATTRIBUTE_HANDLE_LIST, (HANDLE * len(handles))(*handles))
        if package is not None:
            capability_array = (SID_AND_ATTRIBUTES * max(1, len(capabilities)))(
                *[SID_AND_ATTRIBUTES(sid.pointer, SE_GROUP_ENABLED)
                  for sid in capabilities])
            keep.append(capability_array)
            add(ATTRIBUTE_SECURITY_CAPABILITIES, SECURITY_CAPABILITIES(
                package.pointer, capability_array if capabilities else None,
                len(capabilities), 0))
            add(ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY, wintypes.DWORD(
                ALL_APPLICATION_PACKAGES_OPT_OUT if less_privileged else 0))
        if job is not None:
            add(ATTRIBUTE_JOB_LIST, (HANDLE * 1)(job))
        info = STARTUPINFOEXW()
        info.StartupInfo.cb = ctypes.sizeof(info)
        info.StartupInfo.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
        info.StartupInfo.wShowWindow = SW_HIDE
        info.StartupInfo.hStdInput, info.StartupInfo.hStdOutput = stdin, stdout
        info.StartupInfo.hStdError = stderr
        desktop_text = ctypes.create_unicode_buffer(desktop) if desktop else None
        if desktop_text is not None:
            info.StartupInfo.lpDesktop = ctypes.cast(desktop_text, wintypes.LPWSTR)
        info.lpAttributeList = ctypes.cast(attribute_list, ctypes.c_void_p)
        result = PROCESS_INFORMATION()
        flags = (EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_NO_WINDOW
                 | CREATE_UNICODE_ENVIRONMENT | CREATE_NEW_PROCESS_GROUP)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        block = _environment_block(environment)
        if token is not None:
            ok = a.CreateProcessAsUserW(token, argv[0], command, None, None, True, flags,
                                        block, str(cwd), ctypes.byref(info),
                                        ctypes.byref(result))
        else:
            ok = a.CreateProcessW(argv[0], command, None, None, True, flags, block,
                                  str(cwd), ctypes.byref(info), ctypes.byref(result))
        if not ok:
            raise WinError("CreateProcess")
        return Process(result.hProcess, result.hThread, result.dwProcessId)
    finally:
        a.DeleteProcThreadAttributeList(attribute_list)


def in_job(process, job):
    answer = wintypes.BOOL()
    if not api().IsProcessInJob(HANDLE(process), HANDLE(job), ctypes.byref(answer)):
        raise WinError("IsProcessInJob")
    return bool(answer.value)


def resume(process):
    if api().ResumeThread(HANDLE(process.thread)) == 0xFFFFFFFF:
        raise WinError("ResumeThread")


def terminate(process, code=1):
    api().TerminateProcess(HANDLE(process.handle), code)
