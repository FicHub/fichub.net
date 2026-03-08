#!./venv/bin/python
import ipaddress
import json
from pathlib import Path
import sys
import traceback
import xml.etree.ElementTree as ET

from fichub_net.rl_conf import IP_TAG_SOURCES

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

TAGGED_IP_RANGES: dict[str, list[IPNetwork]] = {}
IP_TAG: dict[str, str | None] = {}


def try_parse_ip_network(r: str) -> IPNetwork | None:
    try:
        return ipaddress.ip_network(r)
    except Exception as e:
        traceback.print_exc()
        print(e)
        print(f"try_parse_ip_network: ^ something went wrong parsing {r}")
    return None


def load_azure_ip_ranges_xml(fname: Path, tag: str = "azure") -> None:
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    # Load legacy xml format
    with fname.open() as f:
        x = f.read().strip()

    root = ET.fromstring(x)

    def extract_ip_ranges(e: ET.Element) -> set[str]:
        if e.tag == "IpRange":
            return {e.attrib["Subnet"]}
        s = set()
        for child in e:
            s |= extract_ip_ranges(child)
        return s

    ranges = extract_ip_ranges(root)

    for r in ranges:
        n = try_parse_ip_network(r)
        if n is not None:
            TAGGED_IP_RANGES[tag].append(n)


def load_azure_ip_ranges_json(fname: Path, tag: str = "azure") -> None:
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    # Load new json format
    with fname.open() as f:
        x = f.read()
    j = json.loads(x)
    for val in j["values"]:
        prop = val["properties"]
        for r in prop["addressPrefixes"]:
            n = try_parse_ip_network(r)
            if n is not None:
                TAGGED_IP_RANGES[tag].append(n)


def load_google_ip_ranges(fname: Path, tag: str = "google") -> None:
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    with fname.open() as f:
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
        n = try_parse_ip_network(r)
        if n is not None:
            TAGGED_IP_RANGES[tag].append(n)


def load_aws_ip_ranges(fname: Path, tag: str = "aws") -> None:
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    with fname.open() as f:
        x = f.read()
    j = json.loads(x)

    for prefix in j["prefixes"]:
        r = prefix.get("ip_prefix")
        if r is None:
            r = prefix.get("ipv6_prefix")
        if r is None:
            continue
        n = try_parse_ip_network(r)
        if n is not None:
            TAGGED_IP_RANGES[tag].append(n)


def load_asn_list(tag: str, fname: Path) -> None:
    if tag not in TAGGED_IP_RANGES:
        TAGGED_IP_RANGES[tag] = []

    with fname.open() as f:
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


def load_ip_ranges(dat: Path, sources: dict[str, tuple[str, str]]) -> None:
    seen_sources = set()
    for src in dat.rglob("*"):
        if str(src) not in sources:
            msg = f"load_ip_ranges: live source is not in sources: {src}"
            raise Exception(msg)  # noqa: TRY002

        typ, tag = sources[str(src)]
        if typ == "asn_list":
            load_asn_list(tag, src)
        elif typ == "azure_xml":
            load_azure_ip_ranges_xml(src, tag)
        elif typ == "azure_json":
            load_azure_ip_ranges_json(src, tag)
        elif typ == "google":
            load_google_ip_ranges(src, tag)
        elif typ == "aws":
            load_aws_ip_ranges(src, tag)
        elif typ == "ignore":
            pass
        else:
            msg = f"load_ip_ranges: unknown tag type: {typ}"
            raise Exception(msg)  # noqa: TRY002

        seen_sources |= {str(src)}

    unseen_sources = set(sources.keys()) - seen_sources
    if len(unseen_sources) != 0:
        msg = f"load_ip_ranges: never loaded some sources: {unseen_sources}"
        raise Exception(msg)  # noqa: TRY002


def ip_is_datacenter(addr: str) -> str | None:
    # If we have a cached value for this IPs tag, return it directly
    if addr in IP_TAG:
        return IP_TAG[addr]

    # Otherwise look for it in the tag sets
    try:
        ip = ipaddress.ip_address(addr)

        for tag, tagged_ip_range in TAGGED_IP_RANGES.items():
            for ip_range in tagged_ip_range:
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
    load_ip_ranges(Path("./dat/"), IP_TAG_SOURCES)
    all_good = True
    count = 0
    for line in sys.stdin.readlines():
        addr = line.strip()
        if len(addr) < 1 or addr == "142.132.180.201":  # gil
            continue
        count += 1
        if ip_is_datacenter(addr) is None:
            print(addr)
            all_good = False

    if all_good:
        print(f"all_good: {count=}")
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
