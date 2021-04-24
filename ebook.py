from typing import Dict, Tuple, Any
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
from ebooklib import epub # type: ignore
from ax import Chapter, FicInfo
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
EXPORT_MIMETYPES = {
		'epub': 'application/epub+zip',
		'html': 'application/zip',
		'mobi': 'application/x-mobipocket-ebook',
		'pdf': 'application/pdf',
	}

def formatRelDatePart(val: int, which: str) -> str:
	return f"{val} {which}{'s' if val > 1 else ''} " if val > 0 else ""

def metaDataString(info: FicInfo) -> str:
	diff = relativedelta(datetime.datetime.now(), info.ficUpdated)
	parts = [
			(diff.years, 'year'),
			(diff.months, 'month'),
			(diff.days, 'day'),
		]
	diffString = ''
	for val, which in parts:
		diffString += formatRelDatePart(val, which)
	if len(diffString) < 1:
		diffString = 'today'
	else:
		diffString += ' ago'

	return '\n'.join([
			f"{info.title} by {info.author}",
			'(' + ', '.join([
					f"{info.words} words",
					f"{info.chapters} chapters",
					f"status: {info.status}",
					f"Updated: {info.ficUpdated.date()} - {diffString}",
				]) + ')',
			'',
		])

def buildFileSlug(title: str, author: str, urlId: str) -> str:
	slug = f"{title} by {author}"
	slug = re.sub('[^\w\-_]+', '_', slug)
	slug = re.sub('_+', '_', slug)
	slug = slug.strip('_')
	try:
		t = slug.encode('utf-8').decode('ascii', 'ignore')
		slug = t
	except:
		pass
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


ZipDateTime = Tuple[int, int, int, int, int, int]


def datetimeToZipDateTime(ts: datetime.datetime) -> ZipDateTime:
		return (ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second)


def createHtmlBundle(info: FicInfo, chapters: Dict[int, Chapter]
		) -> Tuple[str, str]:
	slug = buildFileSlug(info.title, info.author, info.id)
	bundle_fname = slug + '.html'

	tmp_fname = randomTempFile(f'{info.id}.zip')

	nchaps = chapters.values()
	data = render_template('full_fic.html', info=info, chapters=nchaps)
	with zipfile.ZipFile(tmp_fname, 'w') as zf:
		zinfo = zipfile.ZipInfo(bundle_fname,
				datetimeToZipDateTime(info.ficUpdated))
		zf.writestr(zinfo, data, compress_type=zipfile.ZIP_DEFLATED)

	return relocateFinishedExport('html', info.id, tmp_fname)


def convertEpub(info: FicInfo, chapters: Dict[int, Chapter], etype: str
		) -> Tuple[str, str]:
	if etype not in EXPORT_TYPES:
		raise Exception(f'convertEpub: invalid etype: {etype}')

	suff = EXPORT_SUFFIXES[etype]
	tmp_fname = randomTempFile(f'{info.id}{suff}')

	epub_fname, ehash = createEpub(info, chapters)

	try:
		res = subprocess.run(\
				['/home/fichub_net/fichub.net/janus.py', epub_fname, tmp_fname],
				timeout=60*5,
			)
		if res.returncode != 0:
			raise Exception(f'convertEpub: error: return code {res.returncode} != 0')
	except:
		raise

	return relocateFinishedExport(etype, info.id, tmp_fname)


def buildEpubChapters(chapters: Dict[int, Chapter]) -> Dict[int, epub.EpubHtml]:
	epubChapters = {}
	for n in chapters:
		ch = chapters[n]
		c = epub.EpubHtml(title=ch.title, file_name=f'chap_{n}.xhtml', lang='en')
		c.title = ch.title
		c.content = ch.content
		epubChapters[n] = c
	return epubChapters

def createEpub(info: FicInfo, rawChapters: Dict[int, Chapter]
		) -> Tuple[str, str]:
	print(info.__dict__)

	book = epub.EpubBook()
	# set metadata
	book.set_identifier(info.id)
	book.set_title(info.title)
	book.set_language('en')
	book.add_author(info.author)

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

	intro = epub.EpubHtml(title='Introduction', file_name='introduction.xhtml', lang='en')
	intro.content = render_template('epub_introduction.html', info=info)

	book.add_item(intro)
	# define Table Of Contents
	book.toc = [epub.Link('introduction.xhtml', 'Introduction', 'intro')] + list(chapters.values())

	# add default NCX and Nav file
	book.add_item(epub.EpubNcx())
	book.add_item(epub.EpubNav())

	# define CSS style
	style = 'BODY {color: white;}'
	nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css",
			media_type="text/css", content=style)

	# add CSS file
	book.add_item(nav_css)

	# basic spine
	nav_page = epub.EpubNav(uid='book_toc', file_name='toc.xhtml')
	nav_page.add_item(doc_style)
	book.add_item(nav_page)
	book.spine = [intro, nav_page] + list(chapters.values())

	tmp_fname = randomTempFile(f'{info.id}.epub')
	epub.write_epub(tmp_fname, book,
			{'mtime':info.ficUpdated, 'play_order':{'enabled':True}})

	return relocateFinishedExport('epub', info.id, tmp_fname)

