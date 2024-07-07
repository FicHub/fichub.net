import ip_tag


def test_load_ip_ranges() -> None:
    ip_tag.load_ip_ranges()


def test_ip_is_datacenter() -> None:
    for addr in [
        "115.60.135.184",
        "172.105.91.7",
        "172.233.157.43",
        "34.122.147.229",
        "3.5.140.1",
        "4.232.106.88",
        "4.232.106.89",
        "45.32.179.18",
        "46.17.43.24",
        "47.76.94.9",
        "47.92.205.",
    ]:
        assert ip_tag.ip_is_datacenter(addr) is not None

    for addr in [
        "100.80.100.100",
    ]:
        assert ip_tag.ip_is_datacenter(addr) is None
