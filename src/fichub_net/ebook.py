from typing import TYPE_CHECKING
import datetime
import os
import pathlib
from pathlib import Path
import random
import re
import shutil
import subprocess
import threading
import traceback
import zipfile

from dateutil.relativedelta import relativedelta
from ebooklib import epub
from flask import render_template

from fichub_net import util
from fichub_net.db import ExportLog, FicVersionBump

if TYPE_CHECKING:
    from fichub_net.ax import Chapter, FicInfo

TMP_DIR = "tmp"
PRIMARY_CACHE_DIR = "/mnt/selene_fichub/cache"
SECONDARY_CACHE_DIR = "/mnt/atem_fichub/cache"

DEFAULT_JANUS_PATH = "/home/fichub/fichub.net/janus.py"

# total version is EXPORT_VERSION + EXPORT_TYPE_VERSIONS[etype]
EXPORT_VERSION = 1
EXPORT_TYPES = ["epub", "html", "mobi", "pdf"]
EXPORT_TYPE_VERSIONS = {
    "epub": 1,
    "html": 1,
    "mobi": 0,
    "pdf": 0,
}
EXPORT_SUFFIXES = {
    "epub": ".epub",
    "html": ".zip",
    "mobi": ".mobi",
    "pdf": ".pdf",
}
EXPORT_MIMETYPES = {
    "epub": "application/epub+zip",
    "html": "application/zip",
    "mobi": "application/x-mobipocket-ebook",
    "pdf": "application/pdf",
}
# TODO: the frontend should not have its own copy here
EXPORT_DESCRIPTIONS = {
    "epub": "EPUB",
    "html": "zipped HTML",
    "mobi": "MOBI",
    "pdf": "PDF",
}


class InvalidETypeError(Exception):
    pass


class JanusError(Exception):
    pass


def export_version(etype: str, url_id: str) -> int:
    res = EXPORT_VERSION
    if etype in EXPORT_TYPE_VERSIONS:
        res += EXPORT_TYPE_VERSIONS[etype]
    for fvb in FicVersionBump.select(url_id):
        res += fvb.value
    return res


def format_rel_date_part(val: int, which: str) -> str:
    return f"{val} {which}{'s' if val > 1 else ''} " if val > 0 else ""


def metadata_string(info: FicInfo) -> str:
    diff = relativedelta(datetime.datetime.now(tz=datetime.UTC), info.fic_updated)
    parts = [
        (diff.years, "year"),
        (diff.months, "month"),
        (diff.days, "day"),
    ]
    diff_string = ""
    for val, which in parts:
        diff_string += format_rel_date_part(val, which)
    if len(diff_string) < 1:
        diff_string = "today"
    else:
        diff_string += " ago"

    return "\n".join(
        [
            f"{info.title} by {info.author}",
            f"{info.words} words in {info.chapters} chapters",
            f"Status: {info.status}",
            f"Updated: {info.fic_updated.date()} - {diff_string}",
            "",
        ]
    )


def build_file_slug(title: str, author: str, url_id: str) -> str:
    slug = f"{title} by {author}"
    slug = re.sub(r"[^\w\-_]+", "_", slug)
    slug = re.sub("_+", "_", slug)
    slug = slug.strip("_")
    try:
        t = slug.encode("utf-8").decode("ascii", "ignore")
        slug = t
    except Exception:
        pass
    return f"{slug}-{url_id}"


def random_temp_file(extra: str, bits: int = 32) -> Path:
    tdir = Path(TMP_DIR) / str(os.getpid())
    if not tdir.is_dir():
        tdir.mkdir(parents=True)
    rbits = random.getrandbits(bits)
    fname = f"{threading.get_ident()}_{rbits:x}_{extra}"
    return tdir / fname


def build_export_path(
    etype: str, url_id: str, create: bool = False
) -> tuple[Path, Path]:
    url_id = url_id.lower()
    parts = [etype]
    parts.extend(url_id[i : i + 3] for i in range(0, len(url_id), 3))
    parts.append(url_id)
    fdir = Path(PRIMARY_CACHE_DIR).joinpath(*parts)
    if create and not fdir.is_dir():
        fdir.mkdir(parents=True)
    sfdir = Path(SECONDARY_CACHE_DIR).joinpath(*parts)
    return fdir, sfdir


def build_export_name(
    etype: str, url_id: str, fhash: str, create: bool = False
) -> tuple[Path, Path]:
    fdir, sfdir = build_export_path(etype, url_id, create)
    suff = EXPORT_SUFFIXES[etype]
    return (fdir / f"{fhash}{suff}"), (sfdir / f"{fhash}{suff}")


def finalize_export(
    etype: str, url_id: str, ihash: str, tname: Path
) -> tuple[Path, str]:
    fhash = util.hash_file(tname)
    fname, _ = build_export_name(etype, url_id, fhash, create=True)
    shutil.move(tname, fname)

    # record this result so we can immediately return it next time, assuming the
    # input hash and export version have not changed
    try:
        n = datetime.datetime.now(tz=datetime.UTC)
        el = ExportLog(url_id, export_version(etype, url_id), etype, ihash, fhash, n)
        el.upsert()
    except Exception as e:
        traceback.print_exc()
        print(e)
        print("finalize_export: ^ something went wrong :/")

    return (fname, fhash)


def find_existing_export(
    etype: str, url_id: str, ihash: str
) -> tuple[Path, str] | None:
    try:
        el = ExportLog.lookup(url_id, export_version(etype, url_id), etype, ihash)
        if el is None:
            return None
        fname, sfname = build_export_name(etype, url_id, el.exportHash)
        if not fname.is_file() and sfname.is_file():
            _, _ = build_export_path(etype, url_id, True)
            try:
                shutil.move(sfname, fname)
            except Exception as ie:
                traceback.print_exc()
                print(ie)
                print(
                    "find_existing_export: ^ something went wrong trying to move existing export :/"
                )
        if not fname.is_file():
            return None
        return (fname, el.exportHash)
    except Exception as e:
        traceback.print_exc()
        print(e)
        print("find_existing_export: ^ something went wrong :/")
    return None


ZipDateTime = tuple[int, int, int, int, int, int]


def datetime_to_zip_datetime(ts: datetime.datetime) -> ZipDateTime:
    return (ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second)


def create_html_bundle(info: FicInfo, chapters: dict[int, Chapter]) -> tuple[Path, str]:
    slug = build_file_slug(info.title, info.author, info.id)
    bundle_fname = slug + ".html"

    _, ehash = create_epub(info, chapters)
    ee = find_existing_export("html", info.id, ehash)
    if ee is not None:
        return ee

    tmp_fname = random_temp_file(f"{info.id}.zip")

    nchaps = chapters.values()
    data = render_template("full_fic.html", info=info, chapters=nchaps)
    with zipfile.ZipFile(tmp_fname, "w") as zf:
        zinfo = zipfile.ZipInfo(
            bundle_fname, datetime_to_zip_datetime(info.fic_updated)
        )
        zf.writestr(zinfo, data, compress_type=zipfile.ZIP_DEFLATED)

    return finalize_export("html", info.id, ehash, tmp_fname)


def convert_epub(
    info: FicInfo, chapters: dict[int, Chapter], etype: str
) -> tuple[Path, str]:
    if etype not in EXPORT_TYPES:
        msg = f"convert_epub: invalid etype: {etype}"
        raise InvalidETypeError(msg)

    suff = EXPORT_SUFFIXES[etype]
    tmp_fname = random_temp_file(f"{info.id}{suff}")

    epub_fname, ehash = create_epub(info, chapters)
    ee = find_existing_export(etype, info.id, ehash)
    if ee is not None:
        return ee

    timeout = (60 * 5) - 10
    if "CONVERT_TIMEOUT" in os.environ:
        timeout = int(os.environ["CONVERT_TIMEOUT"])

    janus_path = DEFAULT_JANUS_PATH
    if "JANUS_PATH" in os.environ:
        janus_path = os.environ["JANUS_PATH"]

    res = subprocess.run(
        [janus_path, epub_fname, tmp_fname],
        timeout=timeout,
        check=False,
    )
    if res.returncode != 0:
        msg = f"convert_epub: error: return code {res.returncode} != 0"
        raise JanusError(msg)

    return finalize_export(etype, info.id, ehash, tmp_fname)


def build_epub_chapters(chapters: dict[int, Chapter]) -> dict[int, epub.EpubHtml]:
    epub_chapters = {}
    for n, ch in chapters.items():
        c = epub.EpubHtml(title=ch.title, file_name=f"chap_{n}.xhtml", lang="en")
        c.title = ch.title
        c.content = ch.content
        epub_chapters[n] = c
    return epub_chapters


def create_epub(info: FicInfo, raw_chapters: dict[int, Chapter]) -> tuple[Path, str]:
    print(info.__dict__)

    book = epub.EpubBook()
    # set metadata
    book.set_identifier(info.id)
    book.set_title(info.title)
    book.set_language("en")
    book.add_author(info.author)
    book.add_metadata("DC", "description", info.description)

    # document style
    doc_style = epub.EpubItem(
        uid="doc_style",
        file_name="style/main.css",
        media_type="text/css",
        content=pathlib.Path("epub_style.css").read_text(),
    )
    book.add_item(doc_style)

    # define CSS style
    style = "BODY {color: white;}"
    nav_css = epub.EpubItem(
        uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style
    )

    # add CSS file
    book.add_item(nav_css)

    # introduction
    intro = epub.EpubHtml(
        title="Introduction", file_name="introduction.xhtml", lang="en"
    )
    intro.content = render_template("epub_introduction.html", info=info)
    book.add_item(intro)

    # nav page
    nav_page = epub.EpubNav(uid="nav", file_name="nav.xhtml")
    nav_page.add_item(doc_style)
    book.add_item(nav_page)

    # actual chapter content
    chapters = build_epub_chapters(raw_chapters)
    for _, c in sorted(chapters.items()):
        c.add_item(doc_style)
        book.add_item(c)

    # define Table Of Contents
    book.toc = [
        epub.Link("introduction.xhtml", "Introduction", "intro"),
        *list(chapters.values()),
    ]

    # basic spine
    book.spine = [intro, nav_page, *list(chapters.values())]

    # add default NCX file
    book.add_item(epub.EpubNcx())

    tmp_fname = random_temp_file(f"{info.id}.epub")
    epub.write_epub(
        tmp_fname, book, {"mtime": info.fic_updated, "play_order": {"enabled": True}}
    )

    ihash = "upstream" if info.content_hash is None else info.content_hash
    return finalize_export("epub", info.id, ihash, tmp_fname)
