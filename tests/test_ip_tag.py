from typing import TYPE_CHECKING
import contextlib
import os
from pathlib import Path
import unittest.mock

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

from fichub_net import ip_tag


@contextlib.contextmanager
def working_directory(path: Path) -> Iterator[None]:
    cur_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(cur_cwd)


def test_try_parse_ip_network() -> None:
    assert ip_tag.try_parse_ip_network("100.0.0.0/8") is not None
    assert ip_tag.try_parse_ip_network("127.0.0.1") is not None

    assert ip_tag.try_parse_ip_network("127.0.0./24") is None
    assert ip_tag.try_parse_ip_network("") is None


@pytest.fixture
def ip_range_dat(tmp_path: Path) -> Path:
    (tmp_path / "dat").mkdir()
    # ignored
    (tmp_path / "dat" / ".gitkeep").write_text("")

    # azure_xml
    (tmp_path / "dat" / "PublicIPs_20200824.xml").write_text(
        """
        <?xml version="1.0" encoding="utf-8"?>
        <AzurePublicIpAddresses xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <Region Name="testregion">
                <IpRange Subnet="127.0.0.1" />
                <IpRange Subnet="not a real range xml" />
                <IpRange Subnet="115.60.135.184" />
            </Region>
        </AzurePublicIpAddresses>
        """,
    )

    # azure_json
    (tmp_path / "dat" / "ServiceTags_Public_20230703.json").write_text(
        """
        {
            "values": [
                {
                    "name": "testgroup",
                    "properties": {
                        "addressPrefixes": [
                            "not a real range json",
                            "127.0.0.1",
                            "3.5.140.1"
                        ]
                    }
                }
            ]
        }
        """,
    )

    # google
    (tmp_path / "dat" / "google_cloud.json").write_text(
        """
        {
            "prefixes": [
                { "ipv4Prefix": "127.0.0.1" },
                { "ipv4Prefix": "not a real ipv4 range google" },
                { "ipv4Prefix": "34.122.147.229" },
                { "ipv6Prefix": "::1" },
                { "ipv6Prefix": "not a real ipv6 range google" },
                { "bad": "missing key" }
            ]
        }
        """,
    )

    # aws
    (tmp_path / "dat" / "aws-ip-ranges.json").write_text(
        """
        {
            "prefixes": [
                { "ip_prefix": "127.0.0.1" },
                { "ip_prefix": "not a real ipv4 range aws" },
                { "ip_prefix": "4.232.106.88" },
                { "ipv6_prefix": "::1" },
                { "ipv6_prefix": "not a real ipv6 range aws" },
                { "bad": "missing key" }
            ]
        }
        """,
    )

    # asn
    (tmp_path / "dat" / "test-asn.txt").write_text(
        """
        127.0.0.1
        not a real ipv4 range asn
        47.92.205.
        ::1
        not a real ipv6 range asn
        """,
    )

    return tmp_path


def test_load_azure_ip_ranges_xml(ip_range_dat: Path) -> None:
    fname = ip_range_dat / "dat" / "PublicIPs_20200824.xml"
    with working_directory(ip_range_dat):
        ip_tag.load_azure_ip_ranges_xml(fname)


def test_load_azure_ip_ranges_json(ip_range_dat: Path) -> None:
    fname = ip_range_dat / "dat" / "ServiceTags_Public_20230703.json"
    with working_directory(ip_range_dat):
        ip_tag.load_azure_ip_ranges_json(fname)


def test_load_google_ip_ranges(ip_range_dat: Path) -> None:
    fname = ip_range_dat / "dat" / "google_cloud.json"
    with working_directory(ip_range_dat):
        ip_tag.load_google_ip_ranges(fname)


def test_load_aws_ip_ranges(ip_range_dat: Path) -> None:
    fname = ip_range_dat / "dat" / "aws-ip-ranges.json"
    with working_directory(ip_range_dat):
        ip_tag.load_aws_ip_ranges(fname)


def test_load_asn_list(ip_range_dat: Path) -> None:
    fname = ip_range_dat / "dat" / "test-asn.txt"
    ip_tag.load_asn_list("test-tag", fname)
    ip_tag.load_asn_list("test-tag", fname)


def test_load_ip_ranges(ip_range_dat: Path) -> None:
    with working_directory(ip_range_dat):
        ip_tag.load_ip_ranges(
            Path("./dat/"),
            {
                "dat/PublicIPs_20200824.xml": ("azure_xml", "azure"),
                "dat/ServiceTags_Public_20230703.json": ("azure_json", "azure"),
                "dat/google_cloud.json": ("google", "google"),
                "dat/aws-ip-ranges.json": ("aws", "aws"),
                "dat/test-asn.txt": ("asn_list", "test-asn"),
                "dat/.gitkeep": ("ignore", "ignore"),
            },
        )


def test_load_ip_ranges_uncovered(ip_range_dat: Path) -> None:
    with (
        working_directory(ip_range_dat),
        pytest.raises(Exception, match="live source is not in sources"),
    ):
        ip_tag.load_ip_ranges(
            Path("./dat/"),
            {
                "dat/PublicIPs_20200824.xml": ("azure_xml", "azure"),
                "dat/ServiceTags_Public_20230703.json": ("azure_json", "azure"),
                "dat/google_cloud.json": ("google", "google"),
                "dat/aws-ip-ranges.json": ("aws", "aws"),
                "dat/.gitkeep": ("ignore", "ignore"),
            },
        )


def test_load_ip_ranges_missing(ip_range_dat: Path) -> None:
    with (
        working_directory(ip_range_dat),
        pytest.raises(Exception, match="never loaded some sources"),
    ):
        ip_tag.load_ip_ranges(
            Path("./dat/"),
            {
                "dat/PublicIPs_20200824.xml": ("azure_xml", "azure"),
                "dat/ServiceTags_Public_20230703.json": ("azure_json", "azure"),
                "dat/google_cloud.json": ("google", "google"),
                "dat/aws-ip-ranges.json": ("aws", "aws"),
                "dat/test-asn.txt": ("asn_list", "test-asn"),
                "dat/test-asn2.txt": ("asn_list", "test-asn"),
                "dat/.gitkeep": ("ignore", "ignore"),
            },
        )


def test_load_ip_ranges_vacuous(tmp_path: Path) -> None:
    with working_directory(tmp_path):
        ip_tag.load_ip_ranges(Path("./dat/"), {})


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    with unittest.mock.patch(
        "sys.stdin.readlines", return_value=["3.5.140.1", "", " 142.132.180.201 \t\n"]
    ):
        assert ip_tag.main() == 0

        with capsys.disabled():
            captured = capsys.readouterr()
            assert captured.out != ""
            assert captured.out == "all_good: count=1\n"
            assert captured.err == ""

    with unittest.mock.patch(
        "sys.stdin.readlines", return_value=["", "100.80.100.100", ""]
    ):
        assert ip_tag.main() == 1

        with capsys.disabled():
            captured = capsys.readouterr()
            assert captured.out != ""
            assert captured.out == "100.80.100.100\n"
            assert captured.err == ""


def test_ip_is_datacenter() -> None:
    for addr in [
        "115.60.135.184",
        "3.5.140.1",
        "34.122.147.229",
        "4.232.106.88",
        "47.92.205.",
    ]:
        tag0 = ip_tag.ip_is_datacenter(addr)
        assert tag0 is not None
        tag1 = ip_tag.ip_is_datacenter(addr)
        assert tag1 is tag0

    for addr in [
        "100.80.100.100",
    ]:
        assert ip_tag.ip_is_datacenter(addr) is None
        assert ip_tag.ip_is_datacenter(addr) is None
