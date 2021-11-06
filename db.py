from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
import datetime
from oil import oil

class ExportLog:
	fieldCount = 6
	def __init__(self, urlId_: str, version_: int, etype_: str, inputHash_: str,
			exportHash_: str, created_: datetime.datetime) -> None:
		self.urlId = urlId_
		self.version = version_
		self.etype = etype_
		self.inputHash = inputHash_
		self.exportHash = exportHash_
		self.created = created_

	@staticmethod
	def lookup(urlId: str, version: int, etype: str, inputHash: str
			) -> Optional['ExportLog']:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select *
				from exportLog e
				where e.urlId = %s
					and e.version = %s
					and e.etype = %s
					and e.inputHash = %s
				''', (urlId, version, etype, inputHash))
			r = curs.fetchone()
			return ExportLog(*r[:ExportLog.fieldCount]) if r is not None else None

	def upsert(self) -> 'ExportLog':
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				insert into exportLog(urlId, version, etype, inputHash, exportHash)
				values(%s, %s, %s, %s, %s)
				on conflict(urlId, version, etype, inputHash) do
				update set exportHash = EXCLUDED.exportHash
				where exportLog.created < EXCLUDED.created
				''', (self.urlId, self.version, self.etype, self.inputHash,
					self.exportHash))
		l = ExportLog.lookup(self.urlId, self.version, self.etype, self.inputHash)
		assert(l is not None)
		self.exportHash = l.exportHash
		self.created = l.created
		return self

class FicInfo:
	tableAlias = 'fi'
	fields = [
		'id', 'created', 'updated', 'title', 'author', 'chapters', 'words',
		'description', 'ficCreated', 'ficUpdated', 'status', 'source', 'extraMeta',
		'sourceId', 'authorId', 'contentHash',
	]
	fieldCount = len(fields)

	@classmethod
	def selectList(cls) -> str:
		return ', '.join(map(lambda f: f'{cls.tableAlias}.{f}', cls.fields))

	# TODO: make sourceId, authorId non-Optional when fully backfilled
	def __init__(self, id_: str, created_: datetime.datetime,
			updated_: datetime.datetime, title_: str, author_: str, chapters_: int,
			words_: int, description_: str, ficCreated_: datetime.datetime,
			ficUpdated_: datetime.datetime, status_: str, source_: str,
			extraMeta_: Optional[str], sourceId_: Optional[int],
			authorId_: Optional[int], contentHash_: Optional[str]) -> None:
		self.id = id_
		self.created = created_
		self.updated = updated_
		self.title = title_
		self.author = author_
		self.chapters = chapters_
		self.words = words_
		self.description = description_
		self.ficCreated = ficCreated_
		self.ficUpdated = ficUpdated_
		self.status = status_
		self.source = source_
		self.extraMeta = extraMeta_
		self.sourceId = sourceId_
		self.authorId = authorId_
		self.contentHash = contentHash_

	def toJson(self) -> Dict['str', Any]:
		return {
				'id': self.id,
				'created': self.ficCreated.isoformat(),
				'updated': self.ficUpdated.isoformat(),
				'title': self.title,
				'author': self.author,
				'chapters': self.chapters,
				'words': self.words,
				'description': self.description,
				'status': self.status,
				'source': self.source,
				'extraMeta': self.extraMeta,
			}

	@staticmethod
	def select(urlId: Optional[str] = None) -> List['FicInfo']:
		with oil.open() as db, db.cursor() as curs:
			curs.execute(f'''
				select {FicInfo.selectList()}
				from ficInfo {FicInfo.tableAlias}
				where %s is null or id = %s
			''', (urlId, urlId))
			return [FicInfo(*r) for r in curs.fetchall()]

	@staticmethod
	def save(ficInfo: Dict[str, str]) -> None:
		with oil.open() as db, db.cursor() as curs:
			fi = FicInfo.parse(ficInfo)
			curs.execute('''
				insert into ficInfo(
					id, title, author, chapters, words, description, ficCreated,
					ficUpdated, status, source, extraMeta, sourceId, authorId,
					contentHash)
				values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				on conflict(id) do
				update set updated = current_timestamp,
					title = EXCLUDED.title, author = EXCLUDED.author,
					chapters = EXCLUDED.chapters, words = EXCLUDED.words,
					description = EXCLUDED.description,
					ficCreated = EXCLUDED.ficCreated, ficUpdated = EXCLUDED.ficUpdated,
					status = EXCLUDED.status, source = EXCLUDED.source,
					extraMeta = EXCLUDED.extraMeta, sourceId = EXCLUDED.sourceId,
					authorId = EXCLUDED.authorId, contentHash = EXCLUDED.contentHash
				''', (fi.id, fi.title, fi.author, fi.chapters, fi.words,
					fi.description, fi.ficCreated, fi.ficUpdated, fi.status, fi.source,
					fi.extraMeta, fi.sourceId, fi.authorId, fi.contentHash))

	@staticmethod
	def parse(ficInfo: Dict[str, str]) -> 'FicInfo':
		extraMeta = ficInfo['extraMeta'] if 'extraMeta' in ficInfo else None
		if extraMeta is not None and len(extraMeta.strip()) < 1:
			extraMeta = None
		return FicInfo(ficInfo['urlId'],
				datetime.datetime.now(), datetime.datetime.now(),
				ficInfo['title'], ficInfo['author'],
				int(ficInfo['chapters']), int(ficInfo['words']),
				ficInfo['desc'],
				datetime.datetime.fromtimestamp(int(ficInfo['published'])/1000.0),
				datetime.datetime.fromtimestamp(int(ficInfo['updated'])/1000.0),
				ficInfo['status'],
				ficInfo['source'],
				extraMeta,
				ficInfo['sourceId'],
				ficInfo['authorId'],
				ficInfo['contentHash'],
			)

class FicBlacklistReason(Enum):
	# blacklist request by author, they're trying to scrub it from the net
	AUTHOR_BLACKLIST_REQUEST = 5
	# greylist request by author, they don't want downloads available
	AUTHOR_GREYLIST_REQUEST = 6

class FicBlacklist:
	def __init__(self, urlId_: str, created_: datetime.datetime,
			updated_: datetime.datetime, reason_: int) -> None:
		self.urlId = urlId_
		self.created = created_
		self.updated = updated_
		self.reason = reason_

	@staticmethod
	def select(urlId: Optional[str] = None) -> List['FicBlacklist']:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select urlId, created, updated, reason
				from ficBlacklist
				where %s is null or urlId = %s
			''', (urlId, urlId))
			return [FicBlacklist(*r) for r in curs.fetchall()]

	@staticmethod
	def check(urlId: str, reason: Optional[int] = None) -> bool:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
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
			''', (reason, reason, reason, reason, urlId))
			return len(curs.fetchall()) > 0

	@staticmethod
	def blacklisted(urlId: str) -> bool:
		return FicBlacklist.check(urlId,
				FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value)

	@staticmethod
	def greylisted(urlId: str) -> bool:
		return FicBlacklist.check(urlId,
				FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value)

	@staticmethod
	def save(urlId: str, reason: int) -> None:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				insert into ficBlacklist(urlId, reason)
				values(%s, %s)
				on conflict(urlId, reason) do
				update set updated = current_timestamp
				''', (urlId, reason))

class AuthorBlacklist:
	def __init__(self, sourceId_: int, authorId_: int,
			created_: datetime.datetime, updated_: datetime.datetime, reason_: int
			) -> None:
		self.sourceId = sourceId_
		self.authorId = authorId_
		self.created = created_
		self.updated = updated_
		self.reason = reason_

	@staticmethod
	def select(sourceId: Optional[int] = None, authorId: Optional[int] = None
			) -> List['AuthorBlacklist']:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select sourceId, authorId, created, updated, reason
				from authorBlacklist
				where (%s is null or sourceId = %s)
					and (%s is null or authorId = %s)
			''', (sourceId, sourceId, authorId, authorId))
			return [AuthorBlacklist(*r) for r in curs.fetchall()]

	@staticmethod
	def check(sourceId: int, authorId: int, reason: Optional[int] = None) -> bool:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select sourceId, authorId from authorBlacklist
				where sourceId = %s and authorId = %s
					and ((%s is null or reason = %s) or sourceId = 19)
			''', (sourceId, authorId, reason, reason))
			return len(curs.fetchall()) > 0

	@staticmethod
	def blacklisted(sourceId: int, authorId: int) -> bool:
		return AuthorBlacklist.check(sourceId, authorId,
				FicBlacklistReason.AUTHOR_BLACKLIST_REQUEST.value)

	@staticmethod
	def greylisted(sourceId: int, authorId: int) -> bool:
		return AuthorBlacklist.check(sourceId, authorId,
				FicBlacklistReason.AUTHOR_GREYLIST_REQUEST.value)

	@staticmethod
	def save(sourceId: int, authorId: int, reason: int) -> None:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				insert into authorBlacklist(sourceId, authorId, reason)
				values(%s, %s, %s)
				on conflict(sourceId, authorId, reason) do
				update set updated = current_timestamp
				''', (sourceId, authorId, reason))

class RequestSource:
	def __init__(self, id_: int, created_: datetime.datetime, isAutomated_: bool,
			route_: str, description_: str) -> None:
		self.id = id_
		self.created = created_
		self.isAutomated = isAutomated_
		self.route = route_
		self.description = description_

	@staticmethod
	def select(isAutomated: bool, route: str, description: str
			) -> Optional['RequestSource']:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select rs.id, rs.created, rs.isAutomated, rs.route, rs.description
				from requestSource rs
				where rs.isAutomated = %s and route = %s and description = %s
			''', (isAutomated, route, description))
			r = curs.fetchone()
			return None if r is None else RequestSource(*r)

	@staticmethod
	def upsert(isAutomated: bool, route: str, description: str
			) -> 'RequestSource':
		existing = RequestSource.select(isAutomated, route, description)
		if existing is not None:
			return existing
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				insert into requestSource(isAutomated, route, description)
				values (%s, %s, %s)
				on conflict(isAutomated, route, description) do nothing
			''', (isAutomated, route, description))
		src = RequestSource.select(isAutomated, route, description)
		if src is None:
			raise Exception(f'RequestSource.upsert: failed to upsert')
		return src

class RequestLog:
	def __init__(self, id_: int, created_: datetime.datetime, sourceId_: int,
			etype_: str, query_: str, infoRequestMs_: int, urlId_: Optional[str],
			ficInfo_: Optional[str], exportMs_: Optional[int],
			exportFileName_: Optional[str], exportFileHash_: Optional[str],
			url_: Optional[str]) -> None:
		self.id = id_
		self.created = created_
		self.sourceId = sourceId_
		self.etype = etype_
		self.query = query_
		self.infoRequestMs = infoRequestMs_
		self.urlId = urlId_
		self.ficInfo = ficInfo_
		self.exportMs = exportMs_
		self.exportFileName = exportFileName_
		self.exportFileHash = exportFileHash_
		self.url = url_

	@staticmethod
	def mostRecentByUrlId(etype: str, urlId: str) -> Optional['RequestLog']:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select r.id, r.created, r.sourceId, r.etype, r.query, r.infoRequestMs,
					r.urlId, r.ficInfo, r.exportMs, r.exportFileName, r.exportFileHash,
					r.url
				from requestLog r
				where r.etype = %s and r.urlId = %s
				order by r.created desc
				limit 1
				''', (etype, urlId))
			r = curs.fetchone()
			return None if r is None else RequestLog(*r)

	@staticmethod
	def insert(source: RequestSource, etype: str, query: str, infoRequestMs: int,
			urlId: Optional[str], ficInfo: Optional[str], exportMs: Optional[int],
			exportFileName: Optional[str], exportFileHash: Optional[str],
			url: Optional[str]) -> None:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				insert into requestLog(sourceId, etype, query, infoRequestMs, urlId,
					ficInfo, exportMs, exportFileName, exportFileHash, url)
				values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				''', (source.id, etype, query, infoRequestMs, urlId, ficInfo, exportMs,
					exportFileName, exportFileHash, url))

