from typing import Dict, Tuple, Any, Optional
import os
import shutil
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
from db import ExportLog
import util

TMP_DIR='tmp'
CACHE_DIR='/mnt/fichub/cache'

# total version is EXPORT_VERSION + EXPORT_TYPE_VERSIONS[etype]
EXPORT_VERSION=1
EXPORT_TYPES = ['epub', 'html', 'mobi', 'pdf']
EXPORT_TYPE_VERSIONS = {
		'epub': 0,
		'html': 1,
		'mobi': 0,
		'pdf': 0,
	}
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
# TODO the frontend should not have its own copy here
EXPORT_DESCRIPTIONS = {
		'epub': 'EPUB',
		'html': 'zipped HTML',
		'mobi': 'MOBI',
		'pdf': 'PDF',
	}

def exportVersion(etype: str) -> int:
	if etype in EXPORT_TYPE_VERSIONS:
		return EXPORT_VERSION + EXPORT_TYPE_VERSIONS[etype]
	return EXPORT_VERSION

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


def buildExportPath(etype: str, urlId: str, create: bool = False) -> str:
	urlId = urlId.lower()
	parts = [CACHE_DIR, etype]
	for i in range(0, len(urlId), 3):
		parts.append(urlId[i:i + 3])
	parts.append(urlId)
	fdir = os.path.join(*parts)
	if create and not os.path.isdir(fdir):
		os.makedirs(fdir)
	return fdir


def buildExportName(etype: str, urlId: str, fhash: str, create: bool = False) -> str:
	fdir = buildExportPath(etype, urlId, create)
	suff = EXPORT_SUFFIXES[etype]
	return os.path.join(fdir, f'{fhash}{suff}')


def finalizeExport(etype: str, urlId: str, ihash: str, tname: str
		) -> Tuple[str, str]:
	fhash = util.hashFile(tname)
	fname = buildExportName(etype, urlId, fhash, create=True)
	shutil.move(tname, fname)

	# record this result so we can immediately return it next time, assuming the
	# input hash and export version have not changed
	try:
		n = datetime.datetime.now()
		el = ExportLog(urlId, exportVersion(etype), etype, ihash, fhash, n)
		el.upsert()
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('finalizeExport: ^ something went wrong :/')

	return (fname, fhash)


def findExistingExport(etype: str, urlId: str, ihash: str
		) -> Optional[Tuple[str, str]]:
	try:
		el = ExportLog.lookup(urlId, exportVersion(etype), etype, ihash)
		if el is None:
			return None
		fname = buildExportName(etype, urlId, el.exportHash)
		if not os.path.isfile(fname):
			return None
		return (fname, el.exportHash)
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('findExistingExport: ^ something went wrong :/')
	return None


ZipDateTime = Tuple[int, int, int, int, int, int]


def datetimeToZipDateTime(ts: datetime.datetime) -> ZipDateTime:
		return (ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second)


def createHtmlBundle(info: FicInfo, chapters: Dict[int, Chapter]
		) -> Tuple[str, str]:
	slug = buildFileSlug(info.title, info.author, info.id)
	bundle_fname = slug + '.html'

	_, ehash = createEpub(info, chapters)
	ee = findExistingExport('html', info.id, ehash)
	if ee is not None:
		return ee

	tmp_fname = randomTempFile(f'{info.id}.zip')

	nchaps = chapters.values()
	data = render_template('full_fic.html', info=info, chapters=nchaps)
	with zipfile.ZipFile(tmp_fname, 'w') as zf:
		zinfo = zipfile.ZipInfo(bundle_fname,
				datetimeToZipDateTime(info.ficUpdated))
		zf.writestr(zinfo, data, compress_type=zipfile.ZIP_DEFLATED)

	return finalizeExport('html', info.id, ehash, tmp_fname)


def convertEpub(info: FicInfo, chapters: Dict[int, Chapter], etype: str
		) -> Tuple[str, str]:
	if etype not in EXPORT_TYPES:
		raise Exception(f'convertEpub: invalid etype: {etype}')

	suff = EXPORT_SUFFIXES[etype]
	tmp_fname = randomTempFile(f'{info.id}{suff}')

	epub_fname, ehash = createEpub(info, chapters)
	ee = findExistingExport(etype, info.id, ehash)
	if ee is not None:
		return ee

	try:
		res = subprocess.run(\
				['/home/fichub/fichub.net/janus.py', epub_fname, tmp_fname],
				timeout=60*5,
			)
		if res.returncode != 0:
			raise Exception(f'convertEpub: error: return code {res.returncode} != 0')
	except:
		raise

	return finalizeExport(etype, info.id, ehash, tmp_fname)


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

	# define CSS style
	style = 'BODY {color: white;}'
	nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css",
			media_type="text/css", content=style)

	# add CSS file
	book.add_item(nav_css)

	# introduction
	intro = epub.EpubHtml(title='Introduction', file_name='introduction.xhtml', lang='en')
	intro.content = render_template('epub_introduction.html', info=info)
	book.add_item(intro)

	# nav page
	nav_page = epub.EpubNav(uid='nav', file_name='nav.xhtml')
	nav_page.add_item(doc_style)
	book.add_item(nav_page)

	# actual chapter content
	chapters = buildEpubChapters(rawChapters)
	for _, c in sorted(chapters.items()):
		c.add_item(doc_style)
		book.add_item(c)

	# define Table Of Contents
	book.toc = [epub.Link('introduction.xhtml', 'Introduction', 'intro')] + list(chapters.values())

	# basic spine
	book.spine = [intro, nav_page] + list(chapters.values())

	# add default NCX file
	book.add_item(epub.EpubNcx())

	tmp_fname = randomTempFile(f'{info.id}.epub')
	epub.write_epub(tmp_fname, book,
			{'mtime':info.ficUpdated, 'play_order':{'enabled':True}})

	return finalizeExport('epub', info.id, 'upstream', tmp_fname)

