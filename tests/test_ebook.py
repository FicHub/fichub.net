from typing import Tuple
import datetime
from pathlib import Path
import shutil

from flask import Flask
from oil import oil
import pytest

from fichub_net import ax, ebook, util
from fichub_net.db import ExportLog, FicInfo
from tests.test_db import build_test_fic_info, build_test_fic_info_dict


def test_exportVersion() -> None:
    assert ebook.exportVersion("fake-etype", "test-ebook-id-0") == 1
    assert ebook.exportVersion("epub", "test-ebook-id-0") == 2  # noqa: PLR2004

    with oil.open() as db, db.cursor() as curs:
        curs.execute(
            "insert into ficVersionBump(id, value) values(%s, %s)",
            ("test-ebook-id-0", 1),
        )

    assert ebook.exportVersion("epub", "test-ebook-id-0") == 3  # noqa: PLR2004


def test_formatRelDatePart() -> None:
    assert ebook.formatRelDatePart(0, "minute") == ""
    assert ebook.formatRelDatePart(1, "minute") == "1 minute "
    assert ebook.formatRelDatePart(10, "minute") == "10 minutes "


def test_metaDataString() -> None:
    fi = build_test_fic_info("test-ebook-id-1")

    meta0 = ebook.metaDataString(fi)
    assert "test title by test author\n" in meta0
    assert "1123 words in 1 chapters\n" in meta0
    assert "Status: test status\n" in meta0
    assert "Updated: " in meta0
    assert " - today\n" in meta0

    fi.ficUpdated -= datetime.timedelta(hours=10)
    meta0 = ebook.metaDataString(fi)
    assert "Updated: " in meta0
    assert " - today\n" in meta0

    fi.ficUpdated -= datetime.timedelta(days=1)
    meta0 = ebook.metaDataString(fi)
    assert "Updated: " in meta0
    assert " - 1 day  ago\n" in meta0

    fi.ficUpdated -= datetime.timedelta(days=1)
    meta0 = ebook.metaDataString(fi)
    assert "Updated: " in meta0
    assert " - 2 days  ago\n" in meta0


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("test", "test_by_anAuthor-sxyz123"),
        ("test title", "test_title_by_anAuthor-sxyz123"),
        # multiple _ are squeezed
        ("test  __  __--title", "test_--title_by_anAuthor-sxyz123"),
        # non-word characters are dropped
        ("test123 .?!:", "test123_by_anAuthor-sxyz123"),
        ("test123 ❓", "test123_by_anAuthor-sxyz123"),
        # non-ascii is dropped
        ("pingüino", "pingino_by_anAuthor-sxyz123"),
    ],
)
def test_buildFileSlug(title: str, expected: str) -> None:
    assert ebook.buildFileSlug(title, "anAuthor", "sxyz123") == expected


def path_starts_with(haystack: Path, needle: Path) -> bool:
    haystack_parts = haystack.parts
    needle_parts = needle.parts
    return haystack_parts[: len(needle_parts)] == needle_parts


def test_randomTempFile() -> None:
    ebook_tmp = Path(ebook.TMP_DIR)

    test_path = ebook.randomTempFile("test")
    assert len(test_path) > 0
    test_path_obj = Path(test_path)
    assert ebook_tmp.is_dir()
    assert not test_path_obj.is_file()
    assert len(test_path_obj.parts) > len(ebook_tmp.parts)
    assert path_starts_with(test_path_obj, ebook_tmp)

    test_path2_obj = Path(ebook.randomTempFile("test"))
    assert not test_path2_obj.is_file()
    assert len(test_path2_obj.parts) > len(ebook_tmp.parts)
    assert path_starts_with(test_path2_obj, ebook_tmp)

    assert test_path2_obj != test_path_obj


EXPORT_PATH_TEST_CASES = [
    ("abc", ("epub/abc/abc", "epub/abc/abc")),
    ("abcd", ("epub/abc/d/abcd", "epub/abc/d/abcd")),
    ("abcdef", ("epub/abc/def/abcdef", "epub/abc/def/abcdef")),
    ("abcdefhi", ("epub/abc/def/hi/abcdefhi", "epub/abc/def/hi/abcdefhi")),
]


@pytest.mark.parametrize(("urlId", "expected"), EXPORT_PATH_TEST_CASES)
def test_buildExportPath(urlId: str, expected: Tuple[str, str]) -> None:
    expected = (
        f"{ebook.PRIMARY_CACHE_DIR}/{expected[0]}",
        f"{ebook.SECONDARY_CACHE_DIR}/{expected[1]}",
    )
    assert ebook.buildExportPath("epub", urlId, create=False) == expected


@pytest.mark.parametrize(
    ("etype", "fhash", "suff"),
    [
        ("epub", "hashfoohash", ".epub"),
        ("html", "hashbarhash", ".zip"),
    ],
)
@pytest.mark.parametrize(("urlId", "expected"), EXPORT_PATH_TEST_CASES)
def test_buildExportName(
    etype: str, fhash: str, suff: str, urlId: str, expected: Tuple[str, str]
) -> None:
    names = ebook.buildExportName(etype, urlId, fhash, create=False)
    expected = (
        f"{ebook.PRIMARY_CACHE_DIR}/{expected[0]}",
        f"{ebook.SECONDARY_CACHE_DIR}/{expected[1]}",
    )
    expected = (
        expected[0].replace("/epub/", f"/{etype}/"),
        expected[1].replace("/epub/", f"/{etype}/"),
    )
    assert names[0] == f"{expected[0]}/{fhash}{suff}"
    assert names[1] == f"{expected[1]}/{fhash}{suff}"


def test_finalizeExport(tmp_path: Path) -> None:
    etype, urlId, ihash = ("epub", "test-ebook-id-2", "inputhash1")

    with pytest.raises(FileNotFoundError, match="does-not-exist"):
        ebook.finalizeExport(
            etype, urlId, "inputhash0", str(tmp_path / "does-not-exist.epub")
        )

    test_content = "test epub content"
    test_hash = "c20dfa655c0afb3c19d88eb083f1b4d4"
    tname = tmp_path / "test.epub"

    assert not tname.is_file()
    tname.write_text(test_content)
    assert tname.is_file()

    version = ebook.exportVersion(etype, urlId)
    el = ExportLog.lookup(urlId, version, etype, ihash)
    assert el is None

    fname, fhash = ebook.finalizeExport(etype, urlId, ihash, str(tname))
    assert fname.startswith(ebook.PRIMARY_CACHE_DIR)
    assert fhash == test_hash
    assert not tname.is_file()
    assert Path(fname).is_file()
    assert Path(fname).read_text() == test_content

    # no FicInfo present, case shouldn't happen unless we failed to test createHtmlBundle, convertEpub, createEpub
    el = ExportLog.lookup(urlId, version, etype, ihash)
    assert el is None

    # With FicInfo, ExportLog should be created
    FicInfo.save(build_test_fic_info_dict(urlId))

    tname.write_text(test_content)
    assert tname.is_file()

    fname2, fhash2 = ebook.finalizeExport(etype, urlId, ihash, str(tname))
    assert fname2 == fname
    assert fhash2 == fhash

    el = ExportLog.lookup(urlId, version, etype, ihash)
    assert el is not None
    assert el.exportHash == test_hash


def test_findExistingExport() -> None:
    etype, urlId, ihash = ("epub", "test-ebook-id-2", "inputhash1")
    version = ebook.exportVersion(etype, urlId)

    el = ExportLog.lookup(urlId, version, etype, ihash)
    assert el is not None

    assert ebook.findExistingExport("pdf", urlId, ihash) is None
    assert ebook.findExistingExport(etype, "not-test-ebook-id-2", ihash) is None
    assert ebook.findExistingExport(etype, urlId, "not-the-ihash") is None

    res = ebook.findExistingExport(etype, urlId, ihash)
    assert res is not None
    assert Path(res[0]).is_file()
    assert util.hashFile(res[0]) == el.exportHash
    assert res[1] == el.exportHash

    # Move the export to its secondary path to verify it'll get moved.
    _, sfpath = ebook.buildExportPath(etype, urlId)
    if not Path(sfpath).is_dir():
        Path(sfpath).mkdir(parents=True)

    _, sfname = ebook.buildExportName(etype, urlId, el.exportHash)
    shutil.move(res[0], sfname)

    res2 = ebook.findExistingExport(etype, urlId, ihash)
    assert res2 is not None
    assert Path(res2[0]).is_file()
    assert res2 == res

    # Files that don't exist should return None.
    Path(res2[0]).unlink()
    assert ebook.findExistingExport(etype, urlId, ihash) is None


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (
            datetime.datetime(1000, 2, 3, tzinfo=datetime.timezone.utc),
            (1000, 2, 3, 0, 0, 0),
        ),
        (
            datetime.datetime(2000, 2, 3, tzinfo=datetime.timezone.utc),
            (2000, 2, 3, 0, 0, 0),
        ),
        (
            datetime.datetime(7, 2, 3, 4, tzinfo=datetime.timezone.utc),
            (7, 2, 3, 4, 0, 0),
        ),
        (
            datetime.datetime(7, 2, 3, 4, 5, tzinfo=datetime.timezone.utc),
            (7, 2, 3, 4, 5, 0),
        ),
        (
            datetime.datetime(7, 2, 3, 4, 5, 6, tzinfo=datetime.timezone.utc),
            (7, 2, 3, 4, 5, 6),
        ),
    ],
)
def test_datetimeToZipDateTime(
    dt: datetime.datetime, expected: ebook.ZipDateTime
) -> None:
    assert ebook.datetimeToZipDateTime(dt) == expected


def test_buildEpubChapters() -> None:
    chapters = {
        1: ax.Chapter(1, "first chapter", "<p>foo</p>"),
        3: ax.Chapter(3, "3rd chapter", "<p>foo3</p>"),
        9: ax.Chapter(1, "9th chapter", "<p>foo9</p>"),
    }

    res = ebook.buildEpubChapters(chapters)

    assert res.keys() == chapters.keys()
    for cid in res:
        assert res[cid].title == chapters[cid].title
        assert res[cid].content == chapters[cid].content
        assert res[cid].lang == "en"
        assert res[cid].file_name == f"chap_{cid}.xhtml"


def test_createEpub(app: Flask) -> None:
    chapters = {
        1: ax.Chapter(1, "first chapter", "<p>foo</p>"),
        3: ax.Chapter(3, "3rd chapter", "<p>foo3</p>"),
        9: ax.Chapter(1, "9th chapter", "<p>foo9</p>"),
    }
    etype, urlId, expected_hash = (
        "epub",
        "test-ebook-id-3",
        "cb4a68c3180ccf2a5583762113c68c29",
    )
    version = ebook.exportVersion(etype, urlId)

    fi_dict = build_test_fic_info_dict(urlId)
    fi = FicInfo.parse(fi_dict)
    ihash = fi.contentHash
    assert ihash is not None

    expected_fname_str, _ = ebook.buildExportName(etype, urlId, expected_hash)
    expected_fname = Path(expected_fname_str)
    assert not expected_fname.is_file()

    # TODO: don't require an app context for render_template? Does this enable
    # changing the cwd, and could be used for epub_style.css too?
    with pytest.raises(RuntimeError, match="Working outside of application context"):
        ebook.createEpub(fi, chapters)

    with app.app_context():
        fname, fhash = ebook.createEpub(fi, chapters)
        assert Path(fname).is_file()
        assert fname == expected_fname_str
        assert fhash == expected_hash

        assert util.hashFile(fname) == expected_hash

        # Without a FicInfo record, no ExportLog will be created.
        assert ExportLog.lookup(urlId, version, etype, ihash) is None

        # With a FicInfo, an ExportLog will be created.
        FicInfo.save(fi_dict)

        fname2, fhash2 = ebook.createEpub(fi, chapters)
        assert fname2 == fname
        assert fhash2 == fhash

        el = ExportLog.lookup(urlId, version, etype, ihash)
        assert el is not None
        assert el.exportHash == expected_hash

    # TODO: epubcheck?


# TODO: test createHtmlBundle, calls createEpub
def test_createHtmlBundle(app: Flask) -> None:
    chapters = {
        1: ax.Chapter(1, "1st chapter", "<p>bar</p>"),
        3: ax.Chapter(3, "third chapter", "<p>bar3</p>"),
        8: ax.Chapter(1, "eigth chapter", "<p>bar8</p>"),
    }
    etype, urlId, ihash, expected_hash = (
        "html",
        "test-ebook-id-4",
        "756a51b394ed51cf34465da8d1196eb0",
        "144679f465f2fa01af21b72721b6efdd",
    )
    version = ebook.exportVersion(etype, urlId)

    fi_dict = build_test_fic_info_dict(urlId)
    fi = FicInfo.parse(fi_dict)

    expected_fname_str, _ = ebook.buildExportName(etype, urlId, expected_hash)
    expected_fname = Path(expected_fname_str)
    assert not expected_fname.is_file()

    # TODO: see comment in test_createEpub
    with pytest.raises(RuntimeError, match="Working outside of application context"):
        ebook.createHtmlBundle(fi, chapters)

    with app.app_context():
        fname, fhash = ebook.createHtmlBundle(fi, chapters)
        assert Path(fname).is_file()
        assert fname == expected_fname_str
        assert fhash == expected_hash

        assert util.hashFile(fname) == expected_hash

        # Unlinking the bundle will recreate it.
        Path(fname).unlink()
        assert not Path(fname).is_file()

        fname3, fhash3 = ebook.createHtmlBundle(fi, chapters)
        assert Path(fname3).is_file()
        assert fname3 == fname
        assert fhash3 == fhash

        # Without a FicInfo record, no ExportLog will be generated.
        epub_ihash = fi.contentHash
        assert epub_ihash is not None
        epub_version = ebook.exportVersion("epub", urlId)
        assert ExportLog.lookup(urlId, epub_version, "epub", epub_ihash) is None
        assert ExportLog.lookup(urlId, version, etype, ihash) is None

        # With a FicInfo, an ExportLog will be created.
        FicInfo.save(fi_dict)

        fname4, fhash4 = ebook.createHtmlBundle(fi, chapters)
        assert fname4 == fname
        assert fhash4 == fhash

        assert ExportLog.lookup(urlId, epub_version, "epub", epub_ihash) is not None
        el = ExportLog.lookup(urlId, version, etype, ihash)
        assert el is not None
        assert el.exportHash == expected_hash

        # The existing export should be found now that we have an ExportLog.
        fname2, fhash2 = ebook.createHtmlBundle(fi, chapters)
        assert Path(fname2).is_file()
        assert fname2 == fname
        assert fhash2 == fhash


def test_convertEpub(app: Flask) -> None:
    chapters = {
        1: ax.Chapter(1, "1st chapter", "<p>buzz</p>"),
        4: ax.Chapter(3, "fourth chapter", "<p>buzz4</p>"),
    }
    etype, urlId, _ihash, _expected_hash = (
        "pdf",
        "test-ebook-id-5",
        "f34818f906acc9f1959295d0f30994f9",
        "todo-pdf-hash",
    )
    _version = ebook.exportVersion(etype, urlId)

    fi_dict = build_test_fic_info_dict(urlId)
    fi = FicInfo.parse(fi_dict)

    with pytest.raises(ebook.InvalidETypeError, match="invalid etype: not-an-etype"):
        ebook.convertEpub(fi, chapters, "not-an-etype")

    # TODO: see comment in test_createEpub
    with pytest.raises(RuntimeError, match="Working outside of application context"):
        ebook.convertEpub(fi, chapters, etype)

    with app.app_context():
        pass  # TODO: test convertEpub, calls janus
