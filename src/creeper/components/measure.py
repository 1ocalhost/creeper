import asyncio
import json
import multiprocessing.dummy as multiprocessing
from types import SimpleNamespace

from creeper.utils import _KiB, _MiB, now, fmt_exc, open_url
from creeper.env import CONF_DIR, APP_CONF, FILE_SPEED_JSON
from creeper.proxy.backend import Backend


class CancellablePool:
    def __init__(self, max_workers=3):
        self._free = {self._new_pool() for _ in range(max_workers)}
        self._working = set()
        self._change = asyncio.Event()

    def _new_pool(self):
        return multiprocessing.Pool(1)

    async def apply(self, fn, *args):
        """
        Like multiprocessing.Pool.apply_async, but:
         * is an asyncio coroutine
         * terminates the process if cancelled
        """
        while not self._free:
            await self._change.wait()
            self._change.clear()
        pool = usable_pool = self._free.pop()
        self._working.add(pool)

        loop = asyncio.get_event_loop()
        fut = loop.create_future()

        def _on_done(obj):
            loop.call_soon_threadsafe(fut.set_result, obj)

        def _on_err(err):
            loop.call_soon_threadsafe(fut.set_exception, err)
        pool.apply_async(fn, args, callback=_on_done, error_callback=_on_err)

        try:
            return await fut
        except asyncio.CancelledError:
            pool.terminate()
            usable_pool = self._new_pool()
        finally:
            self._working.remove(pool)
            self._free.add(usable_pool)
            self._change.set()

    def shutdown(self):
        for p in self._working | self._free:
            p.terminate()
        self._free.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


class SpeedTest:
    MAX_DOWNLOAD_SIZE = 15 * _MiB
    READ_SIZE = 10 * _KiB

    def __init__(self, url, proxy):
        self.url = url
        self.proxy = proxy
        self.page = None

        manager = multiprocessing.Manager()
        shared = manager.Namespace()
        shared.start_time = 0
        shared.start_dl_time = 0
        shared.total_dl_size = 0
        shared.dl_end_time = 0
        self.shared = shared

    def _append_dl_data(self, data):
        shared = self.shared
        shared.total_dl_size += len(data)
        shared.dl_end_time = now()

    def connect(self):
        shared = self.shared
        shared.start_time = now()

        self.page = open_url(self.url, self.proxy)
        data = self.page.read(1)
        shared.start_dl_time = now()
        self._append_dl_data(data)

    def download(self):
        shared = self.shared
        if not self.page:
            return

        while True:
            data = self.page.read(self.READ_SIZE)
            if not data:
                break

            self._append_dl_data(data)
            if shared.total_dl_size > self.MAX_DOWNLOAD_SIZE:
                break

    @staticmethod
    def _calc_speed(size, time):
        if time > 0:
            return size / time / _MiB
        else:
            return float('inf')

    def calc(self):
        shared = self.shared
        connection_time = shared.start_dl_time - shared.start_time
        download_time = shared.dl_end_time - shared.start_dl_time
        total_time = connection_time + download_time

        download_speed = self._calc_speed(shared.total_dl_size, download_time)
        average_dl_speed = self._calc_speed(shared.total_dl_size, total_time)

        return SimpleNamespace(
            connection_time='%.2fs' % connection_time,
            download_speed='%.2fMiB/s' % download_speed,
            average_dl_speed='%.2fMiB/s' % average_dl_speed,
        )


async def test_download_speed(url, proxy=None):
    with CancellablePool(1) as pool:
        loop = asyncio.get_event_loop()
        speed_test = SpeedTest(url, proxy)
        connect = loop.create_task(pool.apply(speed_test.connect))

        await asyncio.wait_for(connect, 2.5)
        download = loop.create_task(pool.apply(speed_test.download))
        try:
            await asyncio.wait_for(download, 2.5)
        except asyncio.TimeoutError:
            pass

        return speed_test.calc()


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
        proxy = f'socks5://{backend.host}:{backend.port}'

        try:
            result = await test_download_speed(url, proxy)
        except Exception as exc:
            update_speed_cache(conf.uid, exc)
            raise

        return update_speed_cache(conf.uid, result)
