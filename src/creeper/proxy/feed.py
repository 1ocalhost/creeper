import re
import uuid
import time
import json
import base64
import asyncio
import urllib.request
from urllib.parse import parse_qsl, urlsplit

from creeper.env import CONF_DIR, FILE_FEED_JSON
from creeper.log import logger
from creeper.utils import _MiB, readable_exc, write_json_file, open_url

FEED_FILE_PATH = CONF_DIR / FILE_FEED_JSON


class FeedParseError(Exception):
    pass


class EmptyResponse(Exception):
    pass


def fetch_url_content_impl(url):
    hdr = {'User-Agent': 'Client App'}
    logger.debug(f'fetch feed: {url}')
    req = urllib.request.Request(url, headers=hdr)
    response = open_url(req, None, timeout=10)
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
            key.append(item.get(key_name))
        key = tuple(key)

        is_duplicate = key in unique_items
        unique_items.add(key)
        return {
            'duplicate': is_duplicate,
            'conf': item,
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
    return scheme, proxy_items


def make_feed_data(url, content=None):
    if content is None:
        scheme, proxy_items = None, []
    else:
        scheme, proxy_items = parse_feed_data(content)

    update = time.time() if scheme else None
    return {
        'uid': str(uuid.uuid4()),
        'url': url,
        'update': update,
        'scheme': scheme,
        'proxies': proxy_items
    }


async def fetch_feed(feed_url):
    content = await fetch_url_content(feed_url)
    if not content:
        raise EmptyResponse(feed_url)

    try:
        return make_feed_data(feed_url, content)
    except Exception as exc:
        logger.error(readable_exc(exc))
        raise FeedParseError(feed_url)


def read_feed():
    try:
        with open(FEED_FILE_PATH) as file:
            data = file.read(_MiB)
        return json.loads(data)
    except FileNotFoundError as exc:
        logger.warning(readable_exc(exc))
        return []


def write_feed(feed_list):
    write_json_file(FEED_FILE_PATH, feed_list)


def find_feed_by(feed_list, key, value):
    return (x for x in feed_list if x[key] == value)


def feed_by_uid(feed_list, uid):
    return find_feed_by(feed_list, 'uid', uid)


def feed_by_url(feed_list, url):
    return find_feed_by(feed_list, 'url', url)


def add_feed(url):
    feed_list = read_feed()
    existing = next(feed_by_url(feed_list, url), None)
    if existing:
        return None

    new_feed = make_feed_data(url)
    feed_list.append(new_feed)
    write_feed(feed_list)
    return new_feed


def delete_feed(uid):
    feed_list = read_feed()
    existing = False

    for item in feed_by_uid(feed_list, uid):
        feed_list.remove(item)
        existing = True

    if existing:
        write_feed(feed_list)


def edit_feed(uid, url):
    feed_list = read_feed()
    existing = False

    for item in feed_by_uid(feed_list, uid):
        item['url'] = url
        existing = True
        break

    if not existing:
        raise Exception('feed not found')

    write_feed(feed_list)


async def update_feed(uid):
    feed_list = read_feed()
    feed_item = next(feed_by_uid(feed_list, uid))

    feed = await fetch_feed(feed_item['url'])
    feed.pop('uid', None)
    feed_item.update(**feed)

    write_feed(feed_list)
    return feed_item


async def update_feed_conf(uid, **kwargs):
    feed_list = read_feed()
    feed_item = next(feed_by_uid(feed_list, uid))

    feed_item.update(**kwargs)
    write_feed(feed_list)
