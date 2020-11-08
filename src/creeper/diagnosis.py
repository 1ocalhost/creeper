import string
from urllib.parse import urlparse

from creeper.log import logger
from creeper.utils import readable_exc, fmt_exc, AttrDict
from creeper.feed import update_feed, read_feed
from creeper.measure import test_download_speed, test_backend_speed
from creeper.backend import backend_utilitys

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


async def _switch_node(backend, results):
    def get_key(item):
        speed = item[1]['average_dl_speed']
        NUM_CHARS = string.digits + '.'
        speed_num_char = [x for x in speed if x in NUM_CHARS]
        speed = float(''.join(speed_num_char))
        return speed

    conf, speed = max(results, key=get_key)
    logger.info(f'switch node: {speed} - {conf}')
    await backend_utilitys.restart(backend, conf)


async def _test_nodes_speed(backend, nodes_data):
    scheme = nodes_data['scheme']
    proxies = nodes_data['proxies']
    results = []

    for i, item in enumerate(proxies, 1):
        conf = AttrDict({
            'type': scheme,
            'uid': None,
            'data': item,
        })
        yield f'Test node {i}/{len(proxies)}... '
        try:
            new_item = await test_backend_speed(conf)
            result = new_item['result']
            results.append((conf, result))
            speed = result['average_dl_speed']
            yield f'{speed}\n'
        except Exception as exc:
            logger.error(f'with node {i}, {readable_exc(exc)}')
            yield f'Failed\n'

    if not len(results):
        raise Exception('No nodes available to use')

    await _switch_node(backend, results)
    yield ['ok']


async def _update_subscription(backend):
    try:
        new_feed = await update_feed()
    except Exception as exc:
        exc_type = type(exc).__name__
        yield f'Can not update subscription. ({exc_type})\n'
        new_feed = read_feed()

    assert new_feed
    yield f'Test the speed of nodes...\n'
    nodes_data = new_feed['servers']
    async for v in _test_nodes_speed(backend, nodes_data):
        yield v


async def _diagnosis_network_impl(backend):
    yield f'Test local network...\n'
    async for v in _test_local_network():
        yield v

    yield f'Try update subscription...\n'
    async for v in _update_subscription(backend):
        yield v


async def diagnosis_network(backend):
    global singleton_running
    if singleton_running:
        yield 'Another diagnosis is in progress.'
        return

    singleton_running = True
    try:
        async for v in _diagnosis_network_impl(backend):
            yield v
    except Exception as exc:
        yield f'Sorry, {fmt_exc(exc)}\n'
    finally:
        singleton_running = False
