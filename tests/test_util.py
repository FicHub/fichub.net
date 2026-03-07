from pathlib import Path

import pytest

from fichub_net import util
import fichub_net.authentications as a
from tests.test_ax import AxMock


def test_hash_file(tmp_path: Path) -> None:
    p = tmp_path / "test.txt"
    p.write_text("foo bar baz")
    assert p.read_text() == "foo bar baz"
    assert len(list(tmp_path.iterdir())) == 1

    assert (
        util.hash_file(str(tmp_path / "test.txt")) == "ab07acbb1e496801937adfa772424bf7"
    )

    with pytest.raises(FileNotFoundError, match="not-test.txt"):
        util.hash_file(str(tmp_path / "not-test.txt"))


def test_req_json() -> None:
    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", a.AX_STATUS_ENDPOINT, {})
        r = util.req_json(a.AX_STATUS_ENDPOINT)
        assert r == {}

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", a.AX_STATUS_ENDPOINT, {"foo": "bar"})
        r = util.req_json(a.AX_STATUS_ENDPOINT)
        assert r == {"foo": "bar"}

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add_raw("GET", a.AX_STATUS_ENDPOINT, "not json")
        r = util.req_json(a.AX_STATUS_ENDPOINT, retry_count=0)
        assert r == {
            "err": -1,
            "msg": "req_json: received status code: 200",
        }

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add_raw("GET", a.AX_STATUS_ENDPOINT, "not json")
        rsps.add("GET", a.AX_STATUS_ENDPOINT, {"foo": "bar"})
        r = util.req_json(a.AX_STATUS_ENDPOINT, retry_count=1)
        assert r == {"foo": "bar"}
