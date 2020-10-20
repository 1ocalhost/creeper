import ctypes
from ctypes import windll, wintypes


INTERNET_PER_CONN_FLAGS = 1
INTERNET_PER_CONN_AUTOCONFIG_URL = 4
INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_PER_CONNECTION_OPTION = 75

PROXY_TYPE_AUTO_PROXY_URL = 4

InternetSetOption = windll.wininet.InternetSetOptionW
InternetQueryOption = windll.wininet.InternetQueryOptionW
GlobalFree = windll.Kernel32.GlobalFree


class INTERNET_PER_CONN_OPTION(ctypes.Structure):
    class Value(ctypes.Union):
        _fields_ = [
            ('dwValue', wintypes.DWORD),
            ('pszValue', wintypes.LPWSTR),
            ('ftValue', wintypes.FILETIME),
        ]

        def set(self, val):
            if type(val) == wintypes.DWORD:
                self.dwValue = val
            elif type(val) == wintypes.LPWSTR:
                self.pszValue = val
            else:
                self.dwValue = 0

    _fields_ = [
        ('dwOption', wintypes.DWORD),
        ('Value', Value),
    ]


class INTERNET_PER_CONN_OPTION_LIST(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('pszConnection', wintypes.LPWSTR),
        ('dwOptionCount', wintypes.DWORD),
        ('dwOptionError', wintypes.DWORD),
        ('pOptions', ctypes.POINTER(INTERNET_PER_CONN_OPTION)),
    ]

    @staticmethod
    def make(opt_items):
        item_num = len(opt_items)
        List = INTERNET_PER_CONN_OPTION_LIST()
        Option = (INTERNET_PER_CONN_OPTION * item_num)()
        nSize = wintypes.DWORD(ctypes.sizeof(INTERNET_PER_CONN_OPTION_LIST))

        index = 0
        for k, v in opt_items:
            Option[index].dwOption = k
            Option[index].Value.set(v)
            index += 1

        List.dwSize = ctypes.sizeof(INTERNET_PER_CONN_OPTION_LIST)
        List.pszConnection = None
        List.dwOptionCount = item_num
        List.dwOptionError = 0
        List.pOptions = Option
        return List, nSize


def get_pac_setting_impl():
    opt_list, size_ = INTERNET_PER_CONN_OPTION_LIST.make([
        (INTERNET_PER_CONN_AUTOCONFIG_URL, None),
        (INTERNET_PER_CONN_FLAGS, None)
    ])

    is_ok = InternetQueryOption(None, INTERNET_OPTION_PER_CONNECTION_OPTION,
                                ctypes.byref(opt_list), ctypes.byref(size_))
    opt = opt_list.pOptions
    v0 = opt[0].Value

    if v0.dwValue:
        url = ctypes.wstring_at(v0.pszValue)
        GlobalFree(v0.dwValue)
    else:
        url = ''

    flags = opt[1].Value.dwValue
    return bool(is_ok), url, flags


def set_pac_setting_impl(url, flags=None):
    if url is None and flags is None:
        return False

    settings = []
    if url is not None:
        url_buf = ctypes.create_unicode_buffer(url)
        url_ = ctypes.cast(url_buf, wintypes.LPWSTR)
        url_item = (INTERNET_PER_CONN_AUTOCONFIG_URL, url_)
        settings.append(url_item)

    if flags is not None:
        flag_item = (INTERNET_PER_CONN_FLAGS, wintypes.DWORD(flags))
        settings.append(flag_item)

    opt_list, size_ = INTERNET_PER_CONN_OPTION_LIST.make(settings)
    is_ok = InternetSetOption(None, INTERNET_OPTION_PER_CONNECTION_OPTION,
                              ctypes.byref(opt_list), size_)
    if not is_ok:
        return False

    InternetSetOption(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
    InternetSetOption(None, INTERNET_OPTION_REFRESH, None, 0)
    return True


def get_pac_setting():
    is_ok, url, flags = get_pac_setting_impl()
    if not is_ok:
        return False, None, None

    is_enabled = flags & PROXY_TYPE_AUTO_PROXY_URL
    return is_ok, url, bool(is_enabled)


def set_pac_setting(pac_file=None, enabled=None):
    if pac_file is None and enabled is None:
        return False

    if enabled is None:
        return set_pac_setting_impl(pac_file)

    is_ok, url, flags = get_pac_setting_impl()
    if not is_ok:
        return False

    if enabled:
        flags |= PROXY_TYPE_AUTO_PROXY_URL
    else:
        flags &= ~PROXY_TYPE_AUTO_PROXY_URL

    return set_pac_setting_impl(pac_file, flags)


def test():
    def show_setting():
        is_ok, url, enabled = get_pac_setting()
        assert is_ok
        print(url, enabled)
        return enabled

    show_setting()

    from time import time
    set_pac_setting(pac_file=f'http://proxy.pac/?t={time()}')
    enabled = show_setting()

    set_pac_setting(pac_file=None, enabled=not enabled)
    show_setting()


if __name__ == '__main__':
    test()
