from typing import TYPE_CHECKING, Any
import os
from pathlib import Path
import re

if TYPE_CHECKING:
    from collections.abc import Iterator

import oil
import pytest
import testcontainers.elasticsearch
import testcontainers.postgres
from urllib3.connectionpool import HTTPConnectionPool

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient
    from urllib3.response import BaseHTTPResponse

POSTGRES_CONTAINER = None


def by_slow_marker(item: pytest.Item) -> int:
    return 0 if item.get_closest_marker("slow") is None else 1


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Order slow tests last.
    items.sort(key=by_slow_marker, reverse=False)

    # Add the elasticsearch marker to any test using the elastic_url fixture.
    for item in items:
        if "elastic_url" in getattr(item, "fixturenames", ()):
            item.add_marker("elasticsearch")
            # These tests themselves aren't very slow, but ES takes ~10s to spin up
            item.add_marker("slow")


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


@pytest.fixture(scope="session", autouse=True)
def _tmp_ebook_dirs(tmp_path_factory: pytest.TempPathFactory) -> None:
    from fichub_net import ebook  # noqa: PLC0415

    tmp_path = tmp_path_factory.mktemp("tmp_ebook_cache_dir")
    primary = tmp_path / "primary" / "cache"
    secondary = tmp_path / "secondary" / "cache"

    ebook.PRIMARY_CACHE_DIR = str(primary)
    ebook.SECONDARY_CACHE_DIR = str(secondary)

    ebook_tmp_dir = tmp_path_factory.mktemp("tmp_ebook_tmp_dir")
    ebook.TMP_DIR = str(ebook_tmp_dir)


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
    conn_parms = oil.OilConnectionParameters.from_environment()
    oil.oil = conn_parms

    # Setup the initial schema and do delayed initialization.
    with oil.oil.open() as db, db.cursor() as curs:
        curs.execute(Path("./sql/fichub_net.sql").read_text())
        for i in range(2, 1_000):
            p = Path(f"./sql/upgrade{i}.sql")
            if not p.is_file():
                break
            curs.execute(p.read_text())

        curs.execute(Path("./sql/limiter.sql").read_text())


def pytest_unconfigure() -> None:
    if POSTGRES_CONTAINER is not None:
        POSTGRES_CONTAINER.__exit__(None, None, None)


@pytest.fixture(scope="session")
def elastic_url() -> Iterator[str]:
    with testcontainers.elasticsearch.ElasticSearchContainer(
        image="elasticsearch:8.8.0",
        mem_limit="1G",
    ) as elastic_container:
        host = elastic_container.get_container_host_ip()
        port = elastic_container.get_exposed_port(elastic_container.port)

        url = f"http://{host}:{port}"

        from fichub_net import authentications  # noqa: PLC0415

        authentications.ELASTICSEARCH_HOSTS = [url]

        yield url


@pytest.fixture
def app() -> Flask:
    from fichub_net.main import app as fichub_app  # noqa: PLC0415

    fichub_app.config.update(
        {
            "TESTING": True,
        }
    )

    return fichub_app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()
