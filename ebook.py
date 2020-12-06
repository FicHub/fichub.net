from typing import Dict, Tuple
import os
import traceback
import datetime
import re
import zipfile
import subprocess
import random
import threading
from dateutil.relativedelta import relativedelta
from flask import render_template
from ebooklib import epub
from ax import Chapter
import util

TMP_DIR='tmp'
CACHE_DIR='cache'

EXPORT_TYPES = ['epub', 'html', 'mobi', 'pdf']
EXPORT_SUFFIXES = {
		'epub': '.epub',
		'html': '.zip',
		'mobi': '.mobi',
		'pdf': '.pdf',
	}

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


def randomTempFile(extra: str, bits: int = 32) -> str:
	tdir = os.path.join(TMP_DIR, str(os.getpid()))
	if not os.path.isdir(tdir):
		os.makedirs(tdir)
	rbits = random.getrandbits(bits)
	fname = f'{threading.get_ident()}_{rbits:x}_{extra}'
	return os.path.join(tdir, fname)


def relocateFinishedExport(etype: str, urlId: str, tname: str
		) -> Tuple[str, str]:
	fhash = util.hashFile(tname)
	fdir = os.path.join(CACHE_DIR, etype, urlId)
	if not os.path.isdir(fdir):
		os.makedirs(fdir)
	suff = EXPORT_SUFFIXES[etype]
	fname = os.path.join(fdir, f'{fhash}{suff}')
	os.rename(tname, fname)

	return (fname, fhash)


def createHtmlBundle(info, chapters) -> None:
	urlId = info['urlId']
	slug = buildFileSlug(info['title'], info['author'], urlId)
	bundle_fname = slug + '.html'

	tmp_fname = randomTempFile(f'{urlId}.zip')

	nchaps = chapters.values()
	data = render_template('full_fic.html', info=info, chapters=nchaps)
	with zipfile.ZipFile(tmp_fname, 'w') as zf:
		zf.writestr(bundle_fname, data, compress_type=zipfile.ZIP_DEFLATED)

	return relocateFinishedExport('html', urlId, tmp_fname)


def convertEpub(info, chapters, etype) -> Tuple[str, str]:
	if etype not in EXPORT_TYPES:
		raise Exception(f'convertEpub: invalid etype: {etype}')

	urlId = info['urlId']
	suff = EXPORT_SUFFIXES[etype]
	tmp_fname = randomTempFile(f'{urlId}{suff}')

	epub_fname, ehash = createEpub(info, chapters)

	try:
		subprocess.run(['ebook-convert', epub_fname, tmp_fname])
	except:
		raise

	return relocateFinishedExport(etype, urlId, tmp_fname)


def buildEpubChapters(chapters: Dict[int, Chapter]):
	epubChapters = {}
	for n in chapters:
		ch = chapters[n]
		c = epub.EpubHtml(title=ch.title, file_name=f'chap_{n}.xhtml', lang='en')
		c.title = ch.title
		c.content = ch.content
		epubChapters[n] = c
	return epubChapters

def createEpub(info, rawChapters) -> Tuple[str, str]:
	print(info)

	book = epub.EpubBook()
	# set metadata
	book.set_identifier(info['urlId'])
	book.set_title(info['title'])
	book.set_language('en')
	book.add_author(info['author'])

	# document style
	doc_style = epub.EpubItem(
		uid="doc_style",
		file_name="style/main.css",
		media_type="text/css",
		content=open("epub_style.css").read()
	)
	book.add_item(doc_style)

	chapters = buildEpubChapters(rawChapters)
	for _, c in sorted(chapters.items()):
		c.add_item(doc_style)
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
	nav_page = epub.EpubNav(uid='book_toc', file_name='toc.xhtml')
	nav_page.add_item(doc_style)
	book.add_item(nav_page)
	book.spine = [intro, nav_page] + list(chapters.values())

	urlId = info['urlId']
	updated = datetime.datetime.utcfromtimestamp(int(info['updated'])/1000)

	tmp_fname = randomTempFile(f'{urlId}.epub')
	epub.write_epub(tmp_fname, book,
			{'mtime':updated, 'play_order':{'enabled':True}})

	return relocateFinishedExport('epub', urlId, tmp_fname)

