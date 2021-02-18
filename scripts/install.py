import os
import sys
import platform
import traceback
import shutil
import tempfile
import subprocess
import webbrowser
from pathlib import Path

APP_NAME = 'Creeper'
APP_UID = 'creeper.pyapp.win32'
INSTALLER_NAME = APP_NAME + ' Installer'
APP_DIR = Path(__file__).absolute().parent
WINAPI = None


class WinApi:
    def __init__(self):
        DLL = ctypes.windll
        WT = ctypes.wintypes
        LPWSTR = WT.LPWSTR
        UINT = WT.UINT
        WCHAR = WT.WCHAR
        HWND = WT.HWND
        INT = WT.INT
        HANDLE = WT.HANDLE
        DWORD = WT.DWORD

        _user32 = DLL.user32
        _shell32 = DLL.shell32
        self.MessageBox = _user32.MessageBoxW
        self.MessageBox.argtypes = (
            HWND, LPWSTR, LPWSTR, UINT)

        self.MAX_PATH_WCHAR = WCHAR * 260
        self.SHGetFolderPath = _shell32.SHGetFolderPathW
        self.SHGetFolderPath.argtypes = (
            HWND, INT, HANDLE, DWORD, self.MAX_PATH_WCHAR)


def message_box(msg, icon=None, confirm=False):
    IDOK = 1
    MB_OKCANCEL = 0x00000001

    icons = {
        'info': 0x40,
        'warn': 0x30,
        'error': 0x10,
        'question': 0x20,
    }

    if confirm and icon is None:
        icon = 'question'

    flags = icons.get(icon, 0)
    if confirm:
        flags |= MB_OKCANCEL

    result = WINAPI.MessageBox(None, msg, INSTALLER_NAME, flags)
    if confirm:
        return result == IDOK


def message_box_cmd(msg):
    import subprocess
    msg = msg.replace('"', "'")
    script = f'msgbox ""{msg}"", 0, ""{INSTALLER_NAME}"":close'
    subprocess.run(f'mshta vbscript:Execute("{script}")')


def check_python():
    py_arch = platform.architecture()
    assert py_arch == ('32bit', 'WindowsPE')


def get_winnt_ver():
    ver = sys.getwindowsversion()
    major = str(ver.major)
    minor = str(ver.minor)
    return float(major + '.' + minor)


def is_os_64bit():
    return platform.machine().endswith('64')


class SpecialFolders:
    CSIDL_STARTMENU = 0x000b
    CSIDL_STARTUP = 0x0007
    CSIDL_COMMON_STARTUP = 0x0018

    def _get_dir(self, dir_type):
        assert WINAPI
        path = WINAPI.MAX_PATH_WCHAR()
        result = WINAPI.SHGetFolderPath(None, dir_type, None, 0, path)
        if result != 0:
            return None
        return Path(path.value)

    def start_menu_dir(self, ensure=False):
        path = self._get_dir(self.CSIDL_STARTMENU)
        if not path:
            return

        path = path / APP_NAME
        if ensure:
            path.mkdir(exist_ok=True)
        return path

    def startup_dir(self):
        return self._get_dir(self.CSIDL_STARTUP)

    def startup_dir_all_user(self):
        return self._get_dir(self.CSIDL_COMMON_STARTUP)


def create_shortcut(shortcut_path, target, arguments='', working_dir=''):
    shortcut_path = Path(shortcut_path)
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    target = Path(target)
    if not target.is_absolute():
        working_dir = Path(working_dir)
        assert working_dir.is_absolute()
        target = working_dir / target

    def escape_path(path):
        return str(path).replace('\\', '/')

    def escape_str(str_):
        return str(str_).replace('\\', '\\\\').replace('"', '\\"')

    shortcut_path = escape_path(shortcut_path)
    target = escape_path(target)
    working_dir = escape_path(working_dir)
    arguments = escape_str(arguments)

    js_content = f'''
        var sh = WScript.CreateObject("WScript.Shell");
        var shortcut = sh.CreateShortcut("{shortcut_path}");
        shortcut.TargetPath = "{target}";
        shortcut.Arguments = "{arguments}";
        shortcut.WorkingDirectory = "{working_dir}";
        shortcut.Save();'''

    fd, path = tempfile.mkstemp('.js')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(js_content)
        subprocess.run([R'wscript.exe', path])
    finally:
        os.unlink(path)


def launcher_lnk(folder):
    return folder / f'{APP_NAME} Launcher.lnk'


def uninstaller_lnk(folder):
    return folder / 'Uninstall.lnk'


def install_app():
    FOLDER = SpecialFolders()
    menu_dir = FOLDER.start_menu_dir(True)
    startup_dir = FOLDER.startup_dir()

    if not menu_dir:
        message_box('failed to get menu_dir!', 'error')
        return

    if not startup_dir:
        message_box('failed to get startup_dir!', 'error')
        return

    launcher = launcher_lnk(menu_dir)
    create_shortcut(launcher, 'python/pythonw.exe', 'src.pyc', APP_DIR)
    create_shortcut(
        uninstaller_lnk(menu_dir), 'installer.exe', 'uninstall', APP_DIR)

    shutil.copy(launcher, startup_dir)
    return launcher


def uninstall_app():
    if not message_box(
            'Do you want to remove this app?', confirm=True):
        return

    FOLDER = SpecialFolders()
    menu_dir = FOLDER.start_menu_dir()
    startup_dir = FOLDER.startup_dir()

    if menu_dir:
        shutil.rmtree(menu_dir)

    if startup_dir:
        try:
            os.unlink(launcher_lnk(startup_dir))
        except FileNotFoundError:
            pass


def main():
    if get_winnt_ver() < 6.0:
        message_box('Not support Windows XP or older.', 'error')
        return

    if '--undo' in sys.argv[1:]:
        uninstall_app()
        return

    check_python()
    launcher = install_app()
    os.startfile(launcher)
    message_box(f'{APP_NAME} has been installed successfully!', 'info')


def gen_url_KB2533623():
    arch = 'x64' if is_os_64bit() else 'x86'
    return 'https://github.com/1ocalhost/creeper-bin/blob/main/' + \
        f'Windows6.1-KB2533623-{arch}.msu'


if __name__ == "__main__":
    try:
        import ctypes
        import ctypes.wintypes
    except ImportError:
        message_box_cmd('You should install KB2533623 update.')
        webbrowser.open(gen_url_KB2533623())
        sys.exit(1)

    try:
        WINAPI = WinApi()
        main()
    except Exception:
        tb = traceback.format_exc()
        message_box('Error:\n' + tb, 'error')
