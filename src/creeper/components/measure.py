import json
import httpx
from types import SimpleNamespace

from creeper.utils import _MiB, now, fmt_exc
from creeper.env import CONF_DIR, APP_CONF, FILE_SPEED_JSON
from creeper.proxy.backend import Backend


class SpeedTest:
    MAX_DOWNLOAD_SIZE = 15 * _MiB

    def __init__(self, url, proxy):
        self.url = url
        self.proxy = proxy
        self.start_time = 0
        self.start_dl_time = 0
        self.total_dl_size = 0
        self.dl_end_time = 0

    def _append_dl_data(self, data):
        self.total_dl_size += len(data)
        self.dl_end_time = now()

    async def run_impl(self, client):
        started_download = False
        timeout = httpx.Timeout(2, read=1)

        async with client.stream(
                'GET', self.url, timeout=timeout) as response:
            end_time = now() + 2.5
            async for chunk in response.aiter_bytes():
                if now() > end_time:
                    break

                if not started_download:
                    self.start_dl_time = now()
                    started_download = True

                self._append_dl_data(chunk)
                if self.total_dl_size >= self.MAX_DOWNLOAD_SIZE:
                    break

    async def run(self):
        self.start_time = now()

        async with httpx.AsyncClient(proxy=self.proxy) as client:
            try:
                await self.run_impl(client)
            except httpx.TimeoutException:
                pass

        if self.total_dl_size <= 0:
            raise TimeoutError

        return self.calc()

    @staticmethod
    def _calc_speed(size, time):
        if time > 0:
            return size / time / _MiB
        else:
            return float('inf')

    def calc(self):
        connection_time = self.start_dl_time - self.start_time
        download_time = self.dl_end_time - self.start_dl_time
        total_time = connection_time + download_time

        download_speed = self._calc_speed(self.total_dl_size, download_time)
        average_dl_speed = self._calc_speed(self.total_dl_size, total_time)

        return SimpleNamespace(
            connection_time='%.2fs' % connection_time,
            download_speed='%.2fMiB/s' % download_speed,
            average_dl_speed='%.2fMiB/s' % average_dl_speed,
        )


def update_speed_cache(server_uid, result):
    new_item = {
        'update': now(),
    }

    if isinstance(result, Exception):
        new_item['error'] = fmt_exc(result)
    else:
        new_item['result'] = result.__dict__

    if not server_uid:
        return new_item

    speed_file_path = CONF_DIR / FILE_SPEED_JSON
    try:
        with open(speed_file_path) as f:
            speed_data = json.loads(f.read())
    except FileNotFoundError:
        speed_data = {}

    def get_key(item):
        return item[1]['update']

    speed_data[server_uid] = new_item
    speed_data = sorted(speed_data.items(), key=get_key)
    speed_data = dict(speed_data[:500])

    new_content = json.dumps(speed_data, indent=4)
    with open(speed_file_path, 'w') as f:
        f.write(new_content)

    return new_item


async def test_backend_speed(conf):
    with Backend() as backend:
        await backend.start_async(conf, timeout=3)
        if backend.port is None:
            raise Exception('failed to start backend')

        url = APP_CONF['measure_url']
        proxy = f'socks5h://{backend.host}:{backend.port}'

        try:
            result = await SpeedTest(url, proxy).run()
        except Exception as exc:
            update_speed_cache(conf.uid, exc)
            raise

        return update_speed_cache(conf.uid, result)
