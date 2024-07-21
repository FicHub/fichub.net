from flask import Flask
from flask.testing import FlaskClient
import pytest


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
