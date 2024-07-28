import contextlib

import elasticsearch
from elasticsearch import Elasticsearch
import pytest

import authentications as a
from db import FicInfo
import es
from tests.test_db import build_test_fic_info, build_test_fic_info_dict


@pytest.fixture(autouse=True)
def use_elastic_url(
    elastic_url: str,
) -> str:
    return elastic_url


def test_reset_es() -> None:
    # If a test that uses es has already run in another module we may already
    # have an index implicitly created, delete it now to ensure we start in a
    # clean state.
    test_es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
    with contextlib.suppress(elasticsearch.NotFoundError):
        es.dropIndex(test_es)


def test_search_before_init(capsys: pytest.CaptureFixture[str]) -> None:
    assert es.search("test") == []

    with capsys.disabled():
        captured = capsys.readouterr()
        assert captured.out != ""
        assert captured.out.find("something went wrong") >= 0
        assert captured.out.find("index_not_found_exception") >= 0
        assert captured.err != ""
        assert captured.err.find("index_not_found_exception") >= 0


def test_dropIndex_before_init() -> None:
    test_es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
    with pytest.raises(elasticsearch.NotFoundError, match="no such index"):
        es.dropIndex(test_es)


def test_createIndex() -> None:
    test_es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
    es.createIndex(test_es)


def test_search_no_results(capsys: pytest.CaptureFixture[str]) -> None:
    assert es.search("test") == []

    with capsys.disabled():
        captured = capsys.readouterr()
        assert captured.out == "es.search(test) => 0 hits\n"
        assert captured.err == ""


def test_handleFicInfo() -> None:
    fi = build_test_fic_info("fooes")
    fi_doc = es.handleFicInfo(fi)
    assert fi_doc["_id"] == "fooes"
    assert fi_doc["urlId"] == "fooes"


def test_save() -> None:
    es.save(build_test_fic_info("fooes"))
    es.save(build_test_fic_info("fooes2"))
    es.save(build_test_fic_info("fooes3"))

    # Force a refresh so we can actually see the doc we just indexed.
    assert a.ELASTICSEARCH_HOSTS != []
    test_es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
    test_es.indices.refresh(index="fi")

    res = test_es.get(index="fi", id="fooes")
    assert res["_source"]["title"] == "test title"

    stats = test_es.indices.stats(index="fi")
    assert stats["_all"]["total"]["docs"]["count"] == 3  # noqa: PLR2004
    assert stats["_all"]["total"]["docs"]["deleted"] == 0


def test_search_no_fic_info() -> None:
    assert len(es.search("test")) == 0
    assert len(es.search("test", 0)) == 0


def test_search() -> None:
    FicInfo.save(build_test_fic_info_dict("fooes"))
    assert len(es.search("test")) == 1
    assert len(es.search("test", 0)) == 0
    assert len(es.search("test", 1)) == 1

    FicInfo.save(build_test_fic_info_dict("fooes2"))
    assert len(es.search("test")) == 2  # noqa: PLR2004
    assert len(es.search("test", 0)) == 0
    assert len(es.search("test", 1)) == 1


def test_blacklist() -> None:
    es.blacklist("fooes2")

    # Force a refresh so we can actually observe the delete.
    assert a.ELASTICSEARCH_HOSTS != []
    test_es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
    test_es.indices.refresh(index="fi")

    stats = test_es.indices.stats(index="fi")
    assert stats["_all"]["total"]["docs"]["count"] == 2  # noqa: PLR2004
    assert stats["_all"]["total"]["docs"]["deleted"] > 0

    # Check that search has updated.
    assert len(es.search("test")) == 1
    assert len(es.search("test", 0)) == 0
    assert len(es.search("test", 1)) == 1
