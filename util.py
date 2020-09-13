import traceback
import json
from oil import oil

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
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('logRequest: error: ^')

