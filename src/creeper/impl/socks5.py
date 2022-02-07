import struct
import socket

from creeper.log import logger
from creeper.utils import fmt_exc


async def parse_socks5_connect(atype, reader):
    ATYP_IPV4 = 1
    ATYP_DOMAIN = 3
    ATYP_IPV6 = 4

    if atype == ATYP_DOMAIN:
        received = await reader.readexactly(1)
        domain_len = int.from_bytes(received, 'big')
        received = await reader.readexactly(domain_len)
        domain = received.decode()

    elif atype == ATYP_IPV4:
        received = await reader.readexactly(4)
        domain = socket.inet_ntop(socket.AF_INET, received)

    elif atype == ATYP_IPV6:
        received = await reader.readexactly(16)
        domain = socket.inet_ntop(socket.AF_INET6, received)

    else:
        raise Exception('Unknown address type!')

    received = await reader.readexactly(2)
    port = int.from_bytes(received, 'big')
    return domain, port


async def negotiate_socks5(reader, writer):
    received = await reader.readexactly(2)
    is_socks5 = received[0] == 5
    if not is_socks5:
        return False, received

    tail_len = received[1]
    await reader.readexactly(tail_len)

    writer.write(b'\x05\x00')
    await writer.drain()

    received = await reader.readexactly(4)
    ver, cmd, rsv, atyp = struct.unpack('!4B', received)
    if cmd != 1:
        raise TypeError('not CMD_CONNECT')

    return True, await parse_socks5_connect(atyp, reader)


async def try_negotiate_socks5(reader, writer):
    try:
        is_socks5, received = await negotiate_socks5(reader, writer)
    except TypeError as e:
        logger.debug(fmt_exc(e))
        return True, None

    if is_socks5:
        host, port = received
        result = None, True, host, port, None
        return True, result

    return False, received


def end_negotiate_socks5(writer, peer_writer):
    host, port = '1.2.3.4', 1234
    response = b'\x05\x00\x00'
    response += b'\x01'  # IPv4
    response += socket.inet_pton(socket.AF_INET, host)
    response += port.to_bytes(2, 'big')
    writer.write(response)
