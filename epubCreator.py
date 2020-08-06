import os
import requests
from ebooklib import epub
import threading
import datetime
import re
from dateutil.relativedelta import relativedelta
import authentications as a
import collections
import random

CACHE_DIR='epub_cache'

rippleCharset = 'rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz'
urlIdCharset = 'abcdefghijklmnopqrstuvwxyz23456789'

def randomString(length: int = 8, charset: str = None) -> str:
	charset = rippleCharset if charset is None else charset
	res = ''
	for i in range(length):
		res += random.choice(charset)
	return res

def formatRelDatePart(val, which): 
	return f"{val} {which}{'s' if val > 1 else ''} " if val > 0 else ""
def metaDataString(p):
	date = datetime.date.fromtimestamp(p['updated']/1000.0)
	dateString = f"{date.year}/{date.month}/{date.day}"
	diff = relativedelta(datetime.date.today(), datetime.date.fromtimestamp(p['updated']/1000.0))
	diffString = f"{formatRelDatePart(diff.years, 'year')}{formatRelDatePart(diff.months, 'month')}{formatRelDatePart(diff.days, 'day')}{formatRelDatePart(diff.hours, 'hour')}" 
	return f"{p['title']} by {p['author']} \n({p['words']} words, {p['chapters']} chapters, status: {p['status']}, Updated: {dateString} - {diffString} ago.)\n", p['title']
def reqJson(link, count = 5):
	cookies = {'session': a.SESSION}
	r = requests.get(link, cookies = cookies)
	try:
		p = r.json()
	except ValueError:
		if(count == 0):
			tmp = {}
			tmp['error'] = f"Page responded with status code: {str(r.status_code)}"
			return tmp
		else:
			reqJson(link, count - 1)
	return p

def worker(book, number, chapters, link):
	chapter = reqJson(f"{link}{number}")
	c = epub.EpubHtml(title=chapter['title'], file_name=f'chap_{number}.xhtml', lang='hr')
	c.content=chapter['content']
	chapters[chapter['chapterId']] = c
	return

def createEpub(link):
	chapters = {}
	chapter = reqJson(link + "1")
	print(link + "1")
	book = epub.EpubBook()
	# set metadata
	book.set_identifier(chapter['info']['urlId'])
	book.set_title(chapter['info']['title'])
	book.set_language('en')
	threads = []
	book.add_author(chapter['info']['author'])
	for i in range(1, int(chapter['info']['chapters'])+1):
		t = threading.Thread(target=worker, args=(book, i, chapters, link))
		threads.append(t)
		t.start()
	for thread in threads:
		thread.join()
	chapters = collections.OrderedDict(sorted(chapters.items()))
	for _, c in sorted(chapters.items()):
		print(c.title)
		book.add_item(c)
	print("requesting intro_page")
	intro_page = reqJson(link)
	intro = epub.EpubHtml(title='Introduction', file_name='introduction' + '.xhtml', lang='hr')
	intro.content = """
	<html>
	<head>
		<title>Introduction</title>
		<link rel="stylesheet" href="style/main.css" type="text/css" />
	</head>
	<body>
		<h1>%s</h1>
		<p><b>By: %s</b></p>
		<p>%s</p>
	</body>
	</html>
	""" % (intro_page['title'], intro_page['author'], intro_page['desc'])
	book.add_item(intro)
	# define Table Of Contents
	book.toc = (epub.Link('introduction.xhtml', 'Introduction', 'intro'),
				(epub.Section('...'),
				list(chapters.values()))
				)

	# add default NCX and Nav file
	book.add_item(epub.EpubNcx())
	book.add_item(epub.EpubNav())

	# define CSS style
	style = 'BODY {color: white;}'
	nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)

	# add CSS file
	book.add_item(nav_css)

	# basic spine
	doc_style = epub.EpubItem(
		uid="doc_style",
		file_name="style/main.css",
		media_type="text/css",
		content=open("epub_style.css").read()
	)
	nav_page = epub.EpubNav(uid='book_toc', file_name='toc.xhtml')
	nav_page.add_item(doc_style)
	book.add_item(nav_page)
	book.spine = [intro, nav_page] + list(chapters.values())

	print("creating book with name: " + intro_page['title'].replace('/', '_') + '.epub')
	if not os.path.isdir(CACHE_DIR):
		os.mkdir(CACHE_DIR)
	path_safe_title = f"{intro_page['title']} by {chapter['info']['author']}"
	path_safe_title = re.sub('[^\w\-_\.]+', '_', path_safe_title)
	path_safe_title = re.sub('_+', '_', path_safe_title)
	path_safe_title = path_safe_title.strip('_')
	#epub_fname = f"{path_safe_title}-{randomString()}.epub"
	urlId = chapter['info']['urlId']
	epub_fname = f"{path_safe_title}-{urlId}.epub"
	epub.write_epub(os.path.join(CACHE_DIR, epub_fname), book, {})
	return epub_fname

