from typing import Dict
import traceback
import urllib.parse
import requests
import authentications as a

def reqJson(link: str, retryCount: int = 5):
	cookies = {'session': a.SESSION}
	r = requests.get(link, cookies = cookies)
	try:
		p = r.json()
	except ValueError:
		if retryCount < 1:
			return {'error': f"Page responded with status code: {str(r.status_code)}"}
		else:
			return reqJson(link, retryCount - 1)
	return p

def lookup(query: str):
	return reqJson('/'.join([a.AX_LOOKUP_ENDPOINT, urllib.parse.quote(query)]))

class Chapter:
	def __init__(self, n: int, title: str, content: str):
		self.n = n
		self.title = title
		self.content = content

def requestAllChapters(urlId: str, expected: int) -> Dict[int, Chapter]:
	link = '/'.join([a.AX_FIC_ENDPOINT, urlId, 'all'])
	res = reqJson(link)
	chapters = {}
	titles = []
	for ch in res['chapters']:
		n = int(ch['chapterId'])

		# extract chapter content
		content = str(ch['content']).strip()
		if len(content) == 0:
			print(f'note: {link} {n} has an empty content body')
			content = '<p></p>'

		# generate a chapter name if its missing
		title = str(ch['title']).strip()
		titles.append(title)
		if title is None or len(title) < 1:
			title = f'Chapter {n}'

		# prepend content with chapter title header
		content = f'<h2>{title}</h2>' + content

		chapters[n] = Chapter(n, title, content)

	# ensure we got the number of expected chapters
	for i in range(1, expected + 1):
		if i not in chapters:
			print(f'requestAllChapters: err: {i} not in chapters')
			print(list(chapters.keys()))
			return None

	# log the chapter titles
	print(f'titles: {titles}')

	return chapters

def fetchChapters(info: Dict[str, str]) -> Dict[int, Chapter]:
	# try to grab all chapters with the new /all endpoint first
	try:
		return requestAllChapters(info['urlId'], int(info['chapters']))
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('^ something went wrong :/')
		raise


