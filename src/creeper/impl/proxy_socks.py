from python_socks._types import ProxyType
from python_socks.async_.asyncio.v2 import Proxy, ProxyChain

from creeper.env import USER_CONF


async def open_connection(
    dest_host,
    dest_port,
    backend_host,
    backend_port
):
    backend_proxy = Proxy(ProxyType.SOCKS5, backend_host, backend_port)
    proxy_list = [backend_proxy]

    if USER_CONF.use_upstream_proxy:
        upstream_proxy = USER_CONF.upstream_proxy_url
        if upstream_proxy:
            proxy_list.append(Proxy.from_url(upstream_proxy))

    proxy_chain = ProxyChain(proxy_list)
    stream = await proxy_chain.connect(dest_host, dest_port, timeout=10.0)
    return stream.reader, stream.writer
