from typing import Iterator

from flask import Flask
from flask.testing import FlaskClient
import pytest


@pytest.fixture()
def app() -> Iterator[Flask]:
    from main import app

    app.config.update(
        {
            "TESTING": True,
        }
    )

    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()
