from typing import Dict, Any, Optional, List, Tuple
import datetime
import traceback
import urllib.parse
import util
from oil import oil
import authentications as a

class FicInfo:
	def __init__(self, id_: str, created_: datetime.datetime,
			updated_: datetime.datetime, title_: str, author_: str, chapters_: int,
			words_: int, description_: str, ficCreated_: datetime.datetime,
			ficUpdated_: datetime.datetime, status_: str, source_: str) -> None:
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
	@staticmethod
	def fromRow(row: Any) -> 'FicInfo':
		return FicInfo(
				id_ = row[0],
				created_ = row[1],
				updated_ = row[2],
				title_ = row[3],
				author_ = row[4],
				chapters_ = row[5],
				words_ = row[6],
				description_ = row[7],
				ficCreated_ = row[8],
				ficUpdated_ = row[9],
				status_ = row[10],
				source_ = row[11],
			)
	@staticmethod
	def select(urlId: Optional[str] = None) -> List['FicInfo']:
		with oil.open() as db, db, db.cursor() as curs:
			curs.execute('''
				select * from ficInfo where %s is null or id = %s
			''', (urlId, urlId))
			return [FicInfo.fromRow(r) for r in curs.fetchall()]

	@staticmethod
	def save(ficInfo: Dict[str, str]) -> None:
		with oil.open() as db, db, db.cursor() as curs:
			curs.execute('''
				insert into ficInfo(
					id, title, author, chapters, words, description, ficCreated,
					ficUpdated, status, source)
				values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				on conflict(id) do
				update set updated = current_timestamp,
					title = EXCLUDED.title, author = EXCLUDED.author,
					chapters = EXCLUDED.chapters, words = EXCLUDED.words,
					description = EXCLUDED.description,
					ficCreated = EXCLUDED.ficCreated, ficUpdated = EXCLUDED.ficUpdated,
					status = EXCLUDED.status, source = EXCLUDED.source
				''', (ficInfo['urlId'], ficInfo['title'], ficInfo['author'],
					int(ficInfo['chapters']), int(ficInfo['words']), ficInfo['desc'],
					datetime.datetime.fromtimestamp(int(ficInfo['published'])/1000.0),
					datetime.datetime.fromtimestamp(int(ficInfo['updated'])/1000.0),
					ficInfo['status'], ficInfo['source']))

	@staticmethod
	def parse(ficInfo: Dict[str, str]) -> 'FicInfo':
		return FicInfo(ficInfo['urlId'],
				datetime.datetime.now(), datetime.datetime.now(),
				ficInfo['title'], ficInfo['author'],
				int(ficInfo['chapters']), int(ficInfo['words']),
				ficInfo['desc'],
				datetime.datetime.fromtimestamp(int(ficInfo['published'])/1000.0),
				datetime.datetime.fromtimestamp(int(ficInfo['updated'])/1000.0),
				ficInfo['status'],
				ficInfo['source'],
			)

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
		with oil.open() as db, db, db.cursor() as curs:
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
	def prevDay(date: datetime.date) -> Optional[datetime.date]:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select max(date(r.created))
				from requestLog r
				where date(r.created) < %s
					and r.exportFileName is not null
					and r.etype = 'epub'
				''', (date,))
			r = curs.fetchone()
			return r[0] if r is not None else None

	@staticmethod
	def nextDay(date: datetime.date) -> Optional[datetime.date]:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select min(date(r.created))
				from requestLog r
				where date(r.created) > %s
					and r.exportFileName is not null
					and r.etype = 'epub'
				''', (date,))
			r = curs.fetchone()
			return r[0] if r is not None else None

	@staticmethod
	def mostRecentEpubCount(date: datetime.date) -> int:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				; with mostRecentPerUrlId as (
					select coalesce(
						max(case when rs.isAutomated = true then null else r.created end),
						max(r.created)) as created,
						r.urlId
					from requestLog r
					join requestSource rs
						on rs.id = r.sourceId
					where r.exportFileName is not null
						and r.etype = 'epub'
						and date(r.created) = date(%s)
						and rs.isAutomated = false
					group by r.urlId
				)
				select count(1)
				from mostRecentPerUrlId mr
				join requestLog r
					on r.urlId = mr.urlId
					and r.created = mr.created
				join ficInfo fi on fi.id = r.urlId
				''', (date,))
			r = curs.fetchone()
			return 0 if r is None else int(r[0])

	@staticmethod
	def mostRecentEpub(date: datetime.date, limit: int, offset: int
			) -> List[Tuple['RequestLog', FicInfo]]:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				; with mostRecentPerUrlId as (
					select coalesce(
						max(case when rs.isAutomated = true then null else r.created end),
						max(r.created)) as created,
						r.urlId
					from requestLog r
					join requestSource rs
						on rs.id = r.sourceId
					where r.exportFileName is not null
						and r.etype = 'epub'
						and date(r.created) = date(%s)
						and rs.isAutomated = false
					group by r.urlId
				)
				select r.id, r.created, r.sourceId, r.etype, r.query, r.infoRequestMs,
					r.urlId, r.ficInfo, r.exportMs, r.exportFileName, r.exportFileHash,
					r.url,
					fi.*
				from mostRecentPerUrlId mr
				join requestLog r
					on r.urlId = mr.urlId
					and r.created = mr.created
				join ficInfo fi on fi.id = r.urlId
				order by r.created desc
				limit %s
				offset %s
				''', (date, limit, offset))
			return [(RequestLog(*r[:12]), FicInfo.fromRow(r[12:]))
					for r in curs.fetchall()]

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
	def mostRecentsByUrlId(urlId: str) -> Tuple[FicInfo, List['RequestLog']]:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				; with recent as (
					select max(rl.id) as id, rl.urlId
					from requestLog rl
					where rl.urlId is not null and rl.exportFileHash is not null
						and rl.urlId = %s
					group by rl.etype, rl.urlId
				)
				select fi.*,
					rl.id, rl.created, rl.sourceId, rl.etype, rl.query,
					rl.infoRequestMs, rl.urlId, rl.ficInfo, rl.exportMs,
					rl.exportFileName, rl.exportFileHash, rl.url
				from ficInfo fi
				join recent l on l.urlId = fi.id
				join requestLog rl on rl.id = l.id
				where fi.id = %s
				''', (urlId, urlId,))
			rs = [(FicInfo.fromRow(r[:12]), RequestLog(*r[12:]))
					for r in curs.fetchall()]
			if len(rs) < 1:
				return (None, [])
			return (rs[0][0], [e[1] for e in rs])

	@staticmethod
	def mostPopular(limit: int = 10, offset: int = 0) -> List[Tuple[int, FicInfo]]:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				; with popular as (
					select count(1) as cnt, urlId
					from requestLog rl
					where rl.urlId is not null
						and rl.exportFileHash is not null
					group by rl.urlId
					order by count(1) desc
					limit %s
					offset %s
				)
				select p.cnt, fi.*
				from popular p
				join ficInfo fi on fi.id = p.urlId
				order by p.cnt desc
				''', (limit, offset))
			return [(int(r[0]), FicInfo.fromRow(r[1:])) for r in curs.fetchall()]

	@staticmethod
	def totalPopular() -> int:
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				; with popular as (
					select count(1) as cnt, urlId
					from requestLog rl
					where rl.urlId is not null
						and rl.exportFileHash is not null
					group by rl.urlId
					order by count(1) desc
				)
				select count(1)
				from popular p
				''')
			r = curs.fetchone()
			return 0 if r is None else int(r[0])

	@staticmethod
	def insert(source: RequestSource, etype: str, query: str, infoRequestMs: int,
			urlId: Optional[str], ficInfo: Optional[str], exportMs: Optional[int],
			exportFileName: Optional[str], exportFileHash: Optional[str],
			url: Optional[str]) -> None:
		with oil.open() as db, db, db.cursor() as curs:
			curs.execute('''
				insert into requestLog(sourceId, etype, query, infoRequestMs, urlId,
					ficInfo, exportMs, exportFileName, exportFileHash, url)
				values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				''', (source.id, etype, query, infoRequestMs, urlId, ficInfo, exportMs,
					exportFileName, exportFileHash, url))

def lookup(query: str) -> Dict[str, Any]:
	url = '/'.join([a.AX_LOOKUP_ENDPOINT, urllib.parse.quote(query, safe='')])
	meta = util.reqJson(url)
	if 'error' in meta and 'err' not in meta:
		meta['err'] = meta.pop('error', None)
	if 'err' not in meta:
		FicInfo.save(meta)
	return meta

class Chapter:
	def __init__(self, n: int, title: str, content: str) -> None:
		self.n = n
		self.title = title
		self.content = content

class MissingChapterException(Exception):
	pass

def requestAllChapters(urlId: str, expected: int) -> Dict[int, Chapter]:
	url = '/'.join([a.AX_FIC_ENDPOINT, urlId, 'all'])
	res = util.reqJson(url)
	chapters = {}
	titles = []
	for ch in res['chapters']:
		n = int(ch['chapterId'])

		# generate a chapter name if its missing
		title = str(ch['title']).strip() if 'title' in ch else None
		titles.append(title)
		if title is None or len(title) < 1:
			title = f'Chapter {n}'

		# extract chapter content and prepend with chapter title header
		titleHeader = f'<h2>{title}</h2>'
		content = titleHeader + str(ch['content']).strip()
		if len(content) <= len(titleHeader):
			print(f'note: {url} {n} has an empty content body')
			content += '<p></p>'
		ch['content'] = None

		chapters[n] = Chapter(n, title, content)

	# ensure we got the number of expected chapters
	for i in range(1, expected + 1):
		if i not in chapters:
			print(f'requestAllChapters: err: {i} not in chapters')
			print(list(chapters.keys()))
			raise MissingChapterException(f'err: missing chapter: {i}/{expected}')

	return chapters

def fetchChapters(info: FicInfo) -> Dict[int, Chapter]:
	# try to grab all chapters with the new /all endpoint first
	try:
		return requestAllChapters(info.id, info.chapters)
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('fetchChapters: ^ something went wrong :/')
		raise

