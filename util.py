from typing import Dict, Optional
import datetime
import traceback
import json
import hashlib
from oil import oil

def hashFile(fname: str) -> str:
	digest = 'hash_err'
	with open(fname, 'rb') as f:
		data = f.read()
		digest = hashlib.md5(data).hexdigest()
	return digest

class FicInfo:
	def __init__(self, id_, created_, updated_, title_, author_, chapters_,
			words_, description_, ficCreated_, ficUpdated_, status_):
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
	@staticmethod
	def fromRow(row):
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
			)
	@staticmethod
	def select(urlId = None):
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
					ficUpdated, status)
				values(%s, %s, %s, %s, %s, %s, %s, %s, %s)
				on conflict(id) do
				update set updated = current_timestamp,
					title = EXCLUDED.title, author = EXCLUDED.author,
					chapters = EXCLUDED.chapters, words = EXCLUDED.words,
					description = EXCLUDED.description,
					ficCreated = EXCLUDED.ficCreated, ficUpdated = EXCLUDED.ficUpdated,
					status = EXCLUDED.status
				''', (ficInfo['urlId'], ficInfo['title'], ficInfo['author'],
					int(ficInfo['chapters']), int(ficInfo['words']), ficInfo['desc'],
					datetime.date.fromtimestamp(int(ficInfo['published'])/1000.0),
					datetime.date.fromtimestamp(int(ficInfo['updated'])/1000.0),
					ficInfo['status']))

class RequestSource:
	def __init__(self, id_, created_, isAutomated_, route_, description_):
		self.id = id_
		self.created = created_
		self.isAutomated = isAutomated_
		self.route = route_
		self.description = description_

	@staticmethod
	def select(isAutomated, route, description):
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
				select rs.id, rs.created, rs.isAutomated, rs.route, rs.description
				from requestSource rs
				where rs.isAutomated = %s and route = %s and description = %s
			''', (isAutomated, route, description))
			r = curs.fetchone()
			return None if r is None else RequestSource(*r)

	@staticmethod
	def upsert(isAutomated, route, description):
		existing = RequestSource.select(isAutomated, route, description)
		if existing is not None:
			return existing
		with oil.open() as db, db, db.cursor() as curs:
			curs.execute('''
				insert into requestSource(isAutomated, route, description)
				values (%s, %s, %s)
				on conflict(isAutomated, route, description) do nothing
			''', (isAutomated, route, description))
		return RequestSource.select(isAutomated, route, description)

class RequestLog:
	def __init__(self, id_, created_, sourceId_, etype_, query_, infoRequestMs_,
			urlId_, ficInfo_, exportMs_, exportFileName_, exportFileHash_, url_):
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
	def mostRecentEpub():
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
					group by r.urlId
				)
				select r.id, r.created, r.sourceId, r.etype, r.query, r.infoRequestMs,
					r.urlId, r.ficInfo, r.exportMs, r.exportFileName, r.exportFileHash,
					r.url
				from mostRecentPerUrlId mr
				join requestLog r
					on r.urlId = mr.urlId
					and r.created = mr.created
				order by r.created desc
				''')
			ls = [RequestLog(*r) for r in curs.fetchall()]
			return ls
		return []

	@staticmethod
	def mostRecentByUrlId(etype: str, urlId: str):
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
			url: Optional[str]):
		with oil.open() as db, db, db.cursor() as curs:
			curs.execute('''
				insert into requestLog(sourceId, etype, query, infoRequestMs, urlId,
					ficInfo, exportMs, exportFileName, exportFileHash, url)
				values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				''', (source.id, etype, query, infoRequestMs, urlId, ficInfo, exportMs,
					exportFileName, exportFileHash, url))

