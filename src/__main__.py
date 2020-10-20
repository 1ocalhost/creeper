import sys
import platform
from subprocess import check_output, CREATE_NO_WINDOW
from creeper.env import MAIN_DIR


def check_python():
    return platform.architecture() == ('32bit', 'WindowsPE')


def check_os():
    def get_winnt_ver():
        ver = sys.getwindowsversion()
        major = str(ver.major)
        minor = str(ver.minor)
        return float(major + '.' + minor)

    def find_win_hotfix(kb):
        args = ['wmic', 'qfe', 'get', 'hotfixid']
        fix_installed = check_output(
            args, creationflags=CREATE_NO_WINDOW)
        return -1 != fix_installed.find(kb.encode())

    if get_winnt_ver() < 6.2:  # Windows 7 or older
        if (not find_win_hotfix('KB2533623')):
            return False

    return True


def main():
    assert check_python()
    assert check_os()
    sys.path.append(str(MAIN_DIR / 'third_party'))

    from creeper.app import App
    App().run()


main()
