import os
import re
import socket
import asyncio
import ipaddress
from threading import Lock

from expiringdict import ExpiringDict
from creeper.log import logger
from creeper.utils import hour_to_sec
from creeper.impl.dns_lookup import dns_lookup
from creeper.impl.cidr_list import CIDRList


def make_domain_name_verifier():
    DOMAIN_TOKEN = re.compile(R'^[a-z0-9-]+$')
    TOP_GENERAL = re.compile(R'^[a-z]{2,}$')

    def is_domain_token(text):
        return bool(DOMAIN_TOKEN.match(text))

    def is_top_domain(text):
        if text.startswith('xn--'):
            return is_domain_token(text)
        else:
            return bool(TOP_GENERAL.match(text))

    def check_if_domain_name(name):
        if -1 == name.find('.'):
            return False

        tokens = name.split('.')
        for i in tokens[1:]:
            if not is_domain_token(i):
                return False

        return is_top_domain(tokens[-1])

    return check_if_domain_name


class HostsFile:
    def __init__(self):
        self.lock = Lock()
        self.cached_stamp = 0
        self.cached_records = {}
        self.hosts_file = R'C:\Windows\System32\drivers\etc\hosts'

    def find(self, name):
        with self.lock:
            return self.find_impl(name)

    def find_impl(self, name):
        if not self.try_update_db():
            return

        return self.cached_records.get(name)

    def read_records(self):
        def read_record(line):
            data = line.split('#')[0].strip()
            tokens = data.replace('\t', ' ').split()
            if len(tokens) != 2:
                return

            ip, host = tokens
            if not SafeDNS.is_ipv4(ip):
                logger.debug(f'not IPv4: {ip}')
                return

            self.cached_records[host] = ip

        with open(self.hosts_file, 'r') as file:
            for line in file.readlines():
                read_record(line)

    def try_update_db(self):
        file_path = self.hosts_file
        if not os.path.isfile(file_path):
            return False

        file_stat = os.stat(file_path)
        if file_stat.st_size > 1024 * 1024 * 10:
            logger.error(f'too large: {file_path}')
            return False

        stamp = os.stat(file_path).st_mtime
        if stamp == self.cached_stamp:
            return True

        self.cached_stamp = stamp
        self.cached_records = {}
        self.read_records()


class SafeDNS:
    def __init__(self):
        self.cache = ExpiringDict(500, hour_to_sec(0.5))
        self.dns_poisoned = {}
        self.hosts_file = HostsFile()
        self.is_domain_name = make_domain_name_verifier()

    @staticmethod
    def is_ipv4(host):
        try:
            socket.inet_aton(host)
        except socket.error:
            return False
        return True

    @staticmethod
    def is_ipv6(host):
        return host.startswith('[')

    @staticmethod
    def dns_query_impl(host, server):
        records = dns_lookup(host, server)
        if not records:
            logger.debug(f'DNS resolving failed: {host} @{server}')
            return

        type_a = records.get('A')
        if not type_a:
            logger.debug(f'DNS no A record: {host} @{server}')
            return

        ip = type_a[0]
        logger.debug(f'DNS resolved: {host} => {ip} @{server}')
        return ip

    async def dns_query(self, host):
        dns_servers = [
            '119.29.29.29',
            '8.8.8.8',
            '223.5.5.5',
        ]

        pre_ip = None
        for times in range(3):
            if times > 0:
                await asyncio.sleep(times)

            for server in dns_servers:
                ip = self.dns_query_impl(host, server)
                if not ip:
                    continue

                if ipaddress.ip_address(ip).is_global:
                    if pre_ip:
                        logger.debug(f'dns_poisoned: {ip} to {pre_ip}')
                        self.dns_poisoned[host] = ip
                    return ip

                pre_ip = ip

        return pre_ip

    def dns_lookup_local(self, host):
        return self.hosts_file.find(host)

    async def lookup_host(self, host):
        ipv4 = self.dns_lookup_local(host)
        if ipv4:
            return ipv4, True

        # example: "hello" from chrome searching bar
        if not self.is_domain_name(host):
            return None, True

        return await self.dns_query(host), False

    async def host_to_ipv4(self, host):
        try:
            return self.cache[host]
        except KeyError:
            pass

        try:
            return self.dns_poisoned[host]
        except KeyError:
            pass

        if self.is_ipv6(host):
            return

        if self.is_ipv4(host):
            return host
        else:
            ipv4, local = await self.lookup_host(host)
            if not ipv4:
                return
            if not local:
                self.cache[host] = ipv4
            return ipv4


class Router:
    def __init__(self, data_file):
        self.dns = SafeDNS()
        self.cn_ip = CIDRList(data_file)
        self.proxy_cache = ExpiringDict(500, hour_to_sec(2))
        self.dirct_cache = ExpiringDict(500, hour_to_sec(0.5))
        self.error_cache = ExpiringDict(100, 5)

    async def query_if_direct(self, host):
        if self.dns.is_ipv6(host):
            return True, host

        ip = await self.dns.host_to_ipv4(host)
        if not ip:
            return None, None

        if not ipaddress.ip_address(ip).is_global:
            return True, ip

        if self.cn_ip.contains(ip):
            return True, ip

        return False, ip

    async def is_direct(self, host):
        for cache in [
            self.dirct_cache,
            self.proxy_cache,
            self.error_cache,
        ]:
            try:
                return cache[host]
            except KeyError:
                continue

        result = await self.query_if_direct(host)
        is_direct_, remote = result
        if is_direct_ is None:
            self.error_cache[host] = result
        elif is_direct_:
            self.dirct_cache[host] = result
        else:
            self.proxy_cache[host] = result

        return is_direct_, remote
