import datetime
import traceback
import json
from oil import oil

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

def saveFicInfo(ficInfo):
	try:
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
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('saveFicInfo: error: ^')

class RequestLog:
	def __init__(self, id_, created_, infoRequestMs_, epubCreationMs_, urlId_,
			query_, ficInfo_, epubFileName_, hash_, url_, isAutomated_):
		self.id = id_
		self.created = created_
		self.infoRequestMs = infoRequestMs_
		self.epubCreationMs = epubCreationMs_
		self.urlId = urlId_
		self.query = query_
		self.ficInfo = ficInfo_
		self.epubFileName = epubFileName_
		self.hash = hash_
		self.url = url_
		self.isAutomated = isAutomated_

	@staticmethod
	def mostRecent():
		with oil.open() as db, db.cursor() as curs:
			curs.execute('''
			select r.* from requestLog r
			left join requestLog o
				on o.urlId = r.urlId
				and o.created > r.created
				and o.isAutomated = false
			where r.isAutomated = false and o.urlId is null
			''')
			ls = [RequestLog(*r) for r in curs.fetchall()]
			return ls
		return []

def logRequest(infoRequestMs, epubCreationMs, urlId, q, ficInfo, epubFileName,
		h, url, isAutomated = False):
	try:
		with oil.open() as db, db, db.cursor() as curs:
			curs.execute('''
				insert into requestLog(
					infoRequestMs, epubCreationMs, urlId, query,
					ficInfo, epubFileName, hash, url, isAutomated)
				values(%s, %s, %s, %s, %s, %s, %s, %s, %s)
				''', (infoRequestMs, epubCreationMs, urlId, q, json.dumps(ficInfo),
					epubFileName, h, url, isAutomated))
		saveFicInfo(ficInfo)
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('logRequest: error: ^')

