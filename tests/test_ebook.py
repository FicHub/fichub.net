import datetime
from pathlib import Path
import shutil

from flask import Flask
from oil import oil
import pytest

from fichub_net import ax, ebook, util
from fichub_net.db import ExportLog, FicInfo
from tests.test_db import build_test_fic_info, build_test_fic_info_dict


def test_export_version() -> None:
    assert ebook.export_version("fake-etype", "test-ebook-id-0") == 1
    assert ebook.export_version("epub", "test-ebook-id-0") == 2  # noqa: PLR2004

    with oil.open() as db, db.cursor() as curs:
        curs.execute(
            "insert into ficVersionBump(id, value) values(%s, %s)",
            ("test-ebook-id-0", 1),
        )

    assert ebook.export_version("epub", "test-ebook-id-0") == 3  # noqa: PLR2004


def test_format_rel_date_part() -> None:
    assert ebook.format_rel_date_part(0, "minute") == ""
    assert ebook.format_rel_date_part(1, "minute") == "1 minute "
    assert ebook.format_rel_date_part(10, "minute") == "10 minutes "


def test_metadata_string() -> None:
    fi = build_test_fic_info("test-ebook-id-1")

    meta0 = ebook.metadata_string(fi)
    assert "test title by test author\n" in meta0
    assert "1123 words in 1 chapters\n" in meta0
    assert "Status: test status\n" in meta0
    assert "Updated: " in meta0
    assert " - today\n" in meta0

    fi.fic_updated -= datetime.timedelta(hours=10)
    meta0 = ebook.metadata_string(fi)
    assert "Updated: " in meta0
    assert " - today\n" in meta0

    fi.fic_updated -= datetime.timedelta(days=1)
    meta0 = ebook.metadata_string(fi)
    assert "Updated: " in meta0
    assert " - 1 day  ago\n" in meta0

    fi.fic_updated -= datetime.timedelta(days=1)
    meta0 = ebook.metadata_string(fi)
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
def test_build_file_slug(title: str, expected: str) -> None:
    assert ebook.build_file_slug(title, "anAuthor", "sxyz123") == expected


def path_starts_with(haystack: Path, needle: Path) -> bool:
    haystack_parts = haystack.parts
    needle_parts = needle.parts
    return haystack_parts[: len(needle_parts)] == needle_parts


def test_random_temp_file() -> None:
    ebook_tmp = Path(ebook.TMP_DIR)

    test_path = ebook.random_temp_file("test")
    assert len(str(test_path)) > 0
    assert ebook_tmp.is_dir()
    assert not test_path.is_file()
    assert len(test_path.parts) > len(ebook_tmp.parts)
    assert path_starts_with(test_path, ebook_tmp)

    test_path2 = ebook.random_temp_file("test")
    assert not test_path2.is_file()
    assert len(test_path2.parts) > len(ebook_tmp.parts)
    assert path_starts_with(test_path2, ebook_tmp)

    assert test_path2 != test_path


EXPORT_PATH_TEST_CASES = [
    ("abc", ("epub/abc/abc", "epub/abc/abc")),
    ("abcd", ("epub/abc/d/abcd", "epub/abc/d/abcd")),
    ("abcdef", ("epub/abc/def/abcdef", "epub/abc/def/abcdef")),
    ("abcdefhi", ("epub/abc/def/hi/abcdefhi", "epub/abc/def/hi/abcdefhi")),
]


@pytest.mark.parametrize(("url_id", "expected"), EXPORT_PATH_TEST_CASES)
def test_build_export_path(url_id: str, expected: tuple[str, str]) -> None:
    expected_objs = (
        Path(ebook.PRIMARY_CACHE_DIR) / expected[0],
        Path(ebook.SECONDARY_CACHE_DIR) / expected[1],
    )
    assert ebook.build_export_path("epub", url_id, create=False) == expected_objs


@pytest.mark.parametrize(
    ("etype", "fhash", "suff"),
    [
        ("epub", "hashfoohash", ".epub"),
        ("html", "hashbarhash", ".zip"),
    ],
)
@pytest.mark.parametrize(("url_id", "expected"), EXPORT_PATH_TEST_CASES)
def test_build_export_name(
    etype: str, fhash: str, suff: str, url_id: str, expected: tuple[str, str]
) -> None:
    names = ebook.build_export_name(etype, url_id, fhash, create=False)
    expected = (
        f"{ebook.PRIMARY_CACHE_DIR}/{expected[0]}",
        f"{ebook.SECONDARY_CACHE_DIR}/{expected[1]}",
    )
    expected = (
        expected[0].replace("/epub/", f"/{etype}/"),
        expected[1].replace("/epub/", f"/{etype}/"),
    )
    assert names[0] == Path(f"{expected[0]}/{fhash}{suff}")
    assert names[1] == Path(f"{expected[1]}/{fhash}{suff}")


def test_finalize_export(tmp_path: Path) -> None:
    etype, url_id, ihash = ("epub", "test-ebook-id-2", "inputhash1")

    with pytest.raises(FileNotFoundError, match="does-not-exist"):
        ebook.finalize_export(
            etype, url_id, "inputhash0", tmp_path / "does-not-exist.epub"
        )

    test_content = "test epub content"
    test_hash = "c20dfa655c0afb3c19d88eb083f1b4d4"
    tname = tmp_path / "test.epub"

    assert not tname.is_file()
    tname.write_text(test_content)
    assert tname.is_file()

    version = ebook.export_version(etype, url_id)
    el = ExportLog.lookup(url_id, version, etype, ihash)
    assert el is None

    fname, fhash = ebook.finalize_export(etype, url_id, ihash, tname)
    assert str(fname).startswith(ebook.PRIMARY_CACHE_DIR)
    assert fhash == test_hash
    assert not tname.is_file()
    assert fname.is_file()
    assert fname.read_text() == test_content

    # no FicInfo present, case shouldn't happen unless we failed to test create_html_bundle, convert_epub, create_epub
    el = ExportLog.lookup(url_id, version, etype, ihash)
    assert el is None

    # With FicInfo, ExportLog should be created
    FicInfo.save(build_test_fic_info_dict(url_id))

    tname.write_text(test_content)
    assert tname.is_file()

    fname2, fhash2 = ebook.finalize_export(etype, url_id, ihash, tname)
    assert fname2 == fname
    assert fhash2 == fhash

    el = ExportLog.lookup(url_id, version, etype, ihash)
    assert el is not None
    assert el.exportHash == test_hash


def test_find_existing_export() -> None:
    etype, url_id, ihash = ("epub", "test-ebook-id-2", "inputhash1")
    version = ebook.export_version(etype, url_id)

    el = ExportLog.lookup(url_id, version, etype, ihash)
    assert el is not None

    assert ebook.find_existing_export("pdf", url_id, ihash) is None
    assert ebook.find_existing_export(etype, "not-test-ebook-id-2", ihash) is None
    assert ebook.find_existing_export(etype, url_id, "not-the-ihash") is None

    res = ebook.find_existing_export(etype, url_id, ihash)
    assert res is not None
    assert Path(res[0]).is_file()
    assert util.hash_file(res[0]) == el.exportHash
    assert res[1] == el.exportHash

    # Move the export to its secondary path to verify it'll get moved.
    _, sfpath = ebook.build_export_path(etype, url_id)
    if not Path(sfpath).is_dir():
        Path(sfpath).mkdir(parents=True)

    _, sfname = ebook.build_export_name(etype, url_id, el.exportHash)
    shutil.move(res[0], sfname)

    res2 = ebook.find_existing_export(etype, url_id, ihash)
    assert res2 is not None
    assert Path(res2[0]).is_file()
    assert res2 == res

    # Files that don't exist should return None.
    Path(res2[0]).unlink()
    assert ebook.find_existing_export(etype, url_id, ihash) is None


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
def test_datetime_to_zip_datetime(
    dt: datetime.datetime, expected: ebook.ZipDateTime
) -> None:
    assert ebook.datetime_to_zip_datetime(dt) == expected


def test_build_epub_chapters() -> None:
    chapters = {
        1: ax.Chapter(1, "first chapter", "<p>foo</p>"),
        3: ax.Chapter(3, "3rd chapter", "<p>foo3</p>"),
        9: ax.Chapter(1, "9th chapter", "<p>foo9</p>"),
    }

    res = ebook.build_epub_chapters(chapters)

    assert res.keys() == chapters.keys()
    for cid in res:
        assert res[cid].title == chapters[cid].title
        assert res[cid].content == chapters[cid].content
        assert res[cid].lang == "en"
        assert res[cid].file_name == f"chap_{cid}.xhtml"


def test_create_epub(app: Flask) -> None:
    chapters = {
        1: ax.Chapter(1, "first chapter", "<p>foo</p>"),
        3: ax.Chapter(3, "3rd chapter", "<p>foo3</p>"),
        9: ax.Chapter(1, "9th chapter", "<p>foo9</p>"),
    }
    etype, url_id, expected_hash = (
        "epub",
        "test-ebook-id-3",
        "cb4a68c3180ccf2a5583762113c68c29",
    )
    version = ebook.export_version(etype, url_id)

    fi_dict = build_test_fic_info_dict(url_id)
    fi = FicInfo.parse(fi_dict)
    ihash = fi.content_hash
    assert ihash is not None

    expected_fname_str, _ = ebook.build_export_name(etype, url_id, expected_hash)
    expected_fname = Path(expected_fname_str)
    assert not expected_fname.is_file()

    # TODO: don't require an app context for render_template? Does this enable
    # changing the cwd, and could be used for epub_style.css too?
    with pytest.raises(RuntimeError, match="Working outside of application context"):
        ebook.create_epub(fi, chapters)

    with app.app_context():
        fname, fhash = ebook.create_epub(fi, chapters)
        assert Path(fname).is_file()
        assert fname == expected_fname_str
        assert fhash == expected_hash

        assert util.hash_file(fname) == expected_hash

        # Without a FicInfo record, no ExportLog will be created.
        assert ExportLog.lookup(url_id, version, etype, ihash) is None

        # With a FicInfo, an ExportLog will be created.
        FicInfo.save(fi_dict)

        fname2, fhash2 = ebook.create_epub(fi, chapters)
        assert fname2 == fname
        assert fhash2 == fhash

        el = ExportLog.lookup(url_id, version, etype, ihash)
        assert el is not None
        assert el.exportHash == expected_hash

    # TODO: epubcheck?


# TODO: test create_html_bundle, calls create_epub
def test_create_html_bundle(app: Flask) -> None:
    chapters = {
        1: ax.Chapter(1, "1st chapter", "<p>bar</p>"),
        3: ax.Chapter(3, "third chapter", "<p>bar3</p>"),
        8: ax.Chapter(1, "eigth chapter", "<p>bar8</p>"),
    }
    etype, url_id, ihash, expected_hash = (
        "html",
        "test-ebook-id-4",
        "756a51b394ed51cf34465da8d1196eb0",
        "144679f465f2fa01af21b72721b6efdd",
    )
    version = ebook.export_version(etype, url_id)

    fi_dict = build_test_fic_info_dict(url_id)
    fi = FicInfo.parse(fi_dict)

    expected_fname_str, _ = ebook.build_export_name(etype, url_id, expected_hash)
    expected_fname = Path(expected_fname_str)
    assert not expected_fname.is_file()

    # TODO: see comment in test_create_epub
    with pytest.raises(RuntimeError, match="Working outside of application context"):
        ebook.create_html_bundle(fi, chapters)

    with app.app_context():
        fname, fhash = ebook.create_html_bundle(fi, chapters)
        assert Path(fname).is_file()
        assert fname == expected_fname_str
        assert fhash == expected_hash

        assert util.hash_file(fname) == expected_hash

        # Unlinking the bundle will recreate it.
        Path(fname).unlink()
        assert not Path(fname).is_file()

        fname3, fhash3 = ebook.create_html_bundle(fi, chapters)
        assert Path(fname3).is_file()
        assert fname3 == fname
        assert fhash3 == fhash

        # Without a FicInfo record, no ExportLog will be generated.
        epub_ihash = fi.content_hash
        assert epub_ihash is not None
        epub_version = ebook.export_version("epub", url_id)
        assert ExportLog.lookup(url_id, epub_version, "epub", epub_ihash) is None
        assert ExportLog.lookup(url_id, version, etype, ihash) is None

        # With a FicInfo, an ExportLog will be created.
        FicInfo.save(fi_dict)

        fname4, fhash4 = ebook.create_html_bundle(fi, chapters)
        assert fname4 == fname
        assert fhash4 == fhash

        assert ExportLog.lookup(url_id, epub_version, "epub", epub_ihash) is not None
        el = ExportLog.lookup(url_id, version, etype, ihash)
        assert el is not None
        assert el.exportHash == expected_hash

        # The existing export should be found now that we have an ExportLog.
        fname2, fhash2 = ebook.create_html_bundle(fi, chapters)
        assert Path(fname2).is_file()
        assert fname2 == fname
        assert fhash2 == fhash


def test_convert_epub(app: Flask) -> None:
    chapters = {
        1: ax.Chapter(1, "1st chapter", "<p>buzz</p>"),
        4: ax.Chapter(3, "fourth chapter", "<p>buzz4</p>"),
    }
    etype, url_id, _ihash, _expected_hash = (
        "pdf",
        "test-ebook-id-5",
        "f34818f906acc9f1959295d0f30994f9",
        "todo-pdf-hash",
    )
    _version = ebook.export_version(etype, url_id)

    fi_dict = build_test_fic_info_dict(url_id)
    fi = FicInfo.parse(fi_dict)

    with pytest.raises(ebook.InvalidETypeError, match="invalid etype: not-an-etype"):
        ebook.convert_epub(fi, chapters, "not-an-etype")

    # TODO: see comment in test_create_epub
    with pytest.raises(RuntimeError, match="Working outside of application context"):
        ebook.convert_epub(fi, chapters, etype)

    with app.app_context():
        pass  # TODO: test convert_epub, calls janus
