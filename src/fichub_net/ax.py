from typing import Any
import contextlib
import traceback
import urllib.parse

from fichub_net import es, util
import fichub_net.authentications as a
from fichub_net.db import AuthorBlacklist, FicBlacklist, FicInfo

FIC_UNAVAILABLE_ERROR = {
    "ret": 5,
    "err": -7,
    "msg": "exports are unavailable for this fic, possibly due to author request",
}


class MissingChapterError(Exception):
    pass


def alive() -> bool:
    with contextlib.suppress(Exception):
        m = util.reqJson(a.AX_STATUS_ENDPOINT, timeout=5.0)
        return "err" not in m or str(m["err"]) == "0"
    return False


def lookup(query: str, timeout: float = 280.0) -> dict[str, Any]:
    url_q = urllib.parse.quote(query, safe="")
    url = f"{a.AX_LOOKUP_ENDPOINT}/{url_q}"
    meta = util.reqJson(url, timeout=timeout)
    if "error" in meta and "err" not in meta:
        meta["err"] = meta.pop("error", None)
    if "err" not in meta:
        if FicBlacklist.check(meta["urlId"]) or AuthorBlacklist.check(
            meta["sourceId"], meta["authorId"]
        ):
            return FIC_UNAVAILABLE_ERROR
        FicInfo.save(meta)
        try:
            fis = FicInfo.select(meta["urlId"])
            es.save(fis[0])
        except Exception as e:
            traceback.print_exc()
            print(e)
            print("lookup: ^ something went wrong saving es data :/")
    return meta


class Chapter:
    def __init__(self, n: int, title: str, content: str) -> None:
        self.n = n
        self.title = title
        self.content = content


def requestAllChapters(urlId: str, expected: int) -> dict[int, Chapter]:
    url = f"{a.AX_FIC_ENDPOINT}/{urlId}"
    res = util.reqJson(url)
    chapters = {}
    titles = []
    for ch in res["chapters"]:
        n = int(ch["chapterId"])

        # generate a chapter name if its missing
        title = str(ch["title"]).strip() if "title" in ch else None
        titles.append(title)
        if title is None or len(title) < 1:
            title = f"Chapter {n}"

        # extract chapter content and prepend with chapter title header
        titleHeader = f"<h2>{title}</h2>"
        content = titleHeader + str(ch["content"]).strip()
        if len(content) <= len(titleHeader):
            print(f"note: {url} {n} has an empty content body")
            content += "<p></p>"
        ch["content"] = None

        chapters[n] = Chapter(n, title, content)

    # ensure we got the number of expected chapters
    for i in range(1, expected + 1):
        if i not in chapters:
            print(f"requestAllChapters: err: {i} not in chapters")
            print(list(chapters.keys()))
            msg = f"err: missing chapter: {i}/{expected}"
            raise MissingChapterError(msg)

    return chapters


def fetchChapters(info: FicInfo) -> dict[int, Chapter]:
    # try to grab all chapters with the new /all endpoint first
    try:
        return requestAllChapters(info.id, info.chapters)
    except Exception as e:
        traceback.print_exc()
        print(e)
        print("fetchChapters: ^ something went wrong :/")
        raise
