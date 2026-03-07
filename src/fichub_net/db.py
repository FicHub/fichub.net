from typing import Any, Optional
import datetime
from enum import Enum
import json
from pathlib import Path
import sys

from oil import oil


class MissingRequestSourceError(Exception):
    pass


class ExportLog:
    field_count = 6

    def __init__(
        self,
        url_id_: str,
        version_: int,
        etype_: str,
        input_hash_: str,
        export_hash_: str,
        created_: datetime.datetime,
    ) -> None:
        self.url_id = url_id_
        self.version = version_
        self.etype = etype_
        self.input_hash = input_hash_
        self.exportHash = export_hash_
        self.created = created_

    @staticmethod
    def lookup(
        url_id: str, version: int, etype: str, input_hash: str
    ) -> Optional["ExportLog"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select *
                from exportLog e
                where e.urlId = %s
                  and e.version = %s
                  and e.etype = %s
                  and e.inputHash = %s
                """,
                (url_id, version, etype, input_hash),
            )
            r = curs.fetchone()
            return ExportLog(*r[: ExportLog.field_count]) if r is not None else None

    def upsert(self) -> "ExportLog":
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                insert into exportLog(urlId, version, etype, inputHash, exportHash)
                values(%s, %s, %s, %s, %s)
                on conflict(urlId, version, etype, inputHash) do
                update set exportHash = EXCLUDED.exportHash
                where exportLog.created < EXCLUDED.created
                """,
                (
                    self.url_id,
                    self.version,
                    self.etype,
                    self.input_hash,
                    self.exportHash,
                ),
            )
        el = ExportLog.lookup(self.url_id, self.version, self.etype, self.input_hash)
        assert el is not None
        self.exportHash = el.exportHash
        self.created = el.created
        return self


class FicVersionBump:
    table_alias = "fvb"
    fields = ("id", "value")
    field_count = len(fields)

    @classmethod
    def select_list(cls) -> str:
        return ", ".join(f"{cls.table_alias}.{f}" for f in cls.fields)

    def __init__(self, id_: str, value_: int) -> None:
        self.id = id_
        self.value = value_

    @staticmethod
    def select(url_id: str) -> list["FicVersionBump"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                f"""
                select {FicVersionBump.select_list()}
                from ficVersionBump {FicVersionBump.table_alias}
                where id = %s
                """,
                (url_id,),
            )
            return [FicVersionBump(*r) for r in curs.fetchall()]


class FicInfo:
    table_alias = "fi"
    fields = (
        "id",
        "created",
        "updated",
        "title",
        "author",
        "chapters",
        "words",
        "description",
        "ficCreated",
        "ficUpdated",
        "status",
        "source",
        "extraMeta",
        "sourceId",
        "authorId",
        "contentHash",
        "authorUrl",
        "authorLocalId",
        "rawExtendedMeta",
    )
    field_count = len(fields)

    @classmethod
    def select_list(cls) -> str:
        return ", ".join(f"{cls.table_alias}.{f}" for f in cls.fields)

    # TODO: make sourceId, authorId non-Optional when fully backfilled
    # TODO: make authorUrl, authorLocalId non-Optional when fully backfilled
    def __init__(
        self,
        id_: str,
        created_: datetime.datetime,
        updated_: datetime.datetime,
        title_: str,
        author_: str,
        chapters_: int,
        words_: int,
        description_: str,
        fic_created_: datetime.datetime,
        fic_updated_: datetime.datetime,
        status_: str,
        source_: str,
        extra_meta_: str | None,
        source_id_: int | None,
        author_id_: int | None,
        content_hash_: str | None,
        author_url_: str | None,
        author_local_id_: str | None,
        raw_extended_meta_: str | None,
    ) -> None:
        self.id = id_
        self.created = created_
        self.updated = updated_
        self.title = title_
        self.author = author_
        self.chapters = chapters_
        self.words = words_
        self.description = description_
        self.fic_created = fic_created_
        self.fic_updated = fic_updated_
        self.status = status_
        self.source = source_
        self.extra_meta = extra_meta_
        self.source_id = source_id_
        self.author_id = author_id_
        self.content_hash = content_hash_
        self.author_url = author_url_
        self.author_local_id = author_local_id_
        self.raw_extended_meta = raw_extended_meta_

    def to_json(self) -> dict["str", Any]:
        raw_extended_meta = None
        try:
            if self.raw_extended_meta is not None and len(self.raw_extended_meta) > 0:
                raw_extended_meta = json.loads(self.raw_extended_meta)
        except Exception:
            pass
        return {
            "id": self.id,
            "created": self.fic_created.isoformat(),
            "updated": self.fic_updated.isoformat(),
            "title": self.title,
            "author": self.author,
            "chapters": self.chapters,
            "words": self.words,
            "description": self.description,
            "status": self.status,
            "source": self.source,
            "extraMeta": self.extra_meta,
            "rawExtendedMeta": raw_extended_meta,
            "authorUrl": self.author_url,
            "authorLocalId": self.author_local_id,
            "sourceId": self.source_id,
            "authorId": self.author_id,
        }

    @staticmethod
    def select(url_id: str | None = None) -> list["FicInfo"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                f"""
                select {FicInfo.select_list()}
                from ficInfo {FicInfo.table_alias}
                where %s is null or id = %s
                """,
                (url_id, url_id),
            )
            return [FicInfo(*r) for r in curs.fetchall()]

    @staticmethod
    def save(fic_info: dict[str, str]) -> None:
        with oil.open() as db, db.cursor() as curs:
            fi = FicInfo.parse(fic_info)
            curs.execute(
                """
                insert into ficInfo(
                  id, title, author, chapters, words, description, ficCreated,
                  ficUpdated, status, source, extraMeta, sourceId, authorId,
                  contentHash, authorUrl, authorLocalId, rawExtendedMeta)
                values(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict(id) do
                update set updated = current_timestamp,
                  title = EXCLUDED.title, author = EXCLUDED.author,
                  chapters = EXCLUDED.chapters, words = EXCLUDED.words,
                  description = EXCLUDED.description,
                  ficCreated = EXCLUDED.ficCreated, ficUpdated = EXCLUDED.ficUpdated,
                  status = EXCLUDED.status, source = EXCLUDED.source,
                  extraMeta = EXCLUDED.extraMeta, sourceId = EXCLUDED.sourceId,
                  authorId = EXCLUDED.authorId, contentHash = EXCLUDED.contentHash,
                  authorUrl = EXCLUDED.authorUrl,
                  authorLocalId = EXCLUDED.authorLocalId,
                  rawExtendedMeta = EXCLUDED.rawExtendedMeta
                """,
                (
                    fi.id,
                    fi.title,
                    fi.author,
                    fi.chapters,
                    fi.words,
                    fi.description,
                    fi.fic_created,
                    fi.fic_updated,
                    fi.status,
                    fi.source,
                    fi.extra_meta,
                    fi.source_id,
                    fi.author_id,
                    fi.content_hash,
                    fi.author_url,
                    fi.author_local_id,
                    fi.raw_extended_meta,
                ),
            )

    @staticmethod
    def parse(fic_info: dict[str, str]) -> "FicInfo":
        extra_meta = fic_info.get("extraMeta")
        if extra_meta is not None and len(extra_meta.strip()) < 1:
            extra_meta = None
        raw_extended_meta = fic_info.get("rawExtendedMeta")
        if raw_extended_meta is not None and len(raw_extended_meta.strip()) < 1:
            raw_extended_meta = None
        return FicInfo(
            fic_info["urlId"],
            datetime.datetime.now(tz=datetime.timezone.utc),
            datetime.datetime.now(tz=datetime.timezone.utc),
            fic_info["title"],
            fic_info["author"],
            int(fic_info["chapters"]),
            int(fic_info["words"]),
            fic_info["desc"],
            datetime.datetime.fromtimestamp(
                int(fic_info["published"]) / 1000.0, tz=datetime.timezone.utc
            ),
            datetime.datetime.fromtimestamp(
                int(fic_info["updated"]) / 1000.0, tz=datetime.timezone.utc
            ),
            fic_info["status"],
            fic_info["source"],
            extra_meta,
            int(fic_info["sourceId"]),
            int(fic_info["authorId"]),
            fic_info["contentHash"],
            fic_info.get("authorUrl"),
            fic_info.get("authorLocalId"),
            raw_extended_meta,
        )


class FicBlacklistReason(Enum):
    # blacklist request by author, they're trying to scrub it from the net
    AUTHOR_BLACKLIST_REQUEST = 5
    # greylist request by author, they don't want downloads available
    AUTHOR_GREYLIST_REQUEST = 6
    # real author requests plagiarism takedown
    REAL_AUTHOR_PLAGIRAISM_TAKEDOWN_REQUEST = 7
    # 3rd party plagiarism request
    THIRD_PARTY_PLAGIRAISM_TAKEDOWN_REQUEST = 8


class FicBlacklist:
    def __init__(
        self,
        url_id_: str,
        created_: datetime.datetime,
        updated_: datetime.datetime,
        reason_: int,
    ) -> None:
        self.url_id = url_id_
        self.created = created_
        self.updated = updated_
        self.reason = reason_

    @staticmethod
    def select(url_id: str | None = None) -> list["FicBlacklist"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select urlId, created, updated, reason
                from ficBlacklist
                where %s is null or urlId = %s
                """,
                (url_id, url_id),
            )
            return [FicBlacklist(*r) for r in curs.fetchall()]

    @staticmethod
    def check(url_id: str, reason: int | None = None) -> bool:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select 1
                from ficInfo fi
                left join ficBlacklist fb
                  on fb.urlId = fi.id
                  and (%s is null or fb.reason = %s)
                left join authorBlacklist ab
                  on ab.sourceId = fi.sourceId
                  and ab.authorId = fi.authorId
                  and (%s is null or ab.reason = %s)
                where fi.id = %s
                  and ((fb.reason is not null or ab.reason is not null) or fi.sourceId = 19)
                """,
                (reason, reason, reason, reason, url_id),
            )
            return len(curs.fetchall()) > 0

    @staticmethod
    def blacklisted(url_id: str) -> bool:
        return FicBlacklist.check(
            url_id, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value
        )

    @staticmethod
    def greylisted(url_id: str) -> bool:
        if FicBlacklist.check(url_id, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value):
            return True
        if FicBlacklist.check(
            url_id, FicBlacklistReason.REAL_AUTHOR_PLAGIRAISM_TAKEDOWN_REQUEST.value
        ):
            return True
        return FicBlacklist.check(
            url_id, FicBlacklistReason.THIRD_PARTY_PLAGIRAISM_TAKEDOWN_REQUEST.value
        )

    @staticmethod
    def save(url_id: str, reason: int) -> None:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                insert into ficBlacklist(urlId, reason)
                values(%s, %s)
                on conflict(urlId, reason) do
                update set updated = current_timestamp
                """,
                (url_id, reason),
            )


class AuthorBlacklist:
    def __init__(
        self,
        source_id_: int,
        author_id_: int,
        created_: datetime.datetime,
        updated_: datetime.datetime,
        reason_: int,
    ) -> None:
        self.source_id = source_id_
        self.author_id = author_id_
        self.created = created_
        self.updated = updated_
        self.reason = reason_

    @staticmethod
    def select(
        source_id: int | None = None, author_id: int | None = None
    ) -> list["AuthorBlacklist"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select sourceId, authorId, created, updated, reason
                from authorBlacklist
                where (%s is null or sourceId = %s)
                  and (%s is null or authorId = %s)
                """,
                (source_id, source_id, author_id, author_id),
            )
            return [AuthorBlacklist(*r) for r in curs.fetchall()]

    @staticmethod
    def check(source_id: int, author_id: int, reason: int | None = None) -> bool:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select sourceId, authorId from authorBlacklist
                where sourceId = %s and authorId = %s
                  and ((%s is null or reason = %s) or sourceId = 19)
                """,
                (source_id, author_id, reason, reason),
            )
            return len(curs.fetchall()) > 0

    @staticmethod
    def blacklisted(source_id: int, author_id: int) -> bool:
        return AuthorBlacklist.check(
            source_id, author_id, FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value
        )

    @staticmethod
    def greylisted(source_id: int, author_id: int) -> bool:
        return AuthorBlacklist.check(
            source_id, author_id, FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value
        )

    @staticmethod
    def save(source_id: int, author_id: int, reason: int) -> None:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                insert into authorBlacklist(sourceId, authorId, reason)
                values(%s, %s, %s)
                on conflict(sourceId, authorId, reason) do
                update set updated = current_timestamp
                """,
                (source_id, author_id, reason),
            )


class RequestSource:
    def __init__(
        self,
        id_: int,
        created_: datetime.datetime,
        is_automated_: bool,
        route_: str,
        description_: str,
    ) -> None:
        self.id = id_
        self.created = created_
        self.is_automated = is_automated_
        self.route = route_
        self.description = description_

    @staticmethod
    def select(
        is_automated: bool, route: str, description: str
    ) -> Optional["RequestSource"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select rs.id, rs.created, rs.isAutomated, rs.route, rs.description
                from requestSource rs
                where rs.isAutomated = %s and route = %s and description = %s
                """,
                (is_automated, route, description),
            )
            r = curs.fetchone()
            return None if r is None else RequestSource(*r)

    @staticmethod
    def upsert(is_automated: bool, route: str, description: str) -> "RequestSource":
        existing = RequestSource.select(is_automated, route, description)
        if existing is not None:
            return existing
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                insert into requestSource(isAutomated, route, description)
                values (%s, %s, %s)
                on conflict(isAutomated, route, description) do nothing
                """,
                (is_automated, route, description),
            )
        src = RequestSource.select(is_automated, route, description)
        if src is None:
            msg = "RequestSource.upsert: failed to upsert"
            raise MissingRequestSourceError(msg)
        return src


class RequestLog:
    def __init__(
        self,
        id_: int,
        created_: datetime.datetime,
        source_id_: int,
        etype_: str,
        query_: str,
        info_request_ms_: int,
        url_id_: str | None,
        fic_info_: str | None,
        export_ms_: int | None,
        export_file_name_: str | None,
        export_file_hash_: str | None,
        url_: str | None,
    ) -> None:
        self.id = id_
        self.created = created_
        self.source_id = source_id_
        self.etype = etype_
        self.query = query_
        self.infoRequestMs = info_request_ms_
        self.url_id = url_id_
        self.fic_info = fic_info_
        self.exportMs = export_ms_
        self.export_file_name = export_file_name_
        self.export_file_hash = export_file_hash_
        self.url = url_

    @staticmethod
    def most_recent_by_url_id(etype: str, url_id: str) -> Optional["RequestLog"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select r.id, r.created, r.sourceId, r.etype, r.query, r.infoRequestMs,
                  r.urlId, r.ficInfo, r.exportMs, r.exportFileName, r.exportFileHash,
                  r.url
                from requestLog r
                where r.etype = %s and r.urlId = %s
                order by r.created desc
                limit 1
                """,
                (etype, url_id),
            )
            r = curs.fetchone()
            return None if r is None else RequestLog(*r)

    @staticmethod
    def insert(
        source: RequestSource,
        etype: str,
        query: str,
        info_request_ms: int,
        url_id: str | None,
        fic_info: str | None,
        export_ms: int | None,
        export_file_name: str | None,
        export_file_hash: str | None,
        url: str | None,
    ) -> None:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                insert into requestLog(sourceId, etype, query, infoRequestMs, urlId,
                  ficInfo, exportMs, exportFileName, exportFileHash, url)
                values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    source.id,
                    etype,
                    query,
                    info_request_ms,
                    url_id,
                    fic_info,
                    export_ms,
                    export_file_name,
                    export_file_hash,
                    url,
                ),
            )


def cmd_migrate() -> int:
    with oil.open() as db, db.cursor() as curs:
        for sql_path in ["./sql/fichub_net.sql", "./sql/limiter.sql"]:
            sql = Path(sql_path).read_text()
            curs.execute(sql)

        for i in range(2, 1_000):
            p = Path(f"./sql/upgrade{i}.sql")
            if not p.is_file():
                break
            curs.execute(p.read_text())

    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] != "migrate":  # noqa: PLR2004
        print("usage: uv run ./src/fichub_net/db.py migrate -- migrate the db")
        return 1

    return cmd_migrate()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
