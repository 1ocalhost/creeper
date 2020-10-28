import errno
import asyncio
import webbrowser
import aiosocks

from creeper import statistic
from creeper.utils import check_singleton
from creeper.impl import http_proxy
from creeper.env import ICON_DIR, PATH_CNIP_DB, \
    APP_NAME, USER_CONF, ENV_NO_BACKEND
from creeper.log import logger
from creeper.router import Router
from creeper.pac import PACServer
from creeper.backend import backend_utilitys, Backend
from creeper.http_api import get_api_filter
from creeper.update import check_update
from creeper.impl.win_tray_icon import start_tray_icon_menu


class AppIcons:
    def __init__(self):
        icons_dir = ICON_DIR
        self.play = icons_dir / 'play.ico'
        self.stop = icons_dir / 'stop.ico'
        self.help = icons_dir / 'help.ico'
        self.tray_play = icons_dir / 'tray_play.ico'
        self.tray_play_lan = icons_dir / 'tray_play_lan.ico'
        self.tray_stop = icons_dir / 'tray_stop.ico'


class App:
    def __init__(self):
        host_ip = '0.0.0.0' if USER_CONF.allow_lan else '127.0.0.1'
        self.icons = AppIcons()
        self.tray_icon = None
        self.app_host = host_ip
        self.app_port = 1080
        self.router = Router(PATH_CNIP_DB)
        self.pac_server = PACServer(self)
        self.backend = None

    @property
    def did_allow_lan(self):
        return USER_CONF.allow_lan

    @property
    def did_enable_proxy(self):
        return USER_CONF.enable_proxy

    @did_enable_proxy.setter
    def did_enable_proxy(self, value):
        USER_CONF.enable_proxy = value

    def base_url(self):
        return f'http://127.0.0.1:{self.app_port}'

    async def is_connect_direct(self, host):
        if not self.did_enable_proxy:
            return True, host

        if not self.backend or not self.backend.port:
            return True, host

        return await self.router.is_direct(host)

    async def on_open_conn(self, host, port):
        is_direct, remote = await self.is_connect_direct(host)
        if is_direct is None:
            statistic.on_route('UNREACHABLE', host)
            return

        backend_port = self.backend.port if self.backend else None
        if is_direct or backend_port is None:
            statistic.on_route('DIRECT', host, remote)
            connection = await asyncio.open_connection(remote, port)
        else:
            backend = aiosocks.Socks5Addr('127.0.0.1', backend_port)
            statistic.on_route('PROXY', host, remote)
            dst = (host, port)  # Use domain-name to avoid DNS cache pollution
            connection = await aiosocks.open_connection(
                proxy=backend, proxy_auth=None,
                dst=dst, remote_resolve=True)

        def statistic_(is_out, bytes_):
            statistic.on_transfer(not is_direct, is_out, bytes_)

        return connection, statistic_

    def on_server_started(self, addr):
        host, port = addr
        logger.info(f'serving on: {host}:{port}')
        self.tray_icon.update(hover_text=f'{APP_NAME} ({port})')

        if not self.pac_server.update_sys_setting(True):
            logger.error('update pac setting')

    def start_server(self):
        http_filter = get_api_filter(self)
        opt = {
            'open_conn': self.on_open_conn,
            'req_filter': http_filter,
            'started': self.on_server_started,
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
            logger.info(f'[backend] serving on {self.backend.port}...')
        else:
            logger.warning(f'configuration for backend not found!')

    def init_tray_icon(self):
        def on_turn_on(icon):
            self.pac_server.update_sys_setting(True)
            self.did_enable_proxy = True
            self.update_state_icon(icon)

        def on_turn_off(icon):
            self.pac_server.update_sys_setting(False)
            self.did_enable_proxy = False
            self.update_state_icon(icon)

        def on_help(icon):
            webbrowser.open(self.base_url() + '/help.html')

        def on_magic(icon):
            webbrowser.open(self.base_url() + '/settings.html')

        menu_items = [
            (self.icons.play, 'Turn On', on_turn_on,
                lambda: not self.did_enable_proxy),
            (self.icons.stop, 'Turn Off', on_turn_off,
                lambda: self.did_enable_proxy),
            (self.icons.help, 'Help', on_help),
        ]

        state_icon = self.make_state_icon()
        self.tray_icon = start_tray_icon_menu(
            menu_items, state_icon, APP_NAME)
        self.tray_icon.set_magic_handler(on_magic)

    def make_state_icon(self):
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

    def run(self):
        check_singleton()

        if USER_CONF.enable_proxy is None:
            USER_CONF.enable_proxy = True

        self.init_tray_icon()
        if not ENV_NO_BACKEND:
            self.init_backend()

        check_update(self.tray_icon)
        self.start_server()
