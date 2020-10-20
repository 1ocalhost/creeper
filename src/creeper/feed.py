import re
import json
import base64
import asyncio
import urllib.request
from urllib.parse import parse_qsl, urlsplit

from creeper.env import USER_CONF
from creeper.log import logger
from creeper.utils import readable_exc


class FeedParseError(Exception):
    pass


def fetch_url_content_impl(url):
    hdr = {'User-Agent': 'Client App'}
    logger.debug(f'fetch feed: {url}')
    req = urllib.request.Request(url, headers=hdr)
    response = urllib.request.urlopen(req, timeout=10)
    return response.read().decode()


async def fetch_url_content(url):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, fetch_url_content_impl, url)


def b64_decode(data):
    if data is None:
        return None

    d = data.replace('_', '/').replace('-', '+')
    return base64.b64decode(d.strip() + '==').decode()


def split_no_empty(obj, sep):
    return list(filter(len, obj.split(sep)))


def parse_ssr_list(uri):
    ssr_scheme = 'ssr://'
    uri_b64 = split_no_empty(uri, ssr_scheme)[0]

    conf = re.split('/', b64_decode(uri_b64))
    if len(conf) == 3:
        ss_conf = ''.join(conf[:2])
        ssr_conf = conf[2]
    else:
        ss_conf = conf[0]
        ssr_conf = conf[1]

    ss_part = ss_conf.split(':', 1)
    ssr_part = parse_qsl(urlsplit(ssr_conf).query)

    return ss_part, dict(ssr_part)


def parse_ssr_item(item):
    ss, ssr = item
    ss_param = ss[1].split(':')
    port, protocol, method, obfs, password = ss_param
    decode = b64_decode

    result = {
        'server': ss[0],
        'server_port': port,
        'protocol': protocol,
        'method': method,
        'obfs': obfs,
        'password': decode(password),
        'obfs_param': decode(ssr.get('obfsparam')),
        'protocol_param': decode(ssr.get('protoparam')),
        'group': decode(ssr.get('group')),
        'remark': decode(ssr.get('remarks')),
    }

    return result


def parse_vmess_list(uri):
    ssr_scheme = 'vmess://'
    uri_b64 = split_no_empty(uri, ssr_scheme)[0]
    return json.loads(b64_decode(uri_b64))


def mark_duplicate(proxy_items, unique_keys):
    unique_items = set()

    def filter_(item):
        key = []
        for key_name in unique_keys:
            key.append(item[key_name])
        key = tuple(key)

        is_duplicate = key in unique_items
        unique_items.add(key)
        return {
            **item,
            'duplicate': is_duplicate,
        }

    return list(map(filter_, proxy_items))


def parse_feed_data(feed):
    all_lines = split_no_empty(b64_decode(feed), '\n')

    if not len(all_lines):
        return {}

    scheme = split_no_empty(all_lines[0], '://')[0]

    if scheme == 'ssr':
        proxy_items = list(map(parse_ssr_list, all_lines))
        proxy_items = list(map(parse_ssr_item, proxy_items))
        unique_keys = ['server', 'server_port']
    elif scheme == 'vmess':
        proxy_items = list(map(parse_vmess_list, all_lines))
        unique_keys = ['add', 'port', 'net', 'host', 'path']
    else:
        raise ValueError(f'unsupported scheme: {scheme}')

    proxy_items = mark_duplicate(proxy_items, unique_keys)
    return {
        'scheme': scheme,
        'proxies': proxy_items
    }


class NoFeedURL(Exception):
    pass


async def fetch_feed():
    if not USER_CONF.feed_url:
        raise NoFeedURL()

    content = await fetch_url_content(USER_CONF.feed_url)
    try:
        return parse_feed_data(content)
    except Exception as exc:
        logger.error(readable_exc(exc))
        raise FeedParseError()
