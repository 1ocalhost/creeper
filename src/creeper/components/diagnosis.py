import string
from urllib.parse import urlparse

from creeper.log import logger
from creeper.utils import readable_exc, fmt_exc, AttrDict
from creeper.components.measure import test_download_speed, test_backend_speed
from creeper.proxy.feed import update_feed, read_feed
from creeper.proxy.backend import backend_utilitys

singleton_running = False


async def _test_local_network():
    home_urls = [
        'https://www.baidu.com',
        'https://www.taobao.com',
        'https://www.qq.com',
    ]

    for url in home_urls:
        host = urlparse(url).netloc
        yield f'{host}... '
        try:
            result = await test_download_speed(url)
            r = result
            yield f'[{r.connection_time}]\n'
            return
        except Exception as exc:
            yield f'Failed: {fmt_exc(exc)}\n'
    raise Exception('Your local network has a few problems')


def _parse_speed_text(text):
    NUM_CHARS = string.digits + '.'
    speed_num_char = [x for x in text if x in NUM_CHARS]
    return float(''.join(speed_num_char))


async def _test_nodes_speed_once(build_conf, results):
    for i, item in enumerate(results, 1):
        conf = build_conf(item[0])
        yield f'Test node {i}/{len(results)}... '

        try:
            new_item = await test_backend_speed(conf)
            result = new_item['result']
            speed_text = result['average_dl_speed']
            speed_num = _parse_speed_text(speed_text)
            yield f'{speed_text}\n'
        except Exception as exc:
            logger.error(f'with node {i}, {readable_exc(exc)}')
            speed_num = 0.0
            yield f'Failed\n'

        item[1].append(speed_num)


def _get_speed_result_key(item):
    return sum(item[1])


def _select_half_fast_nodes(items):
    result = list(sorted(items, key=_get_speed_result_key))
    return result[len(result)//2:]


async def _test_nodes_speed(app, nodes_data):
    scheme = nodes_data['scheme']
    proxies = nodes_data['proxies']

    def build_conf(item):
        return AttrDict({
            'type': scheme,
            'uid': None,
            'data': item,
        })

    results = [(p, []) for p in proxies]
    async for v in _test_nodes_speed_once(build_conf, results):
        yield v

    if not len(results):
        raise Exception('No nodes available to use')

    for i in range(2):
        results = _select_half_fast_nodes(results)
        if len(results) == 1:
            break
        async for v in _test_nodes_speed_once(build_conf, results):
            yield v

    proxy, speed = max(results, key=_get_speed_result_key)
    cur_conf = build_conf(proxy)

    logger.info(f'switch node: {speed} - {cur_conf}')
    await backend_utilitys.restart(app.backend, cur_conf)
    app.pac_server.update_sys_setting(True)
    yield ['ok']


async def _update_subscription(app):
    try:
        new_feed = await update_feed()
    except Exception as exc:
        exc_type = type(exc).__name__
        yield f'Can not update subscription. ({exc_type})\n'
        new_feed = read_feed()

    assert new_feed
    yield f'Test the speed of nodes...\n'
    nodes_data = new_feed['servers']
    async for v in _test_nodes_speed(app, nodes_data):
        yield v


async def _diagnosis_network_impl(app):
    yield f'Test local network...\n'
    async for v in _test_local_network():
        yield v

    yield f'Try update subscription...\n'
    async for v in _update_subscription(app):
        yield v


async def diagnosis_network(app):
    global singleton_running
    if singleton_running:
        yield 'Another diagnosis is in progress.'
        return

    singleton_running = True
    try:
        async for v in _diagnosis_network_impl(app):
            yield v
    except Exception as exc:
        yield f'Sorry, {fmt_exc(exc)}\n'
    finally:
        singleton_running = False
