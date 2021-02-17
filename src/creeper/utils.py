import time
import json
import asyncio
import traceback
import os.path
import tempfile
from datetime import timedelta
from pathlib import Path

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
