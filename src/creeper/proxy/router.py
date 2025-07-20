import asyncio
import os
import re
import time
from threading import Lock

from expiringdict import ExpiringDict
from creeper.log import logger
from creeper.utils import hour_to_sec, is_ipv4
from creeper.impl.dns_lookup import doh_lookup
from creeper.impl.cidr_list import CIDRList
from creeper.env import APP_CONF, PATH_RULES

DOH_SERVERS = APP_CONF['doh']


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


is_domain_name = make_domain_name_verifier()


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
            if not is_ipv4(ip):
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
        self.hosts_file = HostsFile()
        self.resolving = set()
        self.cache = ExpiringDict(10000, hour_to_sec(0.5))

    @staticmethod
    def is_ipv6(host):
        return host.startswith('[')

    @staticmethod
    async def dns_query(host, server):
        records = await doh_lookup(host, server)
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

    async def resolve(self, domain):
        for server in DOH_SERVERS:
            try:
                ip = await self.dns_query(domain, server)
            except Exception:
                continue

            if ip:
                self.cache[domain] = ip
                return ip

    async def resolve_cached(self, domain):
        end_time = time.time() + 30

        while time.time() < end_time:
            ip = self.cache.get(domain)
            if ip:
                return ip

            if domain in self.resolving:
                await asyncio.sleep(0.1)
                continue

            self.resolving.add(domain)
            try:
                ip = await self.resolve(domain)
            except Exception:
                continue
            finally:
                self.resolving.remove(domain)

            self.cache[domain] = ip
            return ip

    def find_local(self, host):
        return self.hosts_file.find(host)


class DomainList:
    def __init__(self, path):
        lines = path.read_text().splitlines()
        lines = map(str.strip, lines)
        lines = filter(None, lines)
        self.rules = set(lines)

    def contains(self, domain):
        parts = domain.split('.')
        for num in range(2, len(parts) + 1):
            subdomian = '.'.join(parts[-num:])
            if subdomian in self.rules:
                return True


class Router:
    def __init__(self):
        self.LIST_MAX = 10000
        self.WAIT_TIMEOUT = 30
        self.dns = SafeDNS()
        self.cn_ip = CIDRList(PATH_RULES / 'china_ip.txt')
        self.gfw_ip = CIDRList(PATH_RULES / 'gfw_ip.txt')
        self.cn_domain = DomainList(PATH_RULES / 'china_domain.txt')
        self.gfw_domain = DomainList(PATH_RULES / 'gfw_domain.txt')
        self.proxy_domain = set()
        self.direct_domain = set()
        self.determining = set()

    def need_proxy_ip(self, ip):
        return not self.cn_ip.contains(ip) and \
            not self.gfw_ip.contains(ip)

    def add_domain(self, domain, ip):
        if self.need_proxy_ip(ip):
            self.proxy_domain.add(domain)
            return True
        else:
            self.direct_domain.add(domain)
            return False

    async def need_proxy_domain(self, domain):
        if self.cn_domain.contains(domain):
            return False

        if self.gfw_domain.contains(domain):
            return True

        end_time = time.time() + self.WAIT_TIMEOUT

        while time.time() < end_time:
            if domain in self.proxy_domain:
                return True

            if domain in self.direct_domain:
                return False

            if domain in self.determining:
                await asyncio.sleep(0.1)
                continue

            self.determining.add(domain)
            try:
                ip = await self.dns.resolve(domain)
            except Exception:
                continue
            finally:
                self.determining.remove(domain)

            if not ip:
                return

            return self.add_domain(domain, ip)

    async def need_proxy(self, host):
        if self.dns.is_ipv6(host):
            return False

        if is_ipv4(host):
            return self.need_proxy_ip(host)

        ip = self.dns.find_local(host)
        if ip:
            return self.need_proxy_ip(ip)

        # example: "hello" from chrome searching bar
        if not is_domain_name(host):
            return None

        return await self.need_proxy_domain(host)
