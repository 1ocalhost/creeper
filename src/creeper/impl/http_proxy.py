import re
import asyncio
import urllib.parse

from creeper.log import logger
from creeper.utils import run_async, readable_exc


all_clients = {}
REQUEST_URI_PARSER = re.compile(r'(.+)\:(\d+)$')


def split_host_port(loc):
    m = REQUEST_URI_PARSER.match(loc)
    if not m:
        return loc, None
    else:
        return m.group(1), int(m.group(2))


def parse_request_uri(uri):

    uri_result = urllib.parse.urlsplit(uri)
    path = uri_result.path
    if not path:
        path = '/'
    if uri_result.query:
        path += '?'
        path += uri_result.query

    return split_host_port(uri_result.netloc), path


async def read_http_header(reader):
    header = b''
    while True:
        line = await reader.readline()
        if not line:
            break

        header += line
        if line == b'\r\n':
            break

    return header


def remore_useless_header(header):
    def not_proxy_keep_alive(x):
        return not x.lower().startswith('proxy-connection:')

    return list(filter(not_proxy_keep_alive, header))


async def get_request_info_from_header(reader):
    header = await read_http_header(reader)
    if not header:
        logger.debug('failed to read header')
        return

    header_items = header.decode().split('\r\n')
    method_args = header_items[0].split(' ')
    method = method_args[0]
    uri = method_args[1]
    tunnel_mode = (method == 'CONNECT')

    if tunnel_mode:
        host, port = split_host_port(uri)
        path = None
        if not port:
            return
    else:
        (host, port), path = parse_request_uri(uri)
        if not port:
            port = 80
        method_args[1] = path
        header_items[0] = ' '.join(method_args)

    header_items = remore_useless_header(header_items)
    new_header = '\r\n'.join(header_items).encode()
    return new_header, tunnel_mode, host, port, path


async def relay_stream(statistic,
                       reader, writer, peer_reader, peer_writer):
    async def relay(reader, reader2, writer, is_out):
        try:
            while True:
                line = await reader.read(1024)
                if len(line) == 0:
                    reader2.feed_eof()
                    break
                writer.write(line)
                statistic(is_out, len(line))
                await writer.drain()
        except BaseException:
            pass

    await asyncio.wait([
        relay(reader, peer_reader, peer_writer, True),
        relay(peer_reader, reader, writer, False)
    ])


async def open_connection_exc(opt, host, port):
    TIMEOUT = 10
    open_conn = opt.get('open_conn')
    if open_conn:
        fut = open_conn(host, port)
        try:
            return await asyncio.wait_for(fut, TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f'connect timeout: {host}:{port}')
    else:
        def statistic():
            pass
        fut = asyncio.open_connection(host, port)
        peer = await asyncio.wait_for(fut, TIMEOUT)
        return peer, statistic


async def open_peer_connection(reader, writer, opt):
    req_info = await get_request_info_from_header(reader)
    if req_info is None:
        return

    header, tunnel_mode, host, port, path = req_info
    req_filter = opt.get('req_filter')
    if req_filter:
        is_filtered = await req_filter(
            reader, writer, tunnel_mode, host, port, path, header)
        if is_filtered:
            return

    result = await open_connection_exc(opt, host, port)
    if result is None:
        return
    peer, statistic = result
    return peer, header, tunnel_mode, statistic


async def server_handler_impl(reader, writer, opt):
    peer_connection = await open_peer_connection(reader, writer, opt)
    if peer_connection is None:
        return

    peer, header, tunnel_mode, statistic = peer_connection
    peer_reader, peer_writer = peer

    try:
        if tunnel_mode:
            writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
            await writer.drain()
        else:
            peer_writer.write(header)
            statistic(True, len(header))
            await peer_writer.drain()
        await relay_stream(
            statistic, reader, writer, peer_reader, peer_writer)
    finally:
        peer_writer.close()


async def server_handler(reader, writer, opt):
    routine = server_handler_impl(reader, writer, opt)
    task = asyncio.ensure_future(routine)
    all_clients[task] = (reader, writer)

    def client_done(task):
        del all_clients[task]
        writer.close()

    task.add_done_callback(client_done)


async def server_loop(host, port, opt):
    on_exc = opt.get('on_exc')

    def exception_handler(loop, context):
        ex = context.get('exception')
        if ex is None:
            return

        if isinstance(ex, AssertionError) and \
                str(ex) == 'feed_data after feed_eof':
            return

        if (on_exc):
            on_exc(ex)

        logger.warn(f'server_loop: {readable_exc(ex)}')

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(exception_handler)

    async def handler(reader, writer):
        await server_handler(reader, writer, opt)

    server = await asyncio.start_server(handler, host, port)
    started = opt.get('started')
    if started:
        addr = server.sockets[0].getsockname()
        started(server, addr)

    async with server:
        await server.serve_forever()


def make_http_server_filter(handler):
    async def filter_(reader, writer, tunnel_mode,
                      host, port, path, header):
        if tunnel_mode:
            return

        if host:
            return

        type_, body = handler(path)
        response = '\r\n'.join([
            'HTTP/1.1 200 OK',
            'Content-Type: ' + type_,
            '',
            body
        ])

        writer.write(response.encode())
        await writer.drain()
        return True

    return filter_


def run_server(ip, port, opt={}):
    run_async(server_loop(ip, port, opt))


if __name__ == '__main__':
    def http_handler(path):
        return 'text/html', f'This is a HTTP proxy server. ({path})\n'

    opt = {'req_filter': make_http_server_filter(http_handler)}
    run_server('127.0.0.1', 9400, opt)

    # reverse mode: curl http://google.com/ -x 127.0.0.1:9400
    # tunnel mode:  curl https://google.com/ -x 127.0.0.1:9400
    # http server:  curl http://127.0.0.1:9400/hello
