#!./venv/bin/python
from typing import Any
from collections.abc import Iterator
import sys
import time
import traceback

from elasticsearch import Elasticsearch
import elasticsearch.helpers

import fichub_net.authentications as a
from fichub_net.db import FicBlacklist, FicInfo

RR_SOURCE_ID = 19


def plog(msg: str) -> None:
    # TODO: actually log too
    print(f"{int(time.time())}|{msg}")


def drop_index(es: Any) -> None:
    es.indices.delete(index="fi")


def create_index(es: Any) -> None:
    # TODO: DeprecationWarning: The 'body' parameter is deprecated and will be
    # removed in a future version. Instead use individiual parameters.
    es.indices.create(
        index="fi",
        body={
            "settings": {
                "analysis": {
                    "analyzer": {
                        "default": {"type": "standard"},
                    },
                },
            },
            "mappings": {
                "properties": {
                    "urlId": {"type": "text"},
                    "created": {"type": "date"},
                    "updated": {"type": "date"},
                    "title": {"type": "text"},
                    "author": {"type": "text"},
                    "chapters": {"type": "long"},
                    "words": {"type": "long"},
                    "description": {"type": "text"},
                    "ficCreated": {"type": "date"},
                    "ficUpdated": {"type": "date"},
                    "status": {"type": "text"},
                    "source": {"type": "text"},
                },
            },
        },
    )


def search(q: str, limit: int = 10) -> list[FicInfo]:
    try:
        es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
        res = es.search(
            index="fi",
            body={
                "query": {
                    "multi_match": {
                        "query": q,
                        "analyzer": "standard",
                    },
                },
                "size": limit,
            },
        )
        print(f"es.search({q}) => {res['hits']['total']['value']} hits")
        fis: list[FicInfo] = []
        for hit in res["hits"]["hits"]:
            if len(fis) >= limit:
                break
            fis += FicInfo.select(hit["_id"])
        return fis[:limit]
    except Exception as e:
        traceback.print_exc()
        print(e)
        print(f"es.search({q}): ^ something went wrong searching es data :/")
        return []  # TODO: return something distinct the caller can use


def save(fi: FicInfo) -> None:
    es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
    r = handle_fic_info(fi)
    _id = r.pop("_id", fi.id)
    es.index(index="fi", id=_id, body=r)


def handle_fic_info(fi: FicInfo) -> dict[str, Any]:
    _id = fi.id
    r = dict(fi.__dict__)
    r["urlId"] = r.pop("id", None)
    r["_id"] = _id
    return r


def blacklist(url_id: str) -> None:
    es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)
    es.delete(index="fi", id=url_id)


def generate_fic_info() -> Iterator[dict[str, Any]]:
    for fi in FicInfo.select():
        if fi.source_id == RR_SOURCE_ID:
            continue
        if FicBlacklist.greylisted(fi.id):
            plog(f"greylisted: {fi.id}")
            continue
        if FicBlacklist.blacklisted(fi.id):
            plog(f"blacklisted: {fi.id}")
            continue
        plog(f"  indexing {fi.id}")
        yield handle_fic_info(fi)


def main(argv: list[str]) -> int:
    if len(argv) not in {1}:
        print(f"usage: {argv[0]}")
        return 1

    es = Elasticsearch(hosts=a.ELASTICSEARCH_HOSTS)

    drop_indexes = False
    if drop_indexes:
        drop_index(es)

    if not es.indices.exists(index="fi"):
        create_index(es)

    success = False
    cnt = 0
    for t in range(10):
        if success:
            break
        if t > 0:
            time.sleep(5)
        try:
            elasticsearch.helpers.bulk(
                client=es, index="fi", actions=generate_fic_info()
            )
            cnt += 1
            success = True
        except SystemExit:
            raise
        except Exception:
            plog("  trouble")
            plog(traceback.format_exc())
    if not success:
        plog("  permanent trouble")
        msg = "block failed"
        raise Exception(msg)  # noqa: TRY002

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
