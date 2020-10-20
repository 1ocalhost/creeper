function FindProxyForURL(url, host) {
    if (isInNet(host, "10.0.0.0", "255.0.0.0") ||
        isInNet(host, "172.16.0.0", "255.240.0.0") ||
        isInNet(host, "192.168.0.0", "255.255.0.0"))
        return "DIRECT";

    var real_localhost = [
        "localhost.ptlogin2.qq.com"
    ];

    for (var i = 0; i < real_localhost.length; ++i) {
        if (host == real_localhost[i])
            return "DIRECT";
    }

    return "PROXY {{proxy}}; DIRECT";
}
