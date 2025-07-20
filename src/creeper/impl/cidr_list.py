import ipaddress


class CIDRList:
    def __init__(self, data_file):
        self.shift_bits = 0
        self.ip_table = {}
        self.init_table(data_file)

    def get_min_prefixlen(self, data):
        def get_prefixlen(cidr):
            return ipaddress.IPv4Network(cidr).prefixlen

        prefix_len_data = list(map(get_prefixlen, data))
        return min(prefix_len_data)

    def get_table_id(self, ip_str):
        ip_num = int(ipaddress.IPv4Address(ip_str))
        return ip_num >> self.shift_bits

    def init_table(self, data_file):
        data = []
        with open(data_file) as file:
            data = file.readlines()

        def is_ipv4_rule(ip):
            return ':' not in ip

        data = filter(is_ipv4_rule, data)
        data = [line.rstrip() for line in data]
        min_prelen = self.get_min_prefixlen(data)
        assert min_prelen in range(1, 33)

        self.shift_bits = 32 - min_prelen
        for item in data:
            ip_str = item.split('/')[0]
            tab_id = self.get_table_id(ip_str)
            record = ipaddress.IPv4Network(item)
            self.ip_table.setdefault(tab_id, []).append(record)

    def contains(self, ipv4):
        tab_id = self.get_table_id(ipv4)
        if tab_id not in self.ip_table:
            return False

        ip_addr = ipaddress.IPv4Address(ipv4)
        for record in self.ip_table[tab_id]:
            if ip_addr in record:
                return True

        return False
