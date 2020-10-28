import os
import sys
import platform
import traceback
import webbrowser
from pathlib import Path

APP_NAME = 'Creeper'
APP_UID = 'creeper.pyapp.win32'
INSTALLER_NAME = APP_NAME + ' Installer'


def message_box(msg, icon='info'):
    icons = {
        'info': 0x40,
        'warn': 0x30,
        'error': 0x10,
    }

    MessageBox = ctypes.windll.user32.MessageBoxW
    flags = icons.get(icon, 0)
    MessageBox(0, msg, INSTALLER_NAME, flags)


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


def get_win_startup_path(all_user=False):
    _shell32 = ctypes.windll.shell32
    SHGetFolderPath = _shell32.SHGetFolderPathW

    CSIDL_STARTUP = 7
    CSIDL_COMMON_STARTUP = 24
    flag = CSIDL_COMMON_STARTUP if all_user else CSIDL_STARTUP

    PathStr = ctypes.wintypes.WCHAR * 260
    path = PathStr()
    result = SHGetFolderPath(0, flag, 0, 0, path)
    return path.value if result == 0 else None


def install_app():
    startup_dir = get_win_startup_path()
    if not startup_dir:
        message_box('get_win_startup_path() Failed!', 'error')
        return

    app_dir = str(Path(__file__).parent)
    content = '\n'.join([
        'Set sh = CreateObject("WScript.Shell")',
        f'sh.CurrentDirectory = "{app_dir}"',
        R'sh.run "python\pythonw.exe src.pyc"',
    ])

    launcher = Path(startup_dir) / f'{APP_UID}.vbs'
    with open(launcher, 'w') as f:
        f.write(content)
    return launcher


def main():
    if get_winnt_ver() < 6.0:
        message_box('Not support Windows XP or older.', 'error')
        return

    check_python()
    launcher = install_app()
    message_box(f'{APP_NAME} has been installed successfully!')
    os.startfile(launcher)


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
        main()
    except Exception:
        tb = traceback.format_exc()
        message_box('Error:\n' + tb, 'error')
