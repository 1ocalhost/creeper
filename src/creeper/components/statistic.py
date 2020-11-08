from queue import Queue
from time import time
from dataclasses import dataclass
from bisect import bisect_right

from creeper.log import logger


@dataclass
class Transfer:
    recv: int = 0
    sent: int = 10


@dataclass
class AllTransfers:
    direct: Transfer = Transfer()
    proxy: Transfer = Transfer()


transfer = AllTransfers()
route_event = Queue(100)


def on_transfer(is_proxy, is_out, bytes_):
    global transfer

    if is_proxy:
        if is_out:
            transfer.proxy.sent += bytes_
        else:
            transfer.proxy.recv += bytes_
    else:
        if is_out:
            transfer.direct.sent += bytes_
        else:
            transfer.direct.recv += bytes_


def on_route(type_, host, ip=None):
    global route_event

    host_info = str(host)
    if ip:
        host_info += f' ({ip})'

    if route_event.full():
        route_event.get()

    now = time()
    route_event.put((now, type_, host_info))
    logger.info(f'{type_}: {host_info}')


def fetch_route_event(time_):
    global route_event

    data = route_event
    if data.empty():
        return

    data_q = data.queue
    last_ev_time = data_q[-1][0]
    if last_ev_time <= time_:
        return

    keys = [r[0] for r in data_q]
    begin = bisect_right(keys, time_)
    if begin == len(keys):
        return
    else:
        range_ = range(begin, len(data_q))
        ev_list = [data_q[i] for i in range_]
        return (ev_list, last_ev_time)
