import os
import sys
import ctypes
import ctypes.wintypes
from subprocess import call, CREATE_NO_WINDOW

_user32 = ctypes.windll.user32
_advapi32 = ctypes.windll.advapi32

_MessageBoxW = _user32.MessageBoxW
RegOpenKeyEx = _advapi32.RegOpenKeyExW
RegQueryValueEx = _advapi32.RegQueryValueExW
RegCloseKey = _advapi32.RegCloseKey


class MsgBox:
    MB_OK = 0
    MB_OKCANCEL = 1
    MB_YESNOCANCEL = 3
    MB_YESNO = 4

    MB_SETFOREGROUND = 0x00010000
    MB_ICONERROR = 0x00000010
    MB_ICONQUESTION = 0x00000020
    MB_ICONWARNING = 0x00000030
    MB_ICONINFORMATION = 0x00000040

    MB_DEFBUTTON1 = 0x00000000
    MB_DEFBUTTON2 = 0x00000100
    MB_DEFBUTTON3 = 0x00000200

    IDOK = 1
    IDCANCEL = 2
    IDABORT = 3
    IDYES = 6
    IDNO = 7

    @staticmethod
    def show(text, caption, flags):
        return _MessageBoxW(None, text, caption, flags)


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


def _get_self_cmd():
    def escape(str_):
        if ' ' in str_:
            return f'"{str_}"'
        return str_

    args = [sys.executable] + sys.argv
    return ' '.join(map(escape, args))


def _get_exit_cmd():
    pid = os.getpid()
    return f'taskkill /F /PID {pid}'


def exec_cmd(cmd):
    call(cmd, shell=True, creationflags=CREATE_NO_WINDOW)


def exit_app():
    exec_cmd(_get_exit_cmd())


def restart_app():
    exit_cmd = _get_exit_cmd()
    self_cmd = _get_self_cmd()
    exec_cmd(f'{exit_cmd} && start {self_cmd}')
