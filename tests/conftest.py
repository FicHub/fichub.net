from typing import Any, List
import os
from pathlib import Path
import re

from flask import Flask
from flask.testing import FlaskClient
import oil
import pytest
import testcontainers.postgres
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.response import BaseHTTPResponse

POSTGRES_CONTAINER = None


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


def pytest_configure() -> None:
    global POSTGRES_CONTAINER  # noqa: PLW0603
    POSTGRES_CONTAINER = testcontainers.postgres.PostgresContainer(
        image="postgres:16.3-bookworm",
        username="fichub_test",
        password="fichub_test_pw",
        dbname="fichub_test",
        driver=None,
    )
    POSTGRES_CONTAINER.__enter__()

    psql_url = POSTGRES_CONTAINER.get_connection_url()

    # Extract the host port from the connection string
    r = re.match(r".*:(\d+)/.*", psql_url)
    if r is None:
        msg = f"error: unable to parse sql port from: {psql_url=}"
        raise Exception(msg)  # noqa: TRY002
    port = int(r.group(1))

    # Point any connections opened to the testcontainer.
    os.environ["OIL_DB_HOST"] = "127.0.0.1"
    os.environ["OIL_DB_SSLMODE"] = "disable"
    os.environ["OIL_DB_PORT"] = f"{port}"
    os.environ["OIL_DB_DBNAME"] = "fichub_test"
    os.environ["OIL_DB_USER"] = "fichub_test"
    os.environ["OIL_DB_PASSWORD"] = "fichub_test_pw"

    # Reset oil.oil from environment.
    conn_parms = oil.OilConnectionParameters.fromEnvironment()
    oil.oil = conn_parms

    # Setup the initial schema and do delayed initialization.
    with oil.oil.open() as db, db.cursor() as curs:
        curs.execute(Path("./sql/fichub_net.sql").read_text())
        for i in range(2, 1_000):
            p = Path(f"./sql/upgrade{i}.sql")
            if not p.is_file():
                break
            curs.execute(p.read_text())


def pytest_unconfigure() -> None:
    if POSTGRES_CONTAINER is not None:
        POSTGRES_CONTAINER.__exit__(None, None, None)


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
