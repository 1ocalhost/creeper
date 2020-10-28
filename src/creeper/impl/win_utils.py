import ctypes
import ctypes.wintypes

_advapi32 = ctypes.windll.advapi32
RegOpenKeyEx = _advapi32.RegOpenKeyExW
RegQueryValueEx = _advapi32.RegQueryValueExW
RegCloseKey = _advapi32.RegCloseKey


def _get_win_machine_guid_impl(key):
    KEY_NAME = 'MachineGuid'
    REG_SZ = 1
    STR_MAX_LEN = 1024
    DWORD = ctypes.wintypes.DWORD
    UIDStr = ctypes.wintypes.WCHAR * STR_MAX_LEN
    type_ = DWORD()
    cb_data = DWORD()
    uid = UIDStr()

    if RegQueryValueEx(
        key, KEY_NAME, None, ctypes.byref(type_),
            None, ctypes.byref(cb_data)):
        return

    if type_.value != REG_SZ:
        return

    if (cb_data.value / 2) > STR_MAX_LEN:
        return

    if RegQueryValueEx(
        key, KEY_NAME, None, None,
            uid, ctypes.byref(cb_data)):
        return

    return uid.value


def get_win_machine_guid():
    HKEY = ctypes.c_void_p
    HKEY_LOCAL_MACHINE = 0x80000002
    KEY_READ = 131097
    KEY_WOW64_64KEY = 0x0100

    key = HKEY()
    if RegOpenKeyEx(
        HKEY_LOCAL_MACHINE, R'SOFTWARE\Microsoft\Cryptography',
            0, KEY_READ | KEY_WOW64_64KEY, ctypes.byref(key)):
        return

    result = _get_win_machine_guid_impl(key)
    RegCloseKey(key)
    return result
