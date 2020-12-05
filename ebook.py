from typing import Dict
import os
import traceback
import datetime
import re
import zipfile
from dateutil.relativedelta import relativedelta
from flask import render_template
from ebooklib import epub
from ax import Chapter

EPUB_CACHE_DIR='cache/epub'
HTML_CACHE_DIR='cache/html'

def formatRelDatePart(val, which): 
	return f"{val} {which}{'s' if val > 1 else ''} " if val > 0 else ""
def metaDataString(p):
	date = datetime.date.fromtimestamp(p['updated']/1000.0)
	dateString = f"{date.year}/{date.month}/{date.day}"
	diff = relativedelta(datetime.date.today(), datetime.date.fromtimestamp(p['updated']/1000.0))
	diffString = f"{formatRelDatePart(diff.years, 'year')}{formatRelDatePart(diff.months, 'month')}{formatRelDatePart(diff.days, 'day')}{formatRelDatePart(diff.hours, 'hour')}" 
	return f"{p['title']} by {p['author']} \n({p['words']} words, {p['chapters']} chapters, status: {p['status']}, Updated: {dateString} - {diffString} ago.)\n", p['title']

def buildFileSlug(title: str, author: str, urlId: str) -> str:
	slug = f"{title} by {author}"
	slug = re.sub('[^\w\-_]+', '_', slug)
	slug = re.sub('_+', '_', slug)
	slug = slug.strip('_')
	return f"{slug}-{urlId}"


def createHtmlBundle(info, chapters) -> None:
	if not os.path.isdir(HTML_CACHE_DIR):
		os.makedirs(HTML_CACHE_DIR)

	urlId = info['urlId']
	slug = buildFileSlug(info['title'], info['author'], urlId)

	bundle_zip_fname = os.path.join(HTML_CACHE_DIR, slug + '.zip')
	bundle_fname = slug + '.html'
	nchaps = chapters.values()
	data = render_template('full_fic.html', info=info, chapters=nchaps)
	with zipfile.ZipFile(bundle_zip_fname, 'w') as zf:
		zf.writestr(bundle_fname, data, compress_type=zipfile.ZIP_DEFLATED)

	return slug + '.zip'


def buildEpubChapters(chapters: Dict[int, Chapter]):
	epubChapters = {}
	for n in chapters:
		ch = chapters[n]
		c = epub.EpubHtml(title=ch.title, file_name=f'chap_{n}.xhtml', lang='en')
		c.title = ch.title
		c.content = ch.content
		epubChapters[n] = c
	return epubChapters

def createEpub(info, rawChapters):
	print(info)

	book = epub.EpubBook()
	# set metadata
	book.set_identifier(info['urlId'])
	book.set_title(info['title'])
	book.set_language('en')
	book.add_author(info['author'])

	chapters = buildEpubChapters(rawChapters)
	for _, c in sorted(chapters.items()):
		book.add_item(c)

	sourceUrl = ''
	if 'source' in info:
		sourceUrl = info['source']

	intro = epub.EpubHtml(title='Introduction', file_name='introduction' + '.xhtml', lang='en')
	intro.content = render_template('epub_introduction.html',
			title=info['title'], author=info['author'], desc=info['desc'],
			sourceUrl=sourceUrl)

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
	book.add_item(doc_style)

	nav_page = epub.EpubNav(uid='book_toc', file_name='toc.xhtml')
	nav_page.add_item(doc_style)
	book.add_item(nav_page)
	book.spine = [intro, nav_page] + list(chapters.values())

	urlId = info['urlId']
	updated = datetime.datetime.utcfromtimestamp(int(info['updated'])/1000)

	slug = buildFileSlug(info['title'], info['author'], urlId)
	epub_fname = f"{slug}.epub"
	print(f"creating book with name: {epub_fname}")

	if not os.path.isdir(EPUB_CACHE_DIR):
		os.makedirs(EPUB_CACHE_DIR)
	epub.write_epub(os.path.join(EPUB_CACHE_DIR, epub_fname), book,
			{'mtime':updated, 'play_order':{'enabled':True}})

	return epub_fname

