from typing import Dict, Optional
import datetime
import json

from oil import oil
import psycopg2.errors
import pytest

from fichub_net.db import (
    AuthorBlacklist,
    ExportLog,
    FicBlacklist,
    FicBlacklistReason,
    FicInfo,
    FicVersionBump,
    RequestLog,
    RequestSource,
)


def build_test_fic_info_dict(url_id: str) -> Dict[str, str]:
    return {
        "urlId": url_id,
        "title": "test title",
        "author": "test author",
        "chapters": "1",
        "words": "1123",
        "desc": "test description",
        "published": "1721500000000",
        "updated": "1721600000000",
        "status": "test status",
        "source": "test source",
        "sourceId": "1",
        "authorId": "1000",
        "contentHash": "test-hash",
    }


def build_test_fic_info(url_id: str) -> FicInfo:
    return FicInfo(
        url_id,
        datetime.datetime.now(tz=datetime.timezone.utc),
        datetime.datetime.now(tz=datetime.timezone.utc),
        "test title",
        "test author",
        1,
        1_123,
        "test description",
        datetime.datetime.now(tz=datetime.timezone.utc),
        datetime.datetime.now(tz=datetime.timezone.utc),
        "test status",
        "test source",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


class TestExportLog:
    def test_init(self) -> None:
        _el = ExportLog(
            "foo",
            1,
            "epub",
            "ex-hash",
            "ex-out-hash",
            datetime.datetime.now(tz=datetime.timezone.utc),
        )

    @staticmethod
    def test_lookup_not_found() -> None:
        el = ExportLog.lookup("foo", 1, "epub", "ex-hash")
        assert el is None

    def test_upsert_foreign_key_violation(self) -> None:
        el = ExportLog(
            "foo",
            1,
            "epub",
            "ex-hash",
            "ex-out-hash",
            datetime.datetime.now(tz=datetime.timezone.utc),
        )
        with pytest.raises(
            psycopg2.errors.ForeignKeyViolation,
            match=r"\(urlid\)=\(foo\) is not present",
        ):
            el.upsert()

    def test_upsert(self) -> None:
        FicInfo.save(build_test_fic_info_dict("foo"))

        el0 = ExportLog(
            "foo",
            1,
            "epub",
            "ex-hash",
            "ex-out-hash",
            datetime.datetime.now(tz=datetime.timezone.utc),
        )
        el0.upsert()

        el1 = ExportLog.lookup("foo", 1, "epub", "ex-hash")
        assert el1 is not None
        assert el1.__dict__ == el0.__dict__


class TestFicVersionBump:
    def test_init(self) -> None:
        _fvb = FicVersionBump("foo2", 1)

    @staticmethod
    def test_select() -> None:
        fvbs = FicVersionBump.select("foo2")
        assert len(fvbs) == 0

        expected_value = 2
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                "insert into ficVersionBump(id, value) values('foo2', %s)",
                (expected_value,),
            )

        fvbs = FicVersionBump.select("foo2")
        assert len(fvbs) == 1
        fvb = fvbs[0]
        assert fvb.value == expected_value


class TestFicInfo:
    def test_init(self) -> None:
        build_test_fic_info("foo3")

    def test_toJson(self) -> None:
        fic_info = build_test_fic_info("foo3")
        expected_extended_meta = {"foo": "bar", "foos": [1, 2, 3]}
        fic_info.rawExtendedMeta = json.dumps(expected_extended_meta)

        j = fic_info.toJson()
        assert j["id"] == "foo3"

        expected = fic_info.__dict__
        expected["created"] = expected["ficCreated"].isoformat()
        expected["updated"] = expected["ficUpdated"].isoformat()
        expected["rawExtendedMeta"] = expected_extended_meta

        for k in j:
            assert j[k] == expected[k]

        # Test when rawExtendedMeta cannot be parsed
        fic_info.rawExtendedMeta = "not json"
        j = fic_info.toJson()
        assert j["rawExtendedMeta"] is None

        # Test when rawExtendedMeta is empty
        fic_info.rawExtendedMeta = ""
        j = fic_info.toJson()
        assert j["rawExtendedMeta"] is None

    @staticmethod
    def test_select_empty() -> None:
        fis = FicInfo.select("foo3")
        assert len(fis) == 0

    @staticmethod
    def test_save() -> None:
        FicInfo.save(build_test_fic_info_dict("foo3"))

    @staticmethod
    def test_select() -> None:
        fis = FicInfo.select("foo3")
        assert len(fis) == 1

    @staticmethod
    def test_parse() -> None:
        fi_dict = build_test_fic_info_dict("foo3")
        fi = FicInfo.parse(fi_dict)
        assert fi.extraMeta is None
        assert fi.rawExtendedMeta is None

        fi_dict["extraMeta"] = ""
        fi = FicInfo.parse(fi_dict)
        assert fi.extraMeta is None

        fi_dict["extraMeta"] = "bar"
        fi = FicInfo.parse(fi_dict)
        assert fi.extraMeta == "bar"

        fi_dict["rawExtendedMeta"] = ""
        fi = FicInfo.parse(fi_dict)
        assert fi.rawExtendedMeta is None

        fi_dict["rawExtendedMeta"] = "baz"
        fi = FicInfo.parse(fi_dict)
        assert fi.rawExtendedMeta == "baz"


class TestFicBlacklist:
    def test_init(self) -> None:
        _fb = FicBlacklist(
            "foo4",
            datetime.datetime.now(tz=datetime.timezone.utc),
            datetime.datetime.now(tz=datetime.timezone.utc),
            FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value,
        )

    @staticmethod
    def test_save() -> None:
        FicInfo.save(build_test_fic_info_dict("foo4_greylist"))
        FicBlacklist.save(
            "foo4_greylist", FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value
        )

        FicInfo.save(build_test_fic_info_dict("foo4_blacklist"))
        FicBlacklist.save(
            "foo4_blacklist", FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value
        )

        FicInfo.save(build_test_fic_info_dict("foo4_multiple"))
        FicBlacklist.save(
            "foo4_multiple", FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value
        )
        FicBlacklist.save(
            "foo4_multiple", FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value
        )

        FicInfo.save(build_test_fic_info_dict("foo4_raptr"))
        FicBlacklist.save(
            "foo4_raptr",
            FicBlacklistReason.REAL_AUTHOR_PLAGIRAISM_TAKEDOWN_REQUEST.value,
        )

    @staticmethod
    def test_select() -> None:
        fbs = FicBlacklist.select("foo4_ok")
        assert len(fbs) == 0

        fbs = FicBlacklist.select("foo4_greylist")
        assert len(fbs) == 1

        fbs = FicBlacklist.select("foo4_blacklist")
        assert len(fbs) == 1

        fbs = FicBlacklist.select("foo4_multiple")
        assert len(fbs) == 2  # noqa: PLR2004

    @staticmethod
    @pytest.mark.parametrize(
        ("url_id", "reason", "expected"),
        [
            ("foo4_ok", None, False),
            ("foo4_ok", FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, False),
            ("foo4_ok", FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, False),
            ("foo4_greylist", None, True),
            ("foo4_greylist", FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, True),
            ("foo4_greylist", FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, False),
            ("foo4_blacklist", None, True),
            ("foo4_blacklist", FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, False),
            ("foo4_blacklist", FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, True),
            ("foo4_multiple", None, True),
            ("foo4_multiple", FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, True),
            ("foo4_multiple", FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, True),
        ],
    )
    def test_check(
        url_id: str, reason: Optional[FicBlacklistReason], expected: bool
    ) -> None:
        ir = None if reason is None else reason.value
        assert FicBlacklist.check(url_id, ir) is expected

    @staticmethod
    def test_blacklisted() -> None:
        assert FicBlacklist.blacklisted("foo4_ok") is False
        assert FicBlacklist.blacklisted("foo4_greylist") is False
        assert FicBlacklist.blacklisted("foo4_blacklist") is True
        assert FicBlacklist.blacklisted("foo4_multiple") is True

    @staticmethod
    def test_greylisted() -> None:
        assert FicBlacklist.greylisted("foo4_ok") is False
        assert FicBlacklist.greylisted("foo4_greylist") is True
        assert FicBlacklist.greylisted("foo4_blacklist") is False
        assert FicBlacklist.greylisted("foo4_multiple") is True
        assert FicBlacklist.greylisted("foo4_raptr") is True


class TestAuthorBlacklist:
    def test_init(self) -> None:
        AuthorBlacklist(
            1,
            1001,
            datetime.datetime.now(tz=datetime.timezone.utc),
            datetime.datetime.now(tz=datetime.timezone.utc),
            5,
        )

    @staticmethod
    def test_save() -> None:
        AuthorBlacklist.save(1, 1001, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value)
        AuthorBlacklist.save(2, 1002, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value)
        AuthorBlacklist.save(1, 1003, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value)
        AuthorBlacklist.save(1, 1003, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value)

    @staticmethod
    @pytest.mark.parametrize(
        ("source_id", "author_id", "expected_len"),
        [
            (None, None, 4),
            (1, None, 3),
            (2, None, 1),
            (None, 1001, 1),
            (None, 1003, 2),
            (1, 1003, 2),
            (2, 1003, 0),
            (1, 1000, 0),
        ],
    )
    def test_select(
        source_id: Optional[int], author_id: Optional[int], expected_len: int
    ) -> None:
        assert len(AuthorBlacklist.select(source_id, author_id)) == expected_len

    @staticmethod
    @pytest.mark.parametrize(
        ("source_id", "author_id", "reason", "expected"),
        [
            (1, 1000, None, False),
            (1, 1000, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, False),
            (1, 1000, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, False),
            (1, 1001, None, True),
            (2, 1001, None, False),
            (1, 1001, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, True),
            (1, 1001, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, False),
            (2, 1002, None, True),
            (2, 1002, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, False),
            (2, 1002, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, True),
            (1, 1003, None, True),
            (1, 1003, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST, True),
            (1, 1003, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST, True),
        ],
    )
    def test_check(
        source_id: int,
        author_id: int,
        reason: Optional[FicBlacklistReason],
        expected: bool,
    ) -> None:
        ir = None if reason is None else reason.value
        assert AuthorBlacklist.check(source_id, author_id, ir) is expected

    @staticmethod
    @pytest.mark.parametrize(
        ("source_id", "author_id", "expected"),
        [
            (1, 1000, False),
            (1, 1001, True),
            (2, 1001, False),
            (1, 1002, False),
            (2, 1002, False),
            (1, 1003, True),
            (2, 1003, False),
        ],
    )
    def test_blacklisted(
        source_id: int,
        author_id: int,
        expected: bool,
    ) -> None:
        assert AuthorBlacklist.blacklisted(source_id, author_id) is expected

    @staticmethod
    @pytest.mark.parametrize(
        ("source_id", "author_id", "expected"),
        [
            (1, 1000, False),
            (1, 1001, False),
            (2, 1001, False),
            (1, 1002, False),
            (2, 1002, True),
            (1, 1003, True),
            (2, 1003, False),
        ],
    )
    def test_greylisted(
        source_id: int,
        author_id: int,
        expected: bool,
    ) -> None:
        assert AuthorBlacklist.greylisted(source_id, author_id) is expected


class TestRequestSource:
    def test_init(self) -> None:
        RequestSource(
            1,
            datetime.datetime.now(tz=datetime.timezone.utc),
            False,
            "http://localhost",
            "127.0.0.1",
        )

    @staticmethod
    def test_upsert() -> None:
        rs0 = RequestSource.upsert(False, "http://localhost", "127.0.0.1")

        # already inserted
        rs1 = RequestSource.upsert(False, "http://localhost", "127.0.0.1")
        assert rs1.__dict__ == rs0.__dict__

        _rs2 = RequestSource.upsert(False, "http://localhost", "127.0.0.2")
        _rs3 = RequestSource.upsert(True, "http://localhost", "127.0.0.3")

    @staticmethod
    @pytest.mark.parametrize(
        ("is_automated", "route", "description", "found"),
        [
            (False, "http://localhost", "127.0.0.1", True),
            (True, "http://localhost", "127.0.0.1", False),
            (False, "http://localhost", "127.0.0.2", True),
            (True, "http://localhost", "127.0.0.2", False),
            (False, "http://localhost", "127.0.0.3", False),
            (True, "http://localhost", "127.0.0.3", True),
        ],
    )
    def test_select(
        is_automated: bool, route: str, description: str, found: bool
    ) -> None:
        rs = RequestSource.select(is_automated, route, description)
        if found:
            assert rs is not None
        else:
            assert rs is None


class TestRequestLog:
    def test_init(self) -> None:
        RequestLog(
            1,
            datetime.datetime.now(tz=datetime.timezone.utc),
            1,
            "epub",
            "foo5",
            1_000,
            "foo5-url-id",
            "test fic info",
            1_123,
            "/tmp/test-export.epub",
            "test-hash",
            "http://localhost/1",
        )

    @staticmethod
    def test_mostRecentByUrlId_not_found() -> None:
        assert RequestLog.mostRecentByUrlId("epub", "foo5-no-exports") is None

    @staticmethod
    def test_insert() -> None:
        RequestLog.insert(
            RequestSource.upsert(False, "http://localhost", "127.0.1.1"),
            "epub",
            "foo5",
            123,
            "foo5-url-id",
            None,
            None,
            None,
            None,
            None,
        )

        rl0 = RequestLog.mostRecentByUrlId("epub", "foo5-url-id")
        assert rl0 is not None

        rl1 = RequestLog.mostRecentByUrlId("epub", "foo5-url-id")
        assert rl1.__dict__ == rl0.__dict__

        RequestLog.insert(
            RequestSource.upsert(False, "http://localhost", "127.0.1.1"),
            "epub",
            "foo5",
            123,
            "foo5-url-id",
            None,
            None,
            None,
            None,
            None,
        )

        rl2 = RequestLog.mostRecentByUrlId("epub", "foo5-url-id")
        assert rl2.__dict__ != rl0.__dict__

    @staticmethod
    def test_mostRecentByUrlId() -> None:
        rl0 = RequestLog.mostRecentByUrlId("epub", "foo5-url-id")
        assert rl0 is not None
