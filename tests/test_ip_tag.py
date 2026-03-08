from typing import TYPE_CHECKING
import contextlib
import os
from pathlib import Path
import unittest.mock

if TYPE_CHECKING:
    from collections.abc import Iterator

if TYPE_CHECKING:
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


def test_load_azure_ip_ranges(tmp_path: Path) -> None:
    (tmp_path / "dat").mkdir()

    (tmp_path / "dat" / "PublicIPs_20200824.xml").write_text(
        """
        <?xml version="1.0" encoding="utf-8"?>
        <AzurePublicIpAddresses xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <Region Name="testregion">
                <IpRange Subnet="127.0.0.1" />
                <IpRange Subnet="not a real range xml" />
            </Region>
        </AzurePublicIpAddresses>
        """,
    )

    (tmp_path / "dat" / "ServiceTags_Public_20230703.json").write_text(
        """
        {
            "values": [
                {
                    "name": "testgroup",
                    "properties": {
                        "addressPrefixes": [
                            "not a real range json",
                            "127.0.0.1"
                        ]
                    }
                }
            ]
        }
        """,
    )

    with working_directory(tmp_path):
        ip_tag.load_azure_ip_ranges()


def test_load_google_ip_ranges(tmp_path: Path) -> None:
    (tmp_path / "dat").mkdir()
    (tmp_path / "dat" / "google_cloud.json").write_text(
        """
        {
            "prefixes": [
                { "ipv4Prefix": "127.0.0.1" },
                { "ipv4Prefix": "not a real ipv4 range google" },
                { "ipv6Prefix": "::1" },
                { "ipv6Prefix": "not a real ipv6 range google" },
                { "bad": "missing key" }
            ]
        }
        """,
    )

    with working_directory(tmp_path):
        ip_tag.load_google_ip_ranges()


def test_load_aws_ip_ranges(tmp_path: Path) -> None:
    (tmp_path / "dat").mkdir()
    (tmp_path / "dat" / "aws-ip-ranges.json").write_text(
        """
        {
            "prefixes": [
                { "ip_prefix": "127.0.0.1" },
                { "ip_prefix": "not a real ipv4 range aws" },
                { "ipv6_prefix": "::1" },
                { "ipv6_prefix": "not a real ipv6 range aws" },
                { "bad": "missing key" }
            ]
        }
        """,
    )

    with working_directory(tmp_path):
        ip_tag.load_aws_ip_ranges()


def test_load_asn_list(tmp_path: Path) -> None:
    (tmp_path / "dat").mkdir()

    fname = tmp_path / "dat" / "test-asn.txt"
    fname.write_text(
        """
        127.0.0.1
        not a real ipv4 range asn
        ::1
        not a real ipv6 range asn
        """,
    )

    ip_tag.load_asn_list("test-tag", str(fname))
    ip_tag.load_asn_list("test-tag", str(fname))


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    # NOTE: load_ip_ranges() is covered by main()
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
