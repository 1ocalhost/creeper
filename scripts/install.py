import os
import sys
import platform
import traceback
import shutil
import tempfile
import subprocess
from pathlib import Path
from functools import lru_cache

APP_NAME = 'Creeper'
APP_UID = 'creeper.pyapp.win32'
INSTALLER_NAME = APP_NAME + ' Installer'
APP_DIR = Path(__file__).absolute().parent
WINAPI = None
FOLDER = None


def try_os_remove(path):
    return try_os_unlink(path)


def try_os_unlink(path):
    try:
        return os.unlink(path)
    except FileNotFoundError:
        pass


def try_os_rmdir(path):
    try:
        return os.rmdir(path)
    except FileNotFoundError:
        pass


def try_sh_move(src, dst):
    try:
        return shutil.move(src, dst)
    except FileNotFoundError:
        pass


def try_sh_copytree(src, dst):
    try:
        return shutil.copytree(src, dst)
    except FileNotFoundError:
        pass


def try_sh_rmtree(path):
    try:
        return shutil.rmtree(path)
    except FileNotFoundError:
        pass


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

    @lru_cache
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


def create_shortcut(
        shortcut_path, target, arguments='',
        working_dir='', icon=''):
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
    icon = escape_path(icon)
    arguments = escape_str(arguments)

    icon_line = ''
    if icon:
        icon_line = f'shortcut.IconLocation = "{icon}";'

    js_content = f'''
        var sh = WScript.CreateObject("WScript.Shell");
        var shortcut = sh.CreateShortcut("{shortcut_path}");
        shortcut.TargetPath = "{target}";
        shortcut.Arguments = "{arguments}";
        shortcut.WorkingDirectory = "{working_dir}";
        {icon_line}
        shortcut.Save();'''

    fd, path = tempfile.mkstemp('.js')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(js_content)
        subprocess.run([R'wscript.exe', path])
    finally:
        try_os_unlink(path)


def launcher_lnk(folder):
    return folder / f'{APP_NAME} Launcher.lnk'


def uninstaller_lnk(folder):
    return folder / f'{APP_NAME} Uninstaller.lnk'


def install_app_impl():
    menu_dir = FOLDER.start_menu_dir(True)
    startup_dir = FOLDER.startup_dir()

    if not menu_dir:
        message_box('failed to get menu_dir!', 'error')
        return

    if not startup_dir:
        message_box('failed to get startup_dir!', 'error')
        return

    launcher = launcher_lnk(menu_dir)
    create_shortcut(
        launcher, 'python/pythonw.exe', 'src.pyc',
        APP_DIR, APP_DIR / 'data/icons/tray_play.ico')
    create_shortcut(
        uninstaller_lnk(menu_dir),
        'installer.exe', 'copy-uninstall', APP_DIR)

    enable_startup()
    return launcher


def try_uninstall_app_old():
    startup_dir = FOLDER.startup_dir()
    if not startup_dir:
        return

    launcher = Path(startup_dir) / f'{APP_UID}.vbs'
    try_os_remove(launcher)


def restore_user_files():
    is_upgrade = (APP_DIR / 'data.old').exists()
    if not is_upgrade:
        return

    old_ver_file = APP_DIR / 'data.old/html/version.json'
    is_former_too_old = not old_ver_file.exists()
    if is_former_too_old:
        try_uninstall_app_old()
        return

    user_conf_old = APP_DIR / 'data.old/conf/user'
    user_conf = APP_DIR / 'data/conf/user'

    try_os_rmdir(user_conf)
    try_sh_copytree(user_conf_old, user_conf)


def install_app():
    restore_user_files()
    check_python()
    launcher = install_app_impl()
    os.startfile(launcher)


def enable_startup(enable=True):
    startup_dir = FOLDER.startup_dir()
    if not startup_dir:
        return

    if enable:
        menu_dir = FOLDER.start_menu_dir()
        launcher = launcher_lnk(menu_dir)
        shutil.copy(launcher, startup_dir)
    else:
        try_os_unlink(launcher_lnk(startup_dir))


def did_enable_startup():
    startup_dir = FOLDER.startup_dir()
    if not startup_dir:
        return False

    return launcher_lnk(startup_dir).exists()


def uninstall_app():
    menu_dir = FOLDER.start_menu_dir()
    if menu_dir:
        try_sh_rmtree(menu_dir)

    enable_startup(False)

    sys.path.append(str(APP_DIR / 'src.pyc'))
    from creeper.impl.win_pac_setting import set_pac_setting
    set_pac_setting('', False)


def main():
    if get_winnt_ver() < 6.0:
        message_box('Not support Windows XP or older.', 'error')
        return

    args = sys.argv[1:]
    if len(args) == 0:
        install_app()
    elif len(args) == 1:
        if '--undo' in args:
            uninstall_app()


def gen_url_KB2533623():
    arch = 'x64' if is_os_64bit() else 'x86'
    return 'https://github.com/1ocalhost/creeper-bin/blob/main/' + \
        f'Windows6.1-KB2533623-{arch}.msu'


def open_url(url):
    # NOYE: Chrome will lock CWD
    tmp_dir = tempfile.gettempdir()
    cmd = f'cd /D "{tmp_dir}" && start "" "{url}"'
    subprocess.call(
        cmd, shell=True,
        creationflags=subprocess.CREATE_NO_WINDOW)


is_main = (__name__ == '__main__')

try:
    import ctypes
    import ctypes.wintypes
except ImportError:
    if is_main:
        message_box_cmd('You should install KB2533623 update.')
        open_url(gen_url_KB2533623())
        sys.exit(1)
    else:
        raise

try:
    WINAPI = WinApi()
    FOLDER = SpecialFolders()
    if is_main:
        main()
except Exception:
    if is_main:
        tb = traceback.format_exc()
        message_box('Error:\n' + tb, 'error')
    else:
        raise
