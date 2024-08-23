from http import HTTPStatus

from flask.testing import FlaskClient
import pytest

from fichub_net import main


def test_uwsgi_init() -> None:
    main.uwsgi_init()


@pytest.mark.parametrize("suff", ["", "/"])
def test_search_author_404(client: FlaskClient, suff: str) -> None:
    response = client.get(f"/search/author{suff}")
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("q", ["foo", "bar"])
def test_search_author(client: FlaskClient, q: str) -> None:
    response = client.get(f"/search/author/{q}")
    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == "/"


@pytest.mark.parametrize("year", ["1", "2024"])
@pytest.mark.parametrize("month", ["1", "10"])
@pytest.mark.parametrize("day", ["1", "10"])
@pytest.mark.parametrize("page", ["", "2", "100"])
def test_cache_listing(
    client: FlaskClient, year: str, month: str, day: str, page: str
) -> None:
    response = client.get(f"/cache/{year}/{month}/{day}/{page}")
    assert (response.status_code, response.headers["Location"]) == (
        HTTPStatus.FOUND,
        "/",
    )


@pytest.mark.parametrize("page", ["", "2", "100"])
def test_cache_listing_today(client: FlaskClient, page: str) -> None:
    response = client.get(f"/cache/today/{page}")
    assert (response.status_code, response.headers["Location"]) == (
        HTTPStatus.FOUND,
        "/",
    )


@pytest.mark.parametrize("page", ["", "2", "100"])
def test_cache_listing_deprecated(client: FlaskClient, page: str) -> None:
    response = client.get(f"/cache/{page}")
    assert (response.status_code, response.headers["Location"]) == (
        HTTPStatus.FOUND,
        "/",
    )


def test_404(client: FlaskClient) -> None:
    response = client.get("/testing/not-a-real-path")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert b"FicHub" in response.data
    assert b"The requested URL was not found on the server" in response.data
    assert b"please check your spelling and try again." in response.data
    assert b"Need to report an issue," in response.data


@pytest.mark.parametrize("page", ["", "2", "100"])
def test_popular_listing(client: FlaskClient, page: str) -> None:
    response = client.get(f"/popular/{page}")
    assert response.status_code == HTTPStatus.OK
    assert b"FicHub" in response.data
    assert b"Fic.AI" in response.data
    assert b"Need to report an issue," in response.data
