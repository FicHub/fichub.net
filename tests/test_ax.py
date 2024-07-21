from typing import Any, Callable, Dict, List, Optional, Tuple, Type
import datetime
import json
import time
from types import TracebackType

import pytest
from requests.auth import HTTPBasicAuth
import responses
from responses import matchers
from responses.registries import OrderedRegistry

import authentications as a
import ax
from db import FicInfo

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
            self.headers: Dict[str, str] = {}

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

    def __enter__(self) -> "AxMock":
        if self.manage_rsps:
            self.rsps.__enter__()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.manage_rsps:
            self.rsps.__exit__(exc_type, exc_value, traceback)

    def matchers(self) -> List[Callable[..., Any]]:
        return [
            matchers.request_kwargs_matcher(self.expected_kwargs),
            matchers.query_param_matcher(self.expected_params),
            matchers.header_matcher(self.expected_headers),
        ]

    def add(self, method: str, url: str, body: Dict[str, Any]) -> None:
        self.rsps.add(
            method,
            url,
            json=body,
            match=self.matchers(),
        )

    def add_delayed(
        self, method: str, url: str, body: Dict[str, Any], delay: float
    ) -> None:
        def request_callback(_request: Any) -> Tuple[int, Dict[str, str], str]:
            time.sleep(delay)
            headers: Dict[str, str] = {}
            return (200, headers, json.dumps(body))

        self.rsps.add_callback(
            method,
            url,
            callback=request_callback,
            content_type="application/json",
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


@pytest.mark.slow()
def test_alive_slow() -> None:
    # OK response that is a little delayed is up
    with AxMock() as rsps:
        rsps.add_delayed("GET", a.AX_STATUS_ENDPOINT, {"err": 0}, 1.0)
        assert ax.alive()

    # OK response that takes too long is down
    with AxMock() as rsps:
        rsps.add_delayed("GET", a.AX_STATUS_ENDPOINT, {"err": 0}, 6.0)
        assert ax.alive()


# TODO: test lookup


def test_requestAllChapters() -> None:
    urlId = "foo"

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{urlId}", {})
        with pytest.raises(KeyError, match="chapters"):
            r = ax.requestAllChapters(urlId, 1)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{urlId}", {"chapters": []})
        with pytest.raises(ax.MissingChapterError, match="missing chapter: 1/1"):
            r = ax.requestAllChapters(urlId, 1)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{urlId}",
            EXAMPLE_FIC_RESPONSE,
        )
        r = ax.requestAllChapters(urlId, 1)
        assert 1 in r
        assert r[1].__dict__ == EXAMPLE_FIC_CHAPTER.__dict__

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{urlId}",
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
        r = ax.requestAllChapters(urlId, 1)
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
def test_requestAllChapters_missing_title(extra: Dict[str, str]) -> None:
    urlId = "foo"
    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{urlId}",
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
        r = ax.requestAllChapters(urlId, 1)
        assert 1 in r
        assert (
            r[1].__dict__
            == ax.Chapter(
                1,
                "Chapter 1",
                "<h2>Chapter 1</h2><p>foo</p>",
            ).__dict__
        )


def test_fetchChapters() -> None:
    urlId = "foo"

    ficInfo = FicInfo(
        urlId,
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
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{urlId}", {})
        with pytest.raises(KeyError, match="chapters"):
            r = ax.fetchChapters(ficInfo)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add("GET", f"{a.AX_FIC_ENDPOINT}/{urlId}", {"chapters": []})
        with pytest.raises(ax.MissingChapterError, match="missing chapter: 1/1"):
            r = ax.fetchChapters(ficInfo)

    with AxMock(expected_timeout=300.0) as rsps:
        rsps.add(
            "GET",
            f"{a.AX_FIC_ENDPOINT}/{urlId}",
            EXAMPLE_FIC_RESPONSE,
        )
        r = ax.fetchChapters(ficInfo)
        assert 1 in r
        assert r[1].__dict__ == EXAMPLE_FIC_CHAPTER.__dict__
