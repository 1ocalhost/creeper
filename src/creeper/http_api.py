import os
import json
import time
import asyncio
import hashlib
import base64
import binascii
import struct
import dataclasses

from types import SimpleNamespace
from ipaddress import ip_address
from urllib.parse import urlsplit, parse_qs

from creeper.log import logger
from creeper.env import IS_DEBUG, CONF_DIR, HTML_DIR, USER_CONF, \
    FILE_FEED_JSON, FILE_SPEED_JSON, FILE_CUR_NODE_JSON
from creeper.utils import write_drain, fmt_exc, readable_exc, AttrDict
from creeper.proxy.feed import add_feed, delete_feed, edit_feed, update_feed
from creeper.proxy.backend import backend_utilitys
from creeper.components import statistic
from creeper.components.measure import test_backend_speed
from creeper.components.diagnosis import diagnosis_network

MIME_HTML = 'text/html'
MIME_JSON = 'application/json'
MIME_ICON = 'image/x-icon'

CONF_DATA_FILES = [
    FILE_FEED_JSON,
    FILE_SPEED_JSON,
    FILE_CUR_NODE_JSON,
]


class ChunkedWriter:
    def __init__(self, req):
        self.writer = req.writer

    async def begin(self):
        headers = [f'Transfer-Encoding: chunked']
        await write_http_response(
            self.writer, None, 200, MIME_HTML, headers)

    async def write(self, data=''):
        data = data.encode()
        chunk = ('%x' % len(data)).encode()
        chunk += b'\r\n'
        chunk += data
        chunk += b'\r\n'
        await write_drain(self.writer, chunk)

    async def end(self):
        await self.write()


def make_random_token(len=24):
    return binascii.hexlify(os.urandom(24)).decode()


CSRF_TOKEN = make_random_token()


def make_http_status(status):
    items = {
        101: 'Switching Protocols',
        200: 'OK',
        400: 'Bad Request',
        403: 'Forbidden',
        404: 'Not Found',
        500: 'Internal Server Error',
    }

    return str(status) + ' ' + items.get(status)


async def write_http_response(
        writer, body=None, status=200, mime=MIME_HTML, headers=[]):
    all_headers = ['HTTP/1.1 ' + make_http_status(status)]
    if mime:
        all_headers.append(f'Content-Type: {mime}')

    if body is None:
        body = b''
    else:
        all_headers.append(f'Content-Length: {len(body)}')

    all_headers += headers
    all_headers.append('\r\n')

    response = '\r\n'.join(all_headers).encode()
    if isinstance(body, str):
        body = body.encode()
    response += body
    await write_drain(writer, response)


async def api_result_ok(writer, obj):
    body = json.dumps(obj)
    await write_http_response(writer, body, 200, MIME_JSON)


async def api_result_err(writer, msg, code=400):
    body = json.dumps({'error': msg})
    await write_http_response(writer, body, code, MIME_JSON)


async def api_result_exc(writer, exc, code=500):
    logger.error(f'HTTP {code}: {readable_exc(exc)}')
    await api_result_err(writer, fmt_exc(exc), code)


def parse_http_raw_header(header):
    header_str = header.decode()
    lines = header_str.split('\r\n')
    method = lines[0].split(' ')[0]

    header_items = {}
    for item in lines[1:]:
        tokens = item.split(':', 1)
        if len(tokens) == 1:
            key, value = tokens + ['']
        else:
            key, value = tokens

        key = key.lower()
        new_value = header_items.get(key, '')
        if new_value:
            new_value += '; '
        new_value += value.strip()
        header_items[key] = new_value

    return method.upper(), header_items


async def web_socket_accept(headers, writer):
    websocket_key = headers.get('sec-websocket-key')
    if not websocket_key:
        logger.warning('no sec-websocket-key')
        raise

    def accept(key):
        GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        sha1 = hashlib.sha1((key + GUID).encode()).digest()
        return base64.b64encode(sha1).decode()

    headers = [
        'Upgrade: websocket',
        'Connection: Upgrade',
        'Sec-WebSocket-Accept: ' + accept(websocket_key),
    ]

    await write_http_response(writer, None, 101, None, headers)


async def web_socket_send(writer, text):
    def framing(text):
        data = struct.pack('B', 129)
        text_len = len(text)
        if text_len <= 125:
            data += struct.pack('B', text_len)
        elif text_len <= (2 ** 16 - 1):
            data += struct.pack('!BH', 126, text_len)
        else:
            data += struct.pack('!BQ', 127, text_len)

        data += text.encode()
        return data

    await write_drain(writer, framing(text))


async def stream_api_transfer(writer):
    while True:
        data = statistic.transfer
        data_json = json.dumps(dataclasses.asdict(data))
        await web_socket_send(writer, data_json)
        await asyncio.sleep(1)


async def stream_api_route(writer):
    time_ = time.time()
    while True:
        res = statistic.fetch_route_event(time_)
        if res:
            event, current = res
            time_ = current
            data_json = json.dumps(event)
            await web_socket_send(writer, data_json)

        await asyncio.sleep(0.5)


async def route_stream(query, headers, writer):
    args = parse_qs(query)
    type_ = args.get('type')
    if type_:
        type_ = type_[0]

    api_providers = {
        'transfer': stream_api_transfer,
        'route': stream_api_route,
    }

    if type_ in api_providers:
        await web_socket_accept(headers, writer)
        await api_providers[type_](writer)
    else:
        body = f'type="{type_}"'
        await write_http_response(writer, body, 400)


def suffix_to_mime(file_name):
    unknown_mime = 'application/octet-stream'
    mime_table = {
        'html': MIME_HTML,
        'json': MIME_JSON,
        'ico': MIME_ICON,
    }

    tokens = file_name.split('.')
    if len(tokens) == 1:
        return unknown_mime

    extension = tokens[-1].lower()
    return mime_table.get(extension, unknown_mime)


async def try_read_file(writer, api_path):
    api_path_ = api_path[1:]
    if api_path_ == '':
        api_path_ += 'index.html'

    if -1 != api_path_.find('../'):
        await api_result_err(writer, 'unsafe path', 403)
        return

    if api_path_ in CONF_DATA_FILES:
        html_dir = CONF_DIR
    else:
        html_dir = HTML_DIR

    file_path = html_dir / api_path_
    if not file_path.is_file():
        await api_result_err(writer, 'not found', 404)
        return

    file_size = os.path.getsize(file_path)
    if file_size > (1024 * 1024 * 50):
        await api_result_err(writer, 'file too big', 400)
        return

    with open(file_path, "rb") as file:
        file_data = file.read()

    mime = suffix_to_mime(file_path.name)
    await write_http_response(writer, file_data, 200, mime)


class HttpBadRequest(Exception):
    pass


async def _read_json_body_impl(reader, headers, writer):
    try:
        content_length = int(headers['content-length'])
        body = await reader.read(content_length)
        return json.loads(body)
    except Exception as exc:
        raise HttpBadRequest(exc)


async def read_json_body(req):
    return await _read_json_body_impl(
        req.reader, req.headers, req.writer)


class ApiHandlerArgs(SimpleNamespace):
    async def result_ok(self, dict_):
        await api_result_ok(self.writer, dict_)


class ApiHandler:
    def __init__(self, app):
        self.app = app
        self.pac_path = app.pac_server.api_path()
        self.route_table = {}
        self._init_router_table()

    def _init_router_table(self):
        self.route('GET ', self.pac_path, self.get_pac_script)
        self.route('GET ', '/api/token', self.api_token)
        self.route('GET ', '/api/stream', self.api_stream)
        self.route('POST', '/api/add_feed', self.api_add_feed)
        self.route('POST', '/api/delete_feed', self.api_delete_feed)
        self.route('POST', '/api/edit_feed', self.api_edit_feed)
        self.route('POST', '/api/update_feed', self.api_update_feed)
        self.route('POST', '/api/test_speed', self.api_test_speed)
        self.route('POST', '/api/switch_node', self.api_switch_node)
        self.route('GET ', '/api/user_settings', self.api_get_settings)
        self.route('POST', '/api/user_settings', self.api_set_settings)
        self.route('GET ', '/api/diagnosis', self.api_diagnosis)

    def route(self, method, path, func):
        method_ = method.strip().upper()
        self.route_table[(method_, path)] = func

    async def get_pac_script(self, req):
        host = req.headers.get('host')
        if not host:
            sock = req.writer.get_extra_info('sockname')
            host = f'{sock[0]}:{sock[1]}'

        mime, body = self.app.pac_server.get_script(host)
        await write_http_response(req.writer, body, 200, mime)

    async def api_token(self, req):
        await req.result_ok({'token': CSRF_TOKEN})

    async def api_stream(self, req):
        await route_stream(req.url.query, req.headers, req.writer)

    async def api_add_feed(self, req):
        conf = await read_json_body(req)
        result = add_feed(conf['url'])
        if result is None:
            existing, feed = True, {}
        else:
            existing, feed = False, result
        await req.result_ok({
            'existing': existing,
            'feed': feed,
        })

    async def api_delete_feed(self, req):
        conf = await read_json_body(req)
        delete_feed(conf['uid'])
        await req.result_ok(conf)

    async def api_edit_feed(self, req):
        conf = await read_json_body(req)
        edit_feed(conf['uid'], conf['url'])
        await req.result_ok(conf)

    async def api_update_feed(self, req):
        conf = await read_json_body(req)
        new_feed = await update_feed(conf['uid'])
        await req.result_ok(new_feed)

    async def api_test_speed(self, req):
        conf = await read_json_body(req)
        result = await test_backend_speed(AttrDict(conf))
        await req.result_ok(result)

    async def api_switch_node(self, req):
        conf = await read_json_body(req)
        await backend_utilitys.restart(self.app.backend, AttrDict(conf))
        self.app.pac_server.update_sys_setting(True)
        await req.result_ok(conf)

    async def api_get_settings(self, req):
        keys = ['allow_lan']
        result = [(key, USER_CONF[key]) for key in keys]
        await req.result_ok(dict(result))

    async def api_set_settings(self, req):
        payload = await read_json_body(req)
        req_key = payload['key']
        req_value = payload['value']

        if req_key == 'allow_lan':
            USER_CONF.allow_lan = bool(req_value)
            self.app.update_state_icon()
        else:
            raise ValueError(f'bad key name: {req_key}')
        await req.result_ok(payload)

    async def api_diagnosis(self, req):
        writer = ChunkedWriter(req)
        await writer.begin()
        await writer.write(f'<!-- resolve delayed rendering of IE -->' * 20)

        async def call_func(func, text):
            escaped_text = text.replace('\n', R'\n').replace('"', R'\"')
            await writer.write(
                f'<script>parent.{func}("{escaped_text}")</script>')

        async for text in diagnosis_network(self.app):
            if isinstance(text, list):
                await call_func('updateState', text[0])
            else:
                await call_func('appendLog', text)

        await writer.end()

    def is_pac_path(self, path):
        url = urlsplit(path)
        return url.path == self.pac_path

    async def handle(self, reader, writer, path, raw_header):
        method, headers = parse_http_raw_header(raw_header)
        logger.debug(f'HTTP API: {method} {path}')
        url = urlsplit(path)
        api_path = url.path

        if not await self._check_api_request(writer, url, method):
            return

        func = self.route_table.get((method, api_path))
        if func is None:
            if method == 'GET':
                await try_read_file(writer, api_path)
            else:
                await api_result_err(writer, 'not found', 404)
            return

        args = ApiHandlerArgs(
            reader=reader, writer=writer,
            headers=headers, url=url)

        try:
            await func(args)
        except Exception as exc:
            if isinstance(exc, HttpBadRequest):
                real_exc = exc.args[0]
                await api_result_exc(writer, real_exc, 400)
            else:
                await api_result_exc(writer, exc)

    async def _check_api_request(self, writer, url, method):
        if not url.path.startswith('/api/'):
            return True

        if method == 'GET':
            return True

        params = parse_qs(url.query)
        if params.get('token', [''])[0] != CSRF_TOKEN:
            await api_result_err(writer, 'bad token')
            return False

        return True


def get_api_filter(app):
    api_handler = ApiHandler(app)

    async def http_filter(reader, writer, tunnel_mode,
                          host, port, path, raw_header):
        peer_ip_ = writer.get_extra_info('peername')[0]
        peer_ip = ip_address(peer_ip_)

        if tunnel_mode or host:
            if not peer_ip.is_loopback and not app.did_allow_lan:
                logger.warning(f'prevent proxy request from {peer_ip}')
                return True
            return False

        did_allow = True
        need_auth = (not peer_ip.is_loopback and
                     not api_handler.is_pac_path(path))

        if need_auth:
            did_allow = app.did_allow_lan or IS_DEBUG

        if did_allow:
            await api_handler.handle(reader, writer, path, raw_header)
        else:
            msg = f'you are not allowed to access this page! ({peer_ip})'
            await api_result_err(writer, msg, 403)

        return True

    return http_filter
