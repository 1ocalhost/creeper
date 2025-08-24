import sys
import errno
import asyncio
import aiosocks

from creeper.utils import check_singleton
from creeper.impl import http_proxy
from creeper.env import ICON_DIR, \
    APP_NAME, APP_CONF, USER_CONF, ENV_NO_BACKEND
from creeper.log import logger
from creeper.proxy.router import Router
from creeper.proxy.pac import PACServer
from creeper.proxy.backend import backend_utilitys, Backend
from creeper.components import statistic
from creeper.components.update import check_update
from creeper.http_api import get_api_filter
from creeper.impl.win_tray_icon import start_tray_icon_menu
from creeper.impl.win_utils import MsgBox, open_url, exit_app, restart_app

ADDR_ANY = '0.0.0.0'
ADDR_LOCAL = '127.0.0.1'

ROUTE_DNS_ERROR = 0
ROUTE_ALL_DIRECT = 1
ROUTE_ALL_PROXY = 2
ROUTE_SELECT_DIRECT = 3
ROUTE_SELECT_PROXY = 4


class AppIcons:
    def __init__(self):
        icons_dir = ICON_DIR
        self.play = icons_dir / 'play.ico'
        self.stop = icons_dir / 'stop.ico'
        self.settings = icons_dir / 'settings.ico'
        self.tray_play = icons_dir / 'tray_play.ico'
        self.tray_play_lan = icons_dir / 'tray_play_lan.ico'
        self.tray_stop = icons_dir / 'tray_stop.ico'


class App:
    def __init__(self):
        self.listen_any_addr = USER_CONF.allow_lan \
            or USER_CONF.allow_lan_once
        if self.listen_any_addr:
            host_name, host_ip = 'any', ADDR_ANY
        else:
            host_name, host_ip = 'local', ADDR_LOCAL

        self.smart_mode = True
        self.update_via_proxy = False
        self.http_server = None
        self.icons = AppIcons()
        self.tray_icon = None
        self.app_host = host_ip
        self.app_host_name = host_name
        self.app_port = APP_CONF['main_port']
        self.router = Router()
        self.pac_server = PACServer(self)
        self.backend = None
        self.need_restart = False

    @property
    def did_allow_lan(self):
        return USER_CONF.allow_lan

    @property
    def did_enable_proxy(self):
        return USER_CONF.enable_proxy

    @did_enable_proxy.setter
    def did_enable_proxy(self, value):
        USER_CONF.enable_proxy = value

    @property
    def base_url(self):
        return f'http://{ADDR_LOCAL}:{self.app_port}'

    def is_all_direct(self):
        if not self.did_enable_proxy:
            return True

        if not self.backend or not self.backend.port:
            return True

        return False

    @staticmethod
    def make_connection_dns_error(host):
        statistic.on_route('DNS_ERROR', f'DNS_ERROR: {host}')

    async def make_connection(self, route_type, host, port=None):
        if route_type == ROUTE_DNS_ERROR:
            return self.make_connection_dns_error(host)

        if host == 'localhost':
            remote = '127.0.0.1'
        else:
            remote = host

        ip = None

        if self.is_all_direct():
            if route_type != ROUTE_ALL_DIRECT:
                route_type = ROUTE_ALL_DIRECT

        if route_type == ROUTE_ALL_DIRECT:
            via_proxy = False
            route_log = 'ALL_DIRECT'
        elif route_type == ROUTE_ALL_PROXY:
            via_proxy = True
            route_log = 'ALL_PROXY'
        elif route_type == ROUTE_SELECT_DIRECT:
            via_proxy = False
            route_log = 'SELECT_DIRECT'
        elif route_type == ROUTE_SELECT_PROXY:
            via_proxy = True
            route_log = 'SELECT_PROXY'

        route_log = f'[{route_log}] {host}'
        if ip:
            route_log = f'{route_log} ({ip})'

        if via_proxy:
            backend = aiosocks.Socks5Addr(self.backend.host, self.backend.port)
            statistic.on_route('PROXY', route_log)
            dst = (remote, port)
            connection = await aiosocks.open_connection(
                proxy=backend, proxy_auth=None,
                dst=dst, remote_resolve=True)
        else:
            statistic.on_route('DIRECT', route_log)
            connection = await asyncio.open_connection(remote, port)

        def statistic_(is_out, bytes_):
            statistic.on_transfer(via_proxy, is_out, bytes_)

        return connection, statistic_

    async def on_open_conn(self, host, port):
        if self.is_all_direct():
            return await self.make_connection(ROUTE_ALL_DIRECT, host, port)

        if not self.smart_mode:
            return await self.make_connection(ROUTE_ALL_PROXY, host, port)

        via_proxy = await self.router.need_proxy(host)

        if via_proxy is None:
            return await self.make_connection(ROUTE_DNS_ERROR, host)
        elif via_proxy:
            return await self.make_connection(ROUTE_SELECT_PROXY, host, port)
        else:
            return await self.make_connection(ROUTE_SELECT_DIRECT, host, port)

    def on_server_started(self, server, addr):
        self.http_server = server
        host, port = addr
        logger.info(f'serving on: {host}:{port}')
        tray_tip = f'{APP_NAME} ({self.app_host_name}:{port})'
        self.tray_icon.update(hover_text=tray_tip)

        if not self.pac_server.update_sys_setting(True):
            logger.error('update pac setting')

    def did_listening_socket_close(self, exc):
        if isinstance(exc, OSError) and '[WinError 64]' in str(exc):
            return True

        if self.http_server.sockets[0].fileno() == -1:
            return True

        return False

    def on_server_exc(self, exc):
        if self.need_restart:
            return

        if self.did_listening_socket_close(exc):
            self.need_restart = True
            self.update_state_icon()
            self.pac_server.update_sys_setting(False)

    def start_server(self):
        http_filter = get_api_filter(self)
        opt = {
            'open_conn': self.on_open_conn,
            'req_filter': http_filter,
            'started': self.on_server_started,
            'on_exc': self.on_server_exc,
        }

        retry_times = 0
        while True:
            if retry_times > 20:
                logger.error('retry too many times')
                return

            try:
                http_proxy.run_server(self.app_host, self.app_port, opt)
            except OSError as e:
                if e.errno == errno.WSAEADDRINUSE:
                    self.app_port += 1
                    retry_times += 1
                else:
                    raise e

    def init_backend(self):
        backend_utilitys.check()
        self.backend = Backend()

        self.backend.start()
        if self.backend.port:
            addr = f'{self.backend.host}:{self.backend.port}'
            logger.info(f'[backend] serving on {addr}...')
        else:
            logger.warning('configuration for backend not found!')

    def init_tray_icon(self):
        def on_turn_on(icon):
            if self.need_restart:
                self.handle_command('restart')
                return

            self.pac_server.update_sys_setting(True)
            self.did_enable_proxy = True
            self.update_state_icon(icon)

        def on_turn_off(icon):
            self.pac_server.update_sys_setting(False)
            self.did_enable_proxy = False
            self.update_state_icon(icon)

        def on_settings(icon):
            open_url(self.base_url + '/settings.html')

        menu_items = [
            (self.icons.play, 'Turn On', on_turn_on,
                lambda: not self.did_enable_proxy_menu),
            (self.icons.stop, 'Turn Off', on_turn_off,
                lambda: self.did_enable_proxy_menu),
            (self.icons.settings, 'Settings', on_settings),
        ]

        state_icon = self.make_state_icon()
        title = 'trayicon@' + sys.executable
        self.tray_icon = start_tray_icon_menu(
            menu_items, state_icon, APP_NAME, title)
        self.tray_icon.set_magic_handler(self.on_magic)

    @property
    def did_enable_proxy_menu(self):
        return self.did_enable_proxy and not self.need_restart

    def make_state_icon(self):
        if self.need_restart:
            return self.icons.tray_stop

        if self.did_enable_proxy:
            if self.did_allow_lan:
                return self.icons.tray_play_lan
            else:
                return self.icons.tray_play
        else:
            return self.icons.tray_stop

    def update_state_icon(self, icon=None):
        tray_icon = icon or self.tray_icon
        if tray_icon is None:
            return

        state_icon = self.make_state_icon()
        tray_icon.update(state_icon)

    def handle_command(self, command):
        icon = self.tray_icon
        if command == 'restart':
            icon.destroy()
            restart_app()
        elif command == 'exit':
            icon.destroy()
            self.pac_server.update_sys_setting(False)
            backend_utilitys.clear_all()
            exit_app()

    def on_magic(self, icon):
        text = 'Restart the program? or press [No] to quit.'
        options = MsgBox.MB_YESNOCANCEL | MsgBox.MB_DEFBUTTON3 \
            | MsgBox.MB_ICONWARNING | MsgBox.MB_SETFOREGROUND
        result = MsgBox.show(text, APP_NAME, options)
        if result == MsgBox.IDYES:
            self.handle_command('restart')
        elif result == MsgBox.IDNO:
            self.handle_command('exit')

    def run(self):
        check_singleton()

        if USER_CONF.enable_proxy is None:
            USER_CONF.enable_proxy = True

        self.init_tray_icon()
        if not ENV_NO_BACKEND:
            self.init_backend()

        check_update(self.tray_icon)
        self.start_server()
