from typing import Any, List

from flask import Flask
from flask.testing import FlaskClient
import pytest
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.response import BaseHTTPResponse


def by_slow_marker(item: pytest.Item) -> int:
    return 0 if item.get_closest_marker("slow") is None else 1


def pytest_collection_modifyitems(items: List[pytest.Item]) -> None:
    items.sort(key=by_slow_marker, reverse=False)


@pytest.fixture(autouse=True)
def _no_http_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    allowed_hosts = {"localhost"}
    original_urlopen = HTTPConnectionPool.urlopen

    def urlopen_mock(
        self: HTTPConnectionPool, method: str, url: str, *args: Any, **kwargs: Any
    ) -> BaseHTTPResponse:
        if self.host in allowed_hosts:
            return original_urlopen(self, method, url, *args, **kwargs)

        msg = f"error: test was about to {method} {self.scheme}://{self.host}{url}"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "urllib3.connectionpool.HTTPConnectionPool.urlopen", urlopen_mock
    )


@pytest.fixture()
def app() -> Flask:
    from main import app

    app.config.update(
        {
            "TESTING": True,
        }
    )

    return app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()
