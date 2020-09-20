import datetime
import traceback
import json
from oil import oil

def saveFicInfo(ficInfo):
	try:
		with oil.open() as db:
			with db.cursor() as curs:
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

def logRequest(infoRequestMs, epubCreationMs, urlId, q, ficInfo, epubFileName, h, url):
	try:
		with oil.open() as db:
			with db.cursor() as curs:
				curs.execute('''
					insert into requestLog(
						infoRequestMs, epubCreationMs, urlId, query,
						ficInfo, epubFileName, hash, url)
					values(%s, %s, %s, %s, %s, %s, %s, %s)
					''', (infoRequestMs, epubCreationMs, urlId, q, json.dumps(ficInfo),
						epubFileName, h, url))
			saveFicInfo(ficInfo)
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('logRequest: error: ^')

