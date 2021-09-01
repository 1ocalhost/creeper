import time
import json
import socks
import asyncio
import traceback
import os.path
import tempfile
import urllib.request as request
from urllib.parse import urlparse
from datetime import timedelta
from pathlib import Path

from sockshandler import SocksiPyHandler
from creeper.env import MAIN_DIR

_KiB = 1024 * 1
_MiB = 1024 * _KiB


def hour_to_sec(h):
    return timedelta(hours=h).total_seconds()


def fmt_exc(exc):
    return f'{type(exc).__name__}: "{exc}"'


_src_dir_str = str(MAIN_DIR)
_own_src_file_path = {}


def is_own_src_file(path):
    result = _own_src_file_path.get(path)
    if result is not None:
        return result

    real_path = Path(path).resolve()
    result = str(real_path).startswith(_src_dir_str)
    _own_src_file_path[path] = result
    return result


def exc_src(exc):
    info = ''
    frames = traceback.extract_tb(exc.__traceback__)
    f = frames[-1]
    info += f'at {f.filename}:{f.lineno}'

    if is_own_src_file(f.filename):
        return info

    for f in reversed(frames[:-1]):
        if is_own_src_file(f.filename):
            info += f', from {f.filename}:{f.lineno}'
            break

    return info


def readable_exc(exc):
    return f'<{fmt_exc(exc)}> {exc_src(exc)}'


def human_readable_size(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            fmt = "%.1f" if unit else "%.0f"
            return (fmt + "%s%s") % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


async def write_drain(writer, data):
    writer.write(data)
    await writer.drain()


def split_no_empty(str, sep):
    return filter(len, str.split(sep))


def run_async(*tasks):
    future = asyncio.gather(*tasks)
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(future)
    return results


def now():
    return time.time()


def check_singleton():
    import __main__
    app_path = os.path.abspath(__main__.__file__)
    separator = '^'
    lock_name = app_path.lower().replace('\\', separator) \
        .replace('/', separator).replace(':', '') + '.lock'
    lock_file = Path(tempfile.gettempdir()) / lock_name
    lock_file = str(lock_file)

    try:
        if os.path.exists(lock_file):
            os.unlink(lock_file)
        os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except OSError:
        raise


def write_json_file(file_, obj):
    with open(file_, 'w') as f:
        f.write(json.dumps(obj, indent=4))


class AttrDict(dict):
    __slots__ = ()
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def parse_host_port(netloc):
    tokens = netloc.split(':')
    if len(tokens) >= 2:
        port = int(tokens[1])
    else:
        port = 0

    return tokens[0], port


def make_proxy_handler(proxy_url=None):
    if not proxy_url:
        return

    url = urlparse(proxy_url)
    host, port = parse_host_port(url.netloc)

    if (url.scheme == 'http'):
        type_ = socks.HTTP
    elif (url.scheme == 'socks4'):
        type_ = socks.SOCKS4
    elif (url.scheme == 'socks5'):
        type_ = socks.SOCKS5
    else:
        type_ = None

    if type_ is None:
        if proxy_url is not None:
            raise ValueError('bad proxy URL')
    else:
        if not port:
            port = socks.DEFAULT_PORTS[type_]

    if type_ is not None:
        return SocksiPyHandler(type_, host, port)


def open_url(url, proxy_url=None, **kwargs):
    skip_system_proxy = request.ProxyHandler({})
    handlers = [skip_system_proxy]

    proxy_handler = make_proxy_handler(proxy_url)
    if proxy_handler is not None:
        handlers.append(proxy_handler)

    opener = request.build_opener(*handlers)
    return opener.open(url, **kwargs)
