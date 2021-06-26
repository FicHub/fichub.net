from typing import Dict, Any, Optional, List, Tuple
import datetime
import traceback
import urllib.parse
from db import FicInfo
import es
import util
import authentications as a

def alive() -> bool:
	try:
		url = '/'.join([a.AX_LOOKUP_ENDPOINT])
		m = util.reqJson(url, timeout=5.0)
	except:
		return False
	return True

def lookup(query: str, timeout: float = 280.0) -> Dict[str, Any]:
	url = '/'.join([a.AX_LOOKUP_ENDPOINT, urllib.parse.quote(query, safe='')])
	meta = util.reqJson(url, timeout=timeout)
	if 'error' in meta and 'err' not in meta:
		meta['err'] = meta.pop('error', None)
	if 'err' not in meta:
		FicInfo.save(meta)
		try:
			fis = FicInfo.select(meta['urlId'])
			es.save(fis[0])
		except Exception as e:
			traceback.print_exc()
			print(e)
			print('lookup: ^ something went wrong saving es data :/')
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

