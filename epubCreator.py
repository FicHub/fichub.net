import os
import time
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
			return reqJson(link, count - 1)
	return p

def worker(book, number, chapters, link):
	chapter = reqJson(f"{link}{number}")
	c = epub.EpubHtml(title=chapter['title'], file_name=f'chap_{number}.xhtml', lang='en')
	c.content=chapter['content']
	chapters[chapter['chapterId']] = c
	return

def requestAll(link: str, expected: int):
	res = reqJson(link + "all")
	chapters = {}
	for ch in res['chapters']:
		n = ch['chapterId']
		c = epub.EpubHtml(title=ch['title'], file_name=f'chap_{n}.xhtml', lang='en')
		c.content = str(ch['content']).strip()
		if len(c.content) == 0:
			print(f'note: {link} {n} has an empty content body')
			c.content = '<p></p>'
		chapters[n] = c
	for i in range(1, expected + 1):
		if i not in chapters:
			print(f'requestAll: err: {i} not in chapters')
			print(list(chapters.keys()))
			return None
	return chapters

def createEpub(link, info = None):
	if info is None:
		info = reqJson(link)
	print(info)

	book = epub.EpubBook()
	# set metadata
	book.set_identifier(info['urlId'])
	book.set_title(info['title'])
	book.set_language('en')
	book.add_author(info['author'])

	# try to grab all chapters with the new /all endpoint first
	chapters = None
	try:
		chapters = requestAll(link, int(info['chapters']))
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('^ something went wrong :/')

	# if something went wrong, fall back to making a request per chapter
	if chapters is None:
		chapters = {}
		threads = []
		for i in range(1, int(info['chapters'])+1):
			# let's not have _too_ many requests in play at once...
			while threading.active_count() > 64:
				time.sleep(.2)
			t = threading.Thread(target=worker, args=(book, i, chapters, link))
			threads.append(t)
			t.start()
		for thread in threads:
			thread.join()
		chapters = collections.OrderedDict(sorted(chapters.items()))

	titles = []
	for _, c in sorted(chapters.items()):
		c.title = str(c.title).strip()
		titles.append(c.title)
		if c.title is None or len(c.title) < 1:
			c.title = f'Chapter {_}'
		book.add_item(c)
	print(titles)

	intro = epub.EpubHtml(title='Introduction', file_name='introduction' + '.xhtml', lang='en')
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
	""" % (info['title'], info['author'], info['desc'])
	book.add_item(intro)
	# define Table Of Contents
	book.toc = [epub.Link('introduction.xhtml', 'Introduction', 'intro')] + list(chapters.values())

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

	urlId = info['urlId']
	updated = datetime.datetime.utcfromtimestamp(int(info['updated'])/1000)

	path_safe_title = f"{info['title']} by {info['author']}"
	path_safe_title = re.sub('[^\w\-_\.]+', '_', path_safe_title)
	path_safe_title = re.sub('_+', '_', path_safe_title)
	path_safe_title = path_safe_title.strip('_')
	epub_fname = f"{path_safe_title}-{urlId}.epub"
	print(f"creating book with name: {epub_fname}")

	if not os.path.isdir(CACHE_DIR):
		os.mkdir(CACHE_DIR)
	epub.write_epub(os.path.join(CACHE_DIR, epub_fname), book, {'mtime':updated})
	return epub_fname

