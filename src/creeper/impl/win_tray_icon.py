'''
This project is inspired by:
  * http://www.brunningonline.net/simon/blog/archives/SysTrayIcon.py.html
  * https://github.com/Infinidat/infi.systray
'''

import os
import ctypes
import ctypes.wintypes
import functools
import time
from types import SimpleNamespace
from threading import Thread, Event

from creeper.log import logger
from creeper.utils import readable_exc


def _structure(fields):
    class _class(ctypes.Structure):
        _fields_ = fields
    return _class


def _func_byref(func, *pos):
    def _func(*args):
        args_ = []
        for num, arg in enumerate(args, start=1):
            if num in pos:
                args_.append(ctypes.byref(arg))
            else:
                args_.append(arg)
        return func(*args_)
    return _func


class win32con:
    CS_VREDRAW = 1
    CS_HREDRAW = 2
    IDC_ARROW = 32512
    COLOR_WINDOW = 5
    WS_OVERLAPPED = 0
    WS_SYSMENU = 524288
    LR_LOADFROMFILE = 16
    LR_DEFAULTSIZE = 64
    IMAGE_ICON = 1
    IDI_APPLICATION = 32512
    WM_RBUTTONUP = 517
    WM_COMMAND = 273
    WM_USER = 1024
    MF_STRING = 0
    MF_BYCOMMAND = 0
    MF_ENABLED = 0
    MF_DISABLED = 2
    SM_CXSMICON = 49
    SM_CYSMICON = 50
    DI_NORMAL = 3
    DIB_RGB_COLORS = 0
    BI_RGB = 0


class win32api:
    _user32 = ctypes.windll.user32
    GetSystemMetrics = _user32.GetSystemMetrics
    _GetCursorPos = _user32.GetCursorPos

    def GetCursorPos():
        pos = ctypes.wintypes.POINT()
        win32api._GetCursorPos(ctypes.byref(pos))
        return pos

    def LOWORD(v):
        return v & 0xFFFF


class win32gui:
    NIM_ADD = 0
    NIM_MODIFY = 1
    NIM_DELETE = 2
    NIM_SETVERSION = 4
    NIF_MESSAGE = 1
    NIF_ICON = 2
    NIF_TIP = 4
    NIF_INFO = 16
    SZTIP_MAX_LENGTH = 128
    NOTIFYICON_VERSION = 3
    NOTIFYICON_VERSION_4 = 4

    # so we can get coordinates from mouse event
    APP_NOTIFYICON_VER = NOTIFYICON_VERSION_4

    _kernel32 = ctypes.windll.kernel32
    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32
    _gdi32 = ctypes.windll.gdi32

    GetModuleHandle = _kernel32.GetModuleHandleW
    LoadCursor = _user32.LoadCursorW
    DefWindowProc = _user32.DefWindowProcW
    RegisterClass = _func_byref(_user32.RegisterClassW, 1)
    UnregisterClass = _user32.UnregisterClassW
    CreateWindowEx = _user32.CreateWindowExW
    CreateWindow = functools.partial(CreateWindowEx, 0)
    UpdateWindow = _user32.UpdateWindow
    LoadImage = _user32.LoadImageW
    LoadIcon = _user32.LoadIconW
    DestroyIcon = _user32.DestroyIcon
    CreatePopupMenu = _user32.CreatePopupMenu
    AppendMenu = _user32.AppendMenuW
    TrackPopupMenu = _user32.TrackPopupMenu
    EnableMenuItem = _user32.EnableMenuItem
    SetForegroundWindow = _user32.SetForegroundWindow
    SetMenuItemBitmaps = _user32.SetMenuItemBitmaps
    SelectObject = _gdi32.SelectObject
    CreateCompatibleDC = _gdi32.CreateCompatibleDC
    GetDC = _user32.GetDC
    DeleteDC = _user32.GetDC
    DrawIconEx = _user32.DrawIconEx
    _Shell_NotifyIcon = _func_byref(_shell32.Shell_NotifyIconW, 2)

    _wintypes = ctypes.wintypes
    LPARAM = _wintypes.LPARAM
    WPARAM = _wintypes.WPARAM
    HANDLE = _wintypes.HANDLE
    DWORD = _wintypes.DWORD
    LPCWSTR = _wintypes.LPCWSTR
    CHAR = _wintypes.CHAR
    WCHAR = _wintypes.WCHAR
    INT = _wintypes.INT
    UINT = _wintypes.UINT
    GUID = CHAR * 16

    PCWSTR = LPCWSTR
    LONG_PTR = LPARAM
    LRESULT = LONG_PTR

    WNDPROC_ARGTYPES = HANDLE, ctypes.c_uint, WPARAM, LPARAM
    LPFN_WNDPROC = ctypes.CFUNCTYPE(LRESULT, *WNDPROC_ARGTYPES)

    WNDCLASS = _structure([
            ("style", UINT),
            ("lpfnWndProc", LPFN_WNDPROC),
            ("cbClsExtra", INT),
            ("cbWndExtra", INT),
            ("hInstance", HANDLE),
            ("hIcon", HANDLE),
            ("hCursor", HANDLE),
            ("hbrBackground", HANDLE),
            ("lpszMenuName", PCWSTR),
            ("lpszClassName", PCWSTR),
        ])

    NOTIFYICONDATA = _structure([
            ("cbSize", DWORD),
            ("hWnd", HANDLE),
            ("uID", UINT),
            ("uFlags", UINT),
            ("uCallbackMessage", UINT),
            ("hIcon", HANDLE),
            ("szTip", WCHAR * SZTIP_MAX_LENGTH),
            ("dwState", UINT),
            ("dwStateMask", UINT),
            ("szInfo", WCHAR * 256),
            ("uTimeout", UINT),
            ("szInfoTitle", WCHAR * 64),
            ("dwInfoFlags", UINT),
            ("guidItem", GUID),
            ("hBalloonIcon", HANDLE),
        ])

    def PumpMessages():
        _user32 = ctypes.windll.user32
        GetMessage = _func_byref(_user32.GetMessageW, 1)
        TranslateMessage = _func_byref(_user32.TranslateMessage, 1)
        DispatchMessage = _func_byref(_user32.DispatchMessageW, 1)

        msg = ctypes.wintypes.MSG()
        while GetMessage(msg, None, 0, 0) > 0:
            TranslateMessage(msg)
            DispatchMessage(msg)

    def Shell_NotifyIcon(action, args):
        data = win32gui.NOTIFYICONDATA(0, *args)
        data.cbSize = ctypes.sizeof(data)
        return win32gui._Shell_NotifyIcon(action, data)


class win32ex:
    _gdi32 = ctypes.windll.gdi32
    CreateDIBSection = _gdi32.CreateDIBSection

    BITMAPINFOHEADER = _structure([
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ])


win32gui.DefWindowProc.argtypes = win32gui.WNDPROC_ARGTYPES


class _WindowClass:
    def __init__(self, hinst, win_proc):
        self._hinst = hinst
        self._win_proc = win_proc
        self._class_name = None

    def _make_class_data(self):
        # must keep the WNDCLASS in whole lifecycle
        window_class = win32gui.WNDCLASS()
        window_class.hInstance = self._hinst
        window_class.lpszClassName = self._class_name
        window_class.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW
        window_class.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        window_class.hbrBackground = win32con.COLOR_WINDOW
        window_class.lpfnWndProc = win32gui.LPFN_WNDPROC(self._win_proc)
        return window_class

    def register(self):
        if self._class_name is not None:
            return False

        self._class_name = 'class_' + str(time.time())
        self._window_class = self._make_class_data()
        self._class_atom = win32gui.RegisterClass(self._window_class)
        return self._class_atom

    def unregister(self):
        return win32gui.UnregisterClass(self._class_atom, self._hinst)


class _TrayIcon:
    WM_SHELL_NOTIFY = win32con.WM_USER + 1

    def __init__(self):
        self._notify_id = None
        self._icon_loaded = {}
        self._default_icon = win32gui.LoadIcon(
            0, win32con.IDI_APPLICATION)
        self._magic_handler = None

    def init(self, hinst, hwnd):
        self._hinst = hinst
        self._hwnd = hwnd

    def _load_icon(self, file_path):
        hicon = self._icon_loaded.get(file_path)
        if hicon is not None:
            return hicon

        if not os.path.isfile(file_path):
            return self._default_icon

        hinst = win32gui.GetModuleHandle(None)
        ICON_FLAGS = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        hicon = win32gui.LoadImage(
            hinst, str(file_path), win32con.IMAGE_ICON, 0, 0, ICON_FLAGS)

        if not hicon:
            return self._default_icon

        if len(self._icon_loaded) > 100:
            for icon in self._icon_loaded.values():
                win32gui.DestroyIcon(icon)
            self._icon_loaded.clear()

        self._icon_loaded[file_path] = hicon
        return hicon

    def update(self, icon=None, hover_text=None):
        types_flag = 0

        if icon is not None:
            hicon = self._load_icon(icon)
            types_flag |= win32gui.NIF_ICON
        else:
            hicon = None

        if hover_text is not None:
            types_flag |= win32gui.NIF_TIP
            text_array = str(hover_text)
        else:
            text_array = ''

        if not types_flag:
            return

        if self._notify_id:
            message = win32gui.NIM_MODIFY
        else:
            self._set_verison(win32gui.APP_NOTIFYICON_VER)
            message = win32gui.NIM_ADD
            types_flag |= win32gui.NIF_MESSAGE

        self._notify_id = (
            self._hwnd, 0, types_flag,
            self.WM_SHELL_NOTIFY, hicon, text_array)

        return win32gui.Shell_NotifyIcon(message, self._notify_id)

    def _set_verison(self, ver):
        nid = self._hwnd, 0, 0, 0, None, '', 0, 0, '', ver
        win32gui.Shell_NotifyIcon(win32gui.NIM_SETVERSION, nid)

    def sys_notify(self, title, msg, type_='info'):
        if not self._notify_id:
            return

        flag = {
            'info': 1,
            'warning': 2,
            'error': 3,
        }.get(type_, 0)

        notify_id = (
            self._hwnd, 0, win32gui.NIF_INFO,
            0, 0, '', 0, 0, msg, 0, title, flag)
        return win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, notify_id)

    def destroy(self):
        nid = (self._hwnd, 0)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)

    def set_magic_handler(self, handler):
        self._magic_handler = handler

    def on_magic_command(self):
        if self._magic_handler:
            self._magic_handler(self)


class _TrayIconWindow:
    def __init__(self, tray_icon, window_title):
        self._msg_handler = None
        self._tray_icon = tray_icon
        self._window_title = window_title
        self._hinst = win32gui.GetModuleHandle(None)
        self._win_class = _WindowClass(self._hinst, self._window_proc)

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if self._msg_handler:
            self._msg_handler.on_msg(hwnd, msg, wparam, lparam)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _create_window(self, atom):
        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        hwnd = win32gui.CreateWindow(
            atom, self._window_title, style, 0, 0,
            100, 100, 0, 0, self._hinst, None)

        if hwnd:
            win32gui.UpdateWindow(hwnd)
        return hwnd

    def start(self, icon, text, handler, event):
        atom = self._win_class.register()
        if not atom:
            return

        hwnd = self._create_window(atom)
        if not hwnd:
            return

        tray_icon = self._tray_icon
        tray_icon.init(self._hinst, hwnd)
        tray_icon.update(icon, text)
        self._msg_handler = handler

        event.set()
        win32gui.PumpMessages()
        tray_icon.destroy()
        self._win_class.unregister()


class _IconBitmapResource:
    ICON_WIDTH = win32api.GetSystemMetrics(win32con.SM_CXSMICON)
    ICON_HEIGHT = win32api.GetSystemMetrics(win32con.SM_CYSMICON)

    def __init__(self):
        self._bmp = {}

    def _create_dib_section(self, width, height):
        hdr = win32ex.BITMAPINFOHEADER()
        hdr.biSize = ctypes.sizeof(hdr)
        hdr.biWidth = width
        hdr.biHeight = height
        hdr.biPlanes = 1
        hdr.biBitCount = 32
        hdr.biCompression = win32con.BI_RGB
        hdr.biSizeImage = width * height * 4
        hdr.biClrUsed = 0
        hdr.biClrImportant = 0
        pixels = ctypes.c_void_p()
        hdcScreen = win32gui.GetDC(None)
        return win32ex.CreateDIBSection(
            hdcScreen, ctypes.byref(hdr), win32con.DIB_RGB_COLORS,
            ctypes.byref(pixels), None, 0)

    def _load_icon_as_bmp(self, file_path):
        if not os.path.isfile(file_path):
            return

        width, height = self.ICON_WIDTH, self.ICON_HEIGHT
        hicon = win32gui.LoadImage(
            0, str(file_path), win32con.IMAGE_ICON,
            width, height, win32con.LR_LOADFROMFILE)

        if not hicon:
            return

        bmp = self._create_dib_section(width, height)
        bmp_dc = win32gui.CreateCompatibleDC(None)
        old_bmp = win32gui.SelectObject(bmp_dc, bmp)
        win32gui.DrawIconEx(
            bmp_dc, 0, 0, hicon, width, height, 0, 0, win32con.DI_NORMAL)
        win32gui.SelectObject(bmp_dc, old_bmp)
        win32gui.DeleteDC(bmp_dc)
        win32gui.DestroyIcon(hicon)
        return bmp

    def load(self, file_path):
        bmp = self._bmp.get(file_path)
        if bmp is not None:
            return bmp

        bmp = self._load_icon_as_bmp(file_path)
        self._bmp[file_path] = bmp
        return bmp


class _TrayIconMenuHandler:
    def __init__(self, menu, tray_icon):
        self._tray_icon = tray_icon
        self._menu_opt = self._normalize_menu_opt(menu)
        self._menu_gui = None
        self._icon_res = _IconBitmapResource()
        self._msg_handlers = {
            _TrayIcon.WM_SHELL_NOTIFY: self._on_shell_notify,
            win32con.WM_COMMAND: self._on_command,
        }

    @staticmethod
    def _normalize_menu_opt(menu):
        new_opt = {}
        for id_, item in enumerate(menu, 5000):
            obj = SimpleNamespace()
            obj.icon = item[0]
            obj.text = item[1]
            obj.handler = item[2]
            obj.enabled = None
            if len(item) > 3:
                obj.enabled = item[3]
            new_opt[id_] = obj
        return new_opt

    def _create_menu(self):
        self._menu_gui = win32gui.CreatePopupMenu()
        for id_, item in self._menu_opt.items():
            win32gui.AppendMenu(
                self._menu_gui, win32con.MF_STRING, id_, item.text)

            bmp = self._icon_res.load(item.icon)
            if bmp:
                win32gui.SetMenuItemBitmaps(
                    self._menu_gui, id_, win32con.MF_BYCOMMAND, bmp, bmp)

    def _update_menu(self):
        for id_, item in self._menu_opt.items():
            if item.enabled is None:
                continue

            if item.enabled():
                flag = win32con.MF_ENABLED
            else:
                flag = win32con.MF_DISABLED
            win32gui.EnableMenuItem(
                self._menu_gui, id_, win32con.MF_BYCOMMAND | flag)

    def _get_pos_from_wparam(self, wparam):
        use_v4 = win32gui.APP_NOTIFYICON_VER == win32gui.NOTIFYICON_VERSION_4
        if use_v4 and wparam:
            x = wparam & 0xFFFF
            y = (wparam >> 16) & 0xFFFF
            return SimpleNamespace(x=x, y=y)
        return win32api.GetCursorPos()

    def _show_menu(self, hwnd, wparam):
        pos = self._get_pos_from_wparam(wparam)
        if self._menu_gui is None:
            self._create_menu()

        self._update_menu()
        win32gui.SetForegroundWindow(hwnd)
        win32gui.TrackPopupMenu(
            self._menu_gui, None, pos.x, pos.y, None, hwnd, None)

    @staticmethod
    def _is_magic_command():
        GetKeyState = ctypes.windll.user32.GetKeyState
        VK_SHIFT = 0x10
        return bool(GetKeyState(VK_SHIFT) & 0x8000)

    def _on_shell_notify(self, hwnd, wparam, lparam):
        if lparam == win32con.WM_RBUTTONUP:
            if self._is_magic_command():
                self._tray_icon.on_magic_command()
            else:
                self._show_menu(hwnd, wparam)

    def _on_command(self, hwnd, wparam, lparam):
        menu_id = win32api.LOWORD(wparam)
        item = self._menu_opt.get(menu_id)
        if not item or not item.handler:
            return

        try:
            item.handler(self._tray_icon)
        except Exception as exc:
            logger.error(f'tray handler error: {readable_exc(exc)}')

    def on_msg(self, hwnd, msg, wparam, lparam):
        handler = self._msg_handlers.get(msg)
        if handler:
            handler(hwnd, wparam, lparam)


def start_tray_icon_menu(menu, icon, description, window_title=''):
    tray_icon = _TrayIcon()
    window = _TrayIconWindow(tray_icon, window_title)
    handler = _TrayIconMenuHandler(menu, tray_icon)
    event = Event()

    args = icon, description, handler, event
    Thread(target=window.start, args=args).start()
    event.wait()
    return tray_icon
