from typing import Any
from collections.abc import Callable
import datetime
import json
import time
from types import TracebackType

from elasticsearch import Elasticsearch
from oil import oil
import pytest
from requests.auth import HTTPBasicAuth
import responses
from responses import matchers
from responses.registries import OrderedRegistry
from typing_extensions import Self

from fichub_net import ax, es
import fichub_net.authentications as a
from fichub_net.db import AuthorBlacklist, FicBlacklist, FicBlacklistReason, FicInfo
from tests.test_db import build_test_fic_info_dict

EXPECTED_AX_USER_AGENT = "fichub.net/0.1.0"

EXAMPLE_FIC_RESPONSE = {
    "chapters": [
        {
            "chapterId": 1,
            "title": "first chapter",
            "content": "<p>foo</p>",
        }
    ]
}
EXAMPLE_FIC_CHAPTER = ax.Chapter(
    1,
    "first chapter",
    "<h2>first chapter</h2><p>foo</p>",
)


def basic_auth_value(username: str, password: str) -> str:
    class Req:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    r = Req()
    HTTPBasicAuth(username, password)(r)
    return r.headers["Authorization"]


class AxMock:
    def __init__(
        self,
        expected_timeout: float = 5.0,
        rsps: responses.RequestsMock | None = None,
        manage_rsps: bool | None = None,
    ) -> None:
        self.expected_timeout = expected_timeout
        self.rsps = (
            rsps
            if rsps is not None
            else responses.RequestsMock(registry=OrderedRegistry)
        )
        self.manage_rsps = manage_rsps if manage_rsps is not None else (rsps is None)

        self.expected_kwargs = {"timeout": self.expected_timeout}
        self.expected_params = {"apiKey": a.AX_API_KEY}
        self.expected_headers = {
            "User-Agent": EXPECTED_AX_USER_AGENT,
            "Authorization": basic_auth_value(a.AX_USER, a.AX_PASS),
        }

    def __enter__(self) -> Self:
        if self.manage_rsps:
            self.rsps.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.manage_rsps:
            self.rsps.__exit__(exc_type, exc_value, traceback)

    def matchers(self) -> list[Callable[..., Any]]:
        return [
            matchers.request_kwargs_matcher(self.expected_kwargs),
            matchers.query_param_matcher(self.expected_params),
            matchers.header_matcher(self.expected_headers),
        ]

    def add(self, method: str, url: str, body: dict[str, Any]) -> None:
        self.rsps.add(
            method,
            url,
            json=body,
            match=self.matchers(),
        )

    def add_delayed(
        self, method: str, url: str, body: dict[str, Any], delay: float
    ) -> None:
        def request_callback(_request: Any) -> tuple[int, dict[str, str], str]:
            time.sleep(delay)
            headers: dict[str, str] = {}
            return (200, headers, json.dumps(body))

        self.rsps.add_callback(
            method,
            url,
            callback=request_callback,
            content_type="application/json",
            match=self.matchers(),
        )

    def add_raw(self, method: str, url: str, body: str) -> None:
        self.rsps.add(
            method,
            url,
            body=body,
            match=self.matchers(),
        )


def test_alive() -> None:
    # initial request blocked, results in False
    assert not ax.alive()

    # Response with an err is down
    with AxMock() as rsps:
        rsps.add("GET", a.AX_STATUS_ENDPOINT, {"err": 1})
        assert not ax.alive()

    # Response with no err is up
    with AxMock() as rsps:
        rsps.add("GET", a.AX_STATUS_ENDPOINT, {})
        assert ax.alive()

    # Response with 0 err is up
    with AxMock() as rsps:
        rsps.add("GET", a.AX_STATUS_ENDPOINT, {"err": 0})
        assert ax.alive()


@pytest.mark.slow
def test_alive_slow() -> None:
    # OK response that is a little delayed is up
    with AxMock() as rsps:
        rsps.add_delayed("GET", a.AX_STATUS_ENDPOINT, {"err": 0}, 1.0)
        assert ax.alive()

    # OK response that takes too long is down
    with AxMock() as rsps:
        rsps.add_delayed("GET", a.AX_STATUS_ENDPOINT, {"err": 0}, 6.0)
        assert ax.alive()


def test_lookup() -> None:
    query = "test/lookup bar"
    quoted_query = "test%2Flookup%20bar"

    # Simple error cases.
    with AxMock(expected_timeout=200.0) as rsps:
        rsps.add("GET", f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}", {"err": -1})
        r = ax.lookup(query, 200.0)
        assert r == {"err": -1}

    with AxMock(expected_timeout=280.0) as rsps:
        rsps.add("GET", f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}", {"error": -2})
        r = ax.lookup(query)
        assert r == {"err": -2}

    # Response missing fields.
    with AxMock(expected_timeout=280.0) as rsps:
        rsps.add("GET", f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}", {"urlId": "fooax1"})
        with pytest.raises(KeyError, match="sourceId"):
            r = ax.lookup(query)

    with AxMock(expected_timeout=280.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}",
            {"urlId": "fooax1", "sourceId": 1},
        )
        with pytest.raises(KeyError, match="authorId"):
            r = ax.lookup(query)

    # Unavailable exports.
    with AxMock(expected_timeout=280.0) as rsps:
        FicInfo.save(build_test_fic_info_dict("fooax3"))
        FicBlacklist.save("fooax3", FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value)
        fi_dict = build_test_fic_info_dict("fooax3")

        rsps.add("GET", f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}", fi_dict)
        r = ax.lookup(query)
        assert r == ax.FIC_UNAVAILABLE_ERROR

    with AxMock(expected_timeout=280.0) as rsps:
        fi_dict = build_test_fic_info_dict("fooax4")
        fi_dict["sourceId"] = "10"
        fi_dict["authorId"] = "2001"
        AuthorBlacklist.save(
            int(fi_dict["sourceId"]),
            int(fi_dict["authorId"]),
            FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value,
        )

        rsps.add("GET", f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}", fi_dict)
        r = ax.lookup(query)
        assert r == ax.FIC_UNAVAILABLE_ERROR

        fis = FicInfo.select("fooax4")
        assert len(fis) == 0

        # Delete the author entry so we don't impact other tests.
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                "delete from authorBlacklist where sourceId = %s and authorId = %s",
                (int(fi_dict["sourceId"]), int(fi_dict["authorId"])),
            )

    # Successful (probably without elastic search).
    with AxMock(expected_timeout=280.0) as rsps:
        fi_dict = build_test_fic_info_dict("fooax0")
        rsps.add("GET", f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}", fi_dict)
        r = ax.lookup(query)
        assert r == fi_dict

        fis = FicInfo.select("fooax0")
        assert len(fis) == 1


@pytest.mark.elasticsearch
def test_lookup_es(elastic_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    _ = elastic_url  # suppress unused argument

    query = "test/lookup bar"
    quoted_query = "test%2Flookup%20bar"

    with AxMock(expected_timeout=280.0) as rsps:
        fi_dict = build_test_fic_info_dict("fooax2")
        rsps.add("GET", f"{a.AX_LOOKUP_ENDPOINT}/{quoted_query}", fi_dict)
        r = ax.lookup(query)
        assert r == fi_dict

        with capsys.disabled():
            captured = capsys.readouterr()
            assert captured.out.find("something went wrong") == -1

        fis = FicInfo.select("fooax2")
        assert len(fis) == 1

        # Force a refresh so we can actually see the doc we just indexed.
        assert a.ELASTICSEARCH_HOSTS != []
        test_es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
        test_es.indices.refresh(index="fi")

        assert len(es.search("fooax2")) == 1


def test_request_all_chapters() -> None:
    url_id = "foo"

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{url_id}", {})
        with pytest.raises(KeyError, match="chapters"):
            r = ax.request_all_chapters(url_id, 1)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{url_id}", {"chapters": []})
        with pytest.raises(ax.MissingChapterError, match="missing chapter: 1/1"):
            r = ax.request_all_chapters(url_id, 1)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{url_id}",
            EXAMPLE_FIC_RESPONSE,
        )
        r = ax.request_all_chapters(url_id, 1)
        assert 1 in r
        assert r[1].__dict__ == EXAMPLE_FIC_CHAPTER.__dict__

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{url_id}",
            {
                "chapters": [
                    {
                        "chapterId": 1,
                        "title": "first chapter",
                        "content": "",
                    }
                ]
            },
        )
        r = ax.request_all_chapters(url_id, 1)
        assert 1 in r
        assert (
            r[1].__dict__
            == ax.Chapter(
                1,
                "first chapter",
                "<h2>first chapter</h2><p></p>",
            ).__dict__
        )


@pytest.mark.parametrize("extra", [{}, {"title": ""}])
def test_request_all_chapters_missing_title(extra: dict[str, str]) -> None:
    url_id = "foo"
    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{url_id}",
            {
                "chapters": [
                    {
                        "chapterId": 1,
                        "content": "<p>foo</p>",
                    }
                    | extra
                ]
            },
        )
        r = ax.request_all_chapters(url_id, 1)
        assert 1 in r
        assert (
            r[1].__dict__
            == ax.Chapter(
                1,
                "Chapter 1",
                "<h2>Chapter 1</h2><p>foo</p>",
            ).__dict__
        )


def test_fetch_chapters() -> None:
    url_id = "foo"

    fic_info = FicInfo(
        url_id,
        datetime.datetime.now(tz=datetime.timezone.utc),
        datetime.datetime.now(tz=datetime.timezone.utc),
        "test title",
        "test author",
        1,
        1_123,
        "test description",
        datetime.datetime.now(tz=datetime.timezone.utc),
        datetime.datetime.now(tz=datetime.timezone.utc),
        "test status",
        "test source",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{url_id}", {})
        with pytest.raises(KeyError, match="chapters"):
            r = ax.fetch_chapters(fic_info)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{url_id}", {"chapters": []})
        with pytest.raises(ax.MissingChapterError, match="missing chapter: 1/1"):
            r = ax.fetch_chapters(fic_info)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{url_id}",
            EXAMPLE_FIC_RESPONSE,
        )
        r = ax.fetch_chapters(fic_info)
        assert 1 in r
        assert r[1].__dict__ == EXAMPLE_FIC_CHAPTER.__dict__
