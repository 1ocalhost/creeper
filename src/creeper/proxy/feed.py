import uuid
import time
import json
import yaml
import httpx
import hashlib

from creeper.env import CONF_DIR, FILE_FEED_JSON
from creeper.log import logger
from creeper.utils import _MiB, \
    readable_exc, write_json_file, fix_proxy_url

FEED_FILE_PATH = CONF_DIR / FILE_FEED_JSON


class FeedParseError(Exception):
    pass


class EmptyResponse(Exception):
    pass


async def fetch_url_content(url, proxy):
    logger.debug(f'fetch feed: {url}')

    # Simulate popular Clash clients to retrieve accurate proxy
    # configurations and metadata like 'subscription-userinfo' as
    # effectively as possible.
    headers = {'User-Agent': 'clash-verge/2.4.6'}

    async with httpx.AsyncClient(
            proxy=proxy,
            timeout=10,
            follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        user_info = r.headers.get('subscription-userinfo')
        return user_info, r.text


def format_traffic(size_bytes):
    size_bytes = int(size_bytes)
    space = ''

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f}{space}{unit}"
        size_bytes /= 1024

    return f"{size_bytes:.2f}{space}PB"


def parse_subscription_info(info_str):
    if not info_str:
        return None

    parts = [p.strip() for p in info_str.split(';') if p.strip()]

    items = []
    for part in parts:
        key, value = part.split('=')
        if key in ('upload', 'download', 'total'):
            items.append((key, format_traffic(value)))
        elif key == 'expire':
            expire_time = time.localtime(int(value))
            expire_date = time.strftime('%Y-%m-%d', expire_time)
            items.append((key, expire_date))

    return " ".join([f"{k}={v}" for k, v in items])


def get_conf_uid(conf):
    exclude_keys = {'name', 'client-fingerprint'}
    filtered_conf = {k: v for k, v in conf.items() if k not in exclude_keys}

    json_str = json.dumps(filtered_conf, sort_keys=True, separators=(',', ':'))
    conf_hash = hashlib.sha256(json_str.encode()).hexdigest()[:8]

    return f"{conf['type']}://{conf['server']}:{conf['port']}/{conf_hash}"


def parse_feed_data(feed):
    user_info_raw, clash_conf_str = feed
    user_info = parse_subscription_info(user_info_raw)

    def to_proxy(conf):
        return {
            'scheme': conf['type'],
            'conf': conf,
            'uid': get_conf_uid(conf),
            'host': conf['server'],
            'name': conf['name']
        }

    clash_conf = yaml.safe_load(clash_conf_str)
    proxies = clash_conf['proxies']
    proxies = list(map(to_proxy, proxies))

    unique_items = set()

    def convert(item):
        uid = item['uid']
        item['duplicate'] = uid in unique_items
        unique_items.add(uid)
        return item

    proxies = list(map(convert, proxies))
    return user_info, proxies


def make_feed_data(url, content=None):
    if content is None:
        update = None
        user_info = None
        proxies = []
    else:
        update = time.time()
        user_info, proxies = parse_feed_data(content)

    return {
        'uid': str(uuid.uuid4()),
        'url': url,
        'update': update,
        'user_info': user_info,
        'proxies': proxies
    }


async def fetch_feed(feed_url, proxy):
    content = await fetch_url_content(feed_url, proxy)
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


async def update_feed(uid, proxy):
    def load_item():
        feed_list = read_feed()
        feed_item = next(feed_by_uid(feed_list, uid))
        return feed_list, feed_item

    _, feed_item = load_item()
    feed = await fetch_feed(feed_item['url'], proxy)
    feed.pop('uid', None)

    # reload and merge
    feed_list, feed_item = load_item()
    feed_item.update(**feed)

    write_feed(feed_list)
    return feed_item


async def update_feed_app(app, uid):
    proxy = app.base_url \
        if app.update_via_proxy \
        else None

    proxy = fix_proxy_url(proxy)
    return await update_feed(uid, proxy)


async def update_feed_conf(uid, **kwargs):
    feed_list = read_feed()
    feed_item = next(feed_by_uid(feed_list, uid))

    feed_item.update(**kwargs)
    write_feed(feed_list)
