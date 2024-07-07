#!./venv/bin/python
from typing import Any, Dict, List, Optional, Set
import ipaddress
import json
import sys
import traceback
import xml.etree.ElementTree as ElementTree

TAGGED_IP_RANGES: Dict[str, List[Any]] = {}  # TODO
IP_TAG: Dict[str, Optional[str]] = {}


def load_azure_ip_ranges() -> None:
    tag = "azure"
    global TAGGED_IP_RANGES
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    # Load legacy xml format
    with open("./dat/PublicIPs_20200824.xml") as f:
        x = f.read()

    root = ElementTree.fromstring(x)

    def extractIpRanges(e: ElementTree.Element) -> Set[str]:
        if e.tag == "IpRange":
            return {e.attrib["Subnet"]}
        else:
            s = set()
            for child in e:
                s |= extractIpRanges(child)
            return s

    ranges = extractIpRanges(root)

    for r in ranges:
        try:
            n = ipaddress.ip_network(r)
            TAGGED_IP_RANGES[tag].append(n)
        except Exception as e:
            traceback.print_exc()
            print(e)
            print(f"load_azure_ip_ranges: ^ something went wrong parsing {r}")

    # Load new json format
    with open("./dat/ServiceTags_Public_20230703.json") as f:
        x = f.read()
    j = json.loads(x)
    for val in j["values"]:
        prop = val["properties"]
        for r in prop["addressPrefixes"]:
            try:
                n = ipaddress.ip_network(r)
                TAGGED_IP_RANGES[tag].append(n)
            except Exception as e:
                traceback.print_exc()
                print(e)
                print(f"load_azure_ip_ranges: ^ something went wrong parsing {r}")


def load_google_ip_ranges() -> None:
    tag = "google"
    global TAGGED_IP_RANGES
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    with open("./dat/google_cloud.json") as f:
        x = f.read()
    j = json.loads(x)

    for prefix in j["prefixes"]:
        r = None
        if "ipv4Prefix" in prefix:
            r = prefix["ipv4Prefix"]
        elif "ipv6Prefix" in prefix:
            r = prefix["ipv6Prefix"]
        if r is None:
            continue
        try:
            n = ipaddress.ip_network(r)
            TAGGED_IP_RANGES[tag].append(n)
        except Exception as e:
            traceback.print_exc()
            print(e)
            print(f"load_google_ip_ranges: ^ something went wrong parsing {r}")


def load_aws_ip_ranges() -> None:
    tag = "aws"
    global TAGGED_IP_RANGES
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    with open("./dat/aws-ip-ranges.json") as f:
        x = f.read()
    j = json.loads(x)

    for prefix in j["prefixes"]:
        try:
            r = prefix["ip_prefix"]
            n = ipaddress.ip_network(r)
            TAGGED_IP_RANGES[tag].append(n)
        except Exception as e:
            traceback.print_exc()
            print(e)
            print(f"load_aws_ip_ranges: ^ something went wrong parsing {r}")


def load_asn_list(tag: str, fname: str) -> None:
    global TAGGED_IP_RANGES
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    with open(fname) as f:
        x = f.readlines()

    for xx in x:
        try:
            r = xx.strip()
            if len(r) == 0:
                continue
            n = ipaddress.ip_network(r)
            TAGGED_IP_RANGES[tag].append(n)
        except Exception as e:
            traceback.print_exc()
            print(e)
            print(
                f"load_asn_list({tag=}, {fname=}): ^ something went wrong parsing {r}"
            )


def load_ip_ranges() -> None:
    load_asn_list("do", "./dat/digitalocean_ip_cidr_blocks.lst")
    load_asn_list("asn", "./dat/asn9009_2024_02_11.txt")
    load_azure_ip_ranges()
    load_google_ip_ranges()
    load_aws_ip_ranges()


def ip_is_datacenter(addr: str) -> Optional[str]:
    # If we have a cached value for this IPs tag, return it directly
    global IP_TAG
    if addr in IP_TAG:
        return IP_TAG[addr]

    # Otherwise look for it in the tag sets
    global TAGGED_IP_RANGES

    try:
        ip = ipaddress.ip_address(addr)

        for tag in TAGGED_IP_RANGES:
            for ip_range in TAGGED_IP_RANGES[tag]:
                if ip in ip_range:
                    IP_TAG[addr] = tag
                    return IP_TAG[addr]

        IP_TAG[addr] = None
        return IP_TAG[addr]
    except Exception as e:
        traceback.print_exc()
        print(e)
        print(f"ip_tag: ^ something went wrong checking if ip is tagged: {addr}")

    return "uh-oh"


def main() -> int:
    load_ip_ranges()
    all_good = True
    count = 0
    for line in sys.stdin.readlines():
        addr = line.strip()
        if len(addr) < 1 or addr == "142.132.180.201":  # gil
            continue
        count += 1
        # print(f"checking {addr=}")
        if ip_is_datacenter(addr) is None:
            print(addr)
            all_good = False

    if all_good:
        print(f"all_good: {count=}")
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
