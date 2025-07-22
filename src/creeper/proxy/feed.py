import re
import uuid
import time
import json
import httpx
import base64
from urllib.parse import parse_qsl, urlsplit, unquote
from types import SimpleNamespace

from creeper.env import CONF_DIR, FILE_FEED_JSON
from creeper.log import logger
from creeper.utils import AttrDict, _MiB, \
    readable_exc, write_json_file, fix_proxy_url

FEED_FILE_PATH = CONF_DIR / FILE_FEED_JSON


class FeedParseError(Exception):
    pass


class EmptyResponse(Exception):
    pass


def parse_query(query):
    params = {}

    for key, value in parse_qsl(query):
        if key not in params:
            params[key] = value

    return params


async def fetch_url_content(url, proxy):
    logger.debug(f'fetch feed: {url}')
    headers = {'User-Agent': 'Creeper'}

    async with httpx.AsyncClient(
            proxy=proxy,
            timeout=10,
            follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        return r.text


def b64_decode(data):
    if data is None:
        return None

    d = data.replace('_', '/').replace('-', '+')
    return base64.b64decode(d.strip() + '==').decode()


def split_no_empty(obj, sep):
    return list(filter(len, obj.split(sep)))


def parse_ss_uri(uri):
    splited = urlsplit(uri)
    extra, host = splited.netloc.split('@')
    method, password = b64_decode(extra).split(':')
    server, port = host.split(':')
    remark = unquote(splited.fragment)

    meta = SimpleNamespace(
        name=remark,
        server=server,
        port=port,
        extra='')

    conf = {
        'server': server,
        'server_port': port,
        'method': method,
        'password': password,
        'remark': remark,
    }

    return meta, conf


def parse_trojan_uri(uri):
    splited = urlsplit(uri)
    password, host = splited.netloc.split('@')
    server, port = host.split(':')
    remark = unquote(splited.fragment)
    params = parse_query(splited.query)

    meta = SimpleNamespace(
        name=remark,
        server=server,
        port=port,
        extra='')

    conf = {
        'server': server,
        'server_port': int(port),
        'password': password,
        'sni': params['sni'],
        'remark': remark,
    }

    return meta, conf


def parse_ssr_uri_base(uri):
    uri_b64 = split_no_empty(uri, 'ssr://')[0]
    conf = re.split('/', b64_decode(uri_b64))

    if len(conf) == 3:
        ss_conf = ''.join(conf[:2])
        ssr_conf = conf[2]
    else:
        ss_conf = conf[0]
        ssr_conf = conf[1]

    ss = ss_conf.split(':', 1)
    ssr = parse_qsl(urlsplit(ssr_conf).query)
    return ss, dict(ssr)


def parse_ssr_uri(uri):
    ss, ssr = parse_ssr_uri_base(uri)
    ss_param = ss[1].split(':')
    port, protocol, method, obfs, password = ss_param
    decode = b64_decode

    server = ss[0]
    remark = decode(ssr.get('remarks'))
    meta = SimpleNamespace(
        name=remark,
        server=server,
        port=port,
        extra='')

    conf = {
        'server': server,
        'server_port': port,
        'protocol': protocol,
        'method': method,
        'obfs': obfs,
        'password': decode(password),
        'obfs_param': decode(ssr.get('obfsparam')),
        'protocol_param': decode(ssr.get('protoparam')),
        'group': decode(ssr.get('group')),
        'remark': remark,
    }

    return meta, conf


def parse_vmess_query_uri(uri_b64):
    main, extra = uri_b64.split('?')
    main_conf, server_conf = b64_decode(main).split('@')
    security, auth_id = main_conf.split(':')
    server, port = server_conf.split(':')
    query = parse_query(extra)

    obfs = query['obfs']
    if obfs == 'websocket':
        obfs = 'ws'

    return {
        'add': server,
        'port': int(port),
        'security': security,
        'id': auth_id,
        'aid': int(query['alterId']),
        'tls': None,
        'ps': query['remarks'],
        'net': 'ws',
        'path': query['path'],
        'host': query['obfsParam']
    }


def parse_vmess_uri(uri):
    uri_b64 = split_no_empty(uri, 'vmess://')[0]
    if '?' in uri_b64:
        conf = parse_vmess_query_uri(uri_b64)
    else:
        conf = json.loads(b64_decode(uri_b64))

    c = AttrDict(conf)
    extra = f'/{c.net}/{c.host}{c.path}'
    meta = SimpleNamespace(
        name=c.ps,
        server=c.add,
        port=c.port,
        extra=extra)

    return meta, conf


def parse_feed_item(uri):
    if uri.startswith('STATUS='):
        _, info = uri.split('=', 1)
        return split_no_empty(info, '.♥.')

    parts = split_no_empty(uri, '://')
    if len(parts) == 1:
        return

    scheme = parts[0]

    if scheme == 'ss':
        parser = parse_ss_uri
    elif scheme == 'ssr':
        parser = parse_ssr_uri
    elif scheme == 'vmess':
        parser = parse_vmess_uri
    elif scheme == 'trojan':
        parser = parse_trojan_uri
    else:
        raise ValueError(f'unsupported scheme: {scheme}')

    meta, conf = parser(uri)
    uid = f'{scheme}://{meta.server}:{meta.port}{meta.extra}'

    return dict(
        scheme=scheme,
        conf=conf,
        uid=uid,
        host=meta.server,
        name=meta.name)


def parse_feed_data(feed):
    lines = split_no_empty(b64_decode(feed), '\n')
    items = map(str.strip, lines)
    items = map(parse_feed_item, items)
    items = filter(None, items)

    proxies = []
    for item in items:
        if isinstance(item, list):
            for name in item:
                proxies.append(dict(name=name))
        else:
            proxies.append(item)

    unique_items = set()

    def convert(item):
        if not item.get('scheme'):
            return item

        uid = item['uid']
        item['duplicate'] = uid in unique_items
        unique_items.add(uid)
        return item

    return list(map(convert, proxies))


def make_feed_data(url, content=None):
    if content is None:
        update = None
        proxies = []
    else:
        update = time.time()
        proxies = parse_feed_data(content)

    return {
        'uid': str(uuid.uuid4()),
        'url': url,
        'update': update,
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
