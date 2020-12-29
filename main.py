from typing import Any, Dict, Union, Tuple, Optional, cast
import os
import os.path
import time
import traceback
import json
import random
import math
import datetime
from enum import IntEnum
from flask import Flask, Response, jsonify, request, render_template, \
	send_from_directory, redirect, url_for
import werkzeug.wrappers
from werkzeug.exceptions import HTTPException, NotFound

app = Flask(__name__, static_url_path='')

BasicFlaskResponse = Union[Response, werkzeug.wrappers.Response, str]
FlaskResponse = Union[BasicFlaskResponse, Tuple[BasicFlaskResponse, int]]

import ax
from ax import FicInfo, RequestLog, RequestSource
import ebook
import authentications as a

CACHE_BUSTER='25'
CSS_CACHE_BUSTER=CACHE_BUSTER
JS_CACHE_BUSTER=CACHE_BUSTER
CURRENT_CSS=None

class WebError(IntEnum):
	success = 0
	no_query = -1
	invalid_etype = -2
	export_failed = -3
	ensure_failed = -4

errorMessages = {
		WebError.success: 'success',
		WebError.no_query: 'no query',
		WebError.invalid_etype: 'invalid etype',
		WebError.export_failed: 'export failed',
		WebError.ensure_failed: 'ensure failed',
	}

def getErr(err: WebError, extra: Optional[Dict[str, Any]] = None
		) -> Dict[str, Any]:
	base = {'err':int(err),'msg':errorMessages[err]}
	if extra is not None:
		base.update(extra)
	return base

@app.errorhandler(404)
def page_not_found(e: HTTPException) -> FlaskResponse:
	return render_template('404.html'), 404

@app.route('/')
def index() -> FlaskResponse:
	return render_template('index.html')

@app.route('/changes')
def changes() -> FlaskResponse:
	return render_template('changes.html', fullHistory=True)

@app.route('/cache/', defaults={'page': 1})
@app.route('/cache/<int:page>')
def cache_listing_deprecated(page: int) -> FlaskResponse:
	return redirect(url_for('cache_listing_today'))

@app.route('/cache/today/', defaults={'page': 1})
@app.route('/cache/today/<int:page>')
def cache_listing_today(page: int) -> FlaskResponse:
	today = datetime.date.today()
	return cache_listing(today.year, today.month, today.day, page)

@app.route('/cache/<int:year>/<int:month>/<int:day>/', defaults={'page': 1})
@app.route('/cache/<int:year>/<int:month>/<int:day>/<int:page>')
def cache_listing(year: int, month: int, day: int, page: int) -> FlaskResponse:
	date = None
	try:
		date = datetime.date(year, month, day)
	except Exception as e:
		return redirect(url_for('cache_listing_today'))

	if page < 1:
		return redirect(url_for('cache_listing', year=year, month=month, day=day))

	fis = {fi.id: fi for fi in FicInfo.select()}
	rls = RequestLog.mostRecentEpub(date)
	prevDay = RequestLog.prevDay(date)
	nextDay = RequestLog.nextDay(date)

	pageSize = 300 if len(rls) < 300 else 200
	pageCount = int(math.floor((len(rls) + (pageSize - 1)) / pageSize))

	if page > pageCount and page > 1:
		return redirect(url_for('cache_listing', year=year, month=month, day=day,
				page=pageCount))

	# trim to entries on requested page
	rls = rls[(page - 1) * pageSize:page * pageSize]

	items = []
	for rl in rls:
		href = url_for(f'get_cached_export', etype='epub', urlId=rl.urlId,
				fname=f'{rl.exportFileHash}.epub')

		fi = fis[rl.urlId] if rl.urlId in fis else None
		dt = rl.created

		# if we have FicInfo, generate a more direct link to the epub
		if fi is not None:
			slug = ebook.buildFileSlug(fi.title, fi.author, fi.id)
			href = url_for('get_cached_export', etype='epub', urlId=fi.id,
					fname=f'{slug}.epub', h=rl.exportFileHash)

		sourceUrl = ''
		if fi is not None and fi.source is not None:
			sourceUrl = fi.source
		else:
			try:
				info = json.loads(rl.ficInfo)
				if 'source' in info:
					sourceUrl = info['source']
			except:
				pass

		items.append({'href':href, 'ficInfo':fi, 'requestLog':rl, 'created':dt,
			'sourceUrl':sourceUrl})

	return render_template('cache.html', cache=items, pageCount=pageCount,
			page=page, prevDay=prevDay, nextDay=nextDay, date=date)

def try_ensure_export(etype: str, query: str) -> Optional[str]:
	key = f'{etype}_fname'
	res = ensure_export(etype, query)
	if 'err' in res or key not in res:
		return None
	if res[key] is None or isinstance(res[key], str):
		return cast(Optional[str], res[key])
	return None

class InvalidEtypeException(Exception):
	pass

def ensure_export(etype: str, query: str) -> Dict[str, Any]:
	print(f'ensure_export: query: {query}')
	if etype not in ebook.EXPORT_TYPES:
		return getErr(WebError.invalid_etype,
				{'fn': 'ensure_export', 'etype': etype})
	remoteAddr = request.headers.get('X-Real-IP', 'unknown')
	urlRoot = request.headers.get('X-Real-Root', request.url_root)
	isAutomated = (request.args.get('automated', None) == 'true')
	source = RequestSource.upsert(isAutomated, urlRoot, remoteAddr)

	initTimeMs = int(time.time() * 1000)
	lres = ax.lookup(query)
	if 'err' in lres:
		endTimeMs = int(time.time() * 1000)
		RequestLog.insert(source, etype, query, endTimeMs - initTimeMs, None,
				json.dumps(lres), None, None, None, None)
		lres['upstream'] = True
		return lres
	meta = FicInfo.parse(lres)
	infoTimeMs = int(time.time() * 1000)
	infoRequestMs = infoTimeMs - initTimeMs

	etext = None
	try:
		# TODO we could be timing this too...
		metaString = ebook.metaDataString(meta)
		chapters = ax.fetchChapters(meta)

		# actually do the export
		fname, fhash = None, None
		if etype == 'epub':
			fname, fhash = ebook.createEpub(meta, chapters)
		elif etype == 'html':
			fname, fhash = ebook.createHtmlBundle(meta, chapters)
		elif etype in ['mobi', 'pdf']:
			fname, fhash = ebook.convertEpub(meta, chapters, etype)
		else:
			raise InvalidEtypeException(f'err: unknown etype: {etype}')

		exportFileName = os.path.basename(fname)

		slug = ebook.buildFileSlug(meta.title, meta.author, meta.id)
		suff = ebook.EXPORT_SUFFIXES[etype]
		exportUrl = url_for(f'get_cached_export', etype=etype, urlId=meta.id,
				fname=f'{slug}{suff}', h=fhash)

		endTimeMs = int(time.time() * 1000)
		exportMs = endTimeMs - infoTimeMs

		RequestLog.insert(source, etype, query, infoRequestMs, meta.id,
				json.dumps(lres), exportMs, fname, fhash, exportUrl)

		return {'urlId': meta.id, 'info': metaString,
				f'{etype}_fname': fname, 'hash': fhash, 'url': exportUrl}
	except Exception as e:
		endTimeMs = int(time.time() * 1000)
		exportMs = endTimeMs - infoTimeMs
		RequestLog.insert(source, etype, query, endTimeMs - initTimeMs, meta.id,
				json.dumps(lres), exportMs, None, None, None)

		if e.args is not None and len(e.args) > 0:
			if isinstance(e, ax.MissingChapterException):
				etext = e.args[0]
			elif isinstance(e, InvalidEtypeException):
				etext = e.args[0]

		traceback.print_exc()
		print(e)
		print('ensure_export: ^ something went wrong :/')

	return getErr(WebError.export_failed, {
			'msg': f'{etype} export failed; please report this on discord',
			'etext': etext,
			'meta': {
					'id': meta.id,
					'title': meta.title,
					'author': meta.author,
					'chapters': meta.chapters,
					'created': meta.ficCreated,
					'updated': meta.ficUpdated,
					'status': meta.status,
					'source': meta.source,
				},
		})

def legacy_cache_redirect(etype: str, fname: str) -> FlaskResponse:
	fhash = request.args.get('h', None)
	urlId = fname
	if urlId.find('-') >= 0:
		urlId = urlId.split('-')[-1]
	suff = ebook.EXPORT_SUFFIXES[etype]
	if urlId.endswith(suff):
		urlId = urlId[:-len(suff)]
	if fhash is None:
		return redirect(url_for('get_cached_export_partial', etype=etype,
			urlId=urlId, cv=CACHE_BUSTER))
	return redirect(url_for('get_cached_export', etype=etype, urlId=urlId,
		fname=f'{fhash}{suff}', cv=CACHE_BUSTER))

@app.route('/epub/<fname>')
def get_cached_epub_v0(fname: str) -> FlaskResponse:
	return legacy_cache_redirect('epub', fname)

@app.route('/html/<fname>')
def get_cached_html_v0(fname: str) -> FlaskResponse:
	return legacy_cache_redirect('html', fname)

@app.route('/cache/<etype>/<urlId>/<fname>')
def get_cached_export(etype: str, urlId: str, fname: str) -> FlaskResponse:
	if etype not in ebook.EXPORT_TYPES:
		# if this is an unsupported export type, 404
		return page_not_found(NotFound())

	mimetype = ebook.EXPORT_MIMETYPES[etype]
	suff = ebook.EXPORT_SUFFIXES[etype]
	if not fname.endswith(suff):
		# we have a request for the wrong extension, 404
		return page_not_found(NotFound())

	fhash = request.args.get('h', None)
	fdir = os.path.join(ebook.CACHE_DIR, etype, urlId)
	if fhash is not None:
		# if the request is for a specific slug, try to serve it directly
		rname = fname
		fname = f'{fhash}{suff}'
		if os.path.isfile(os.path.join(fdir, fname)):
			return send_from_directory(fdir, fname, as_attachment=True,
					attachment_filename=rname, mimetype=mimetype,
					cache_timeout=(60*60*24*365))
		# fall through...

	# otherwise find the most recent export and give them that
	allInfo = FicInfo.select(urlId)
	if len(allInfo) < 1:
		# entirely unknown fic, 404
		return page_not_found(NotFound())
	ficInfo = allInfo[0]
	slug = ebook.buildFileSlug(ficInfo.title, ficInfo.author, urlId)
	rl = RequestLog.mostRecentByUrlId(etype, urlId)
	if rl is None:
		return page_not_found(NotFound())

	if not os.path.isfile(os.path.join(fdir, f'{rl.exportFileHash}{suff}')):
		# the most recent export is missing for some reason... 404
		return page_not_found(NotFound())

	# redirect back to ourself with the correct filename
	return redirect(url_for('get_cached_export', etype=etype, urlId=urlId,
		fname=f'{slug}{suff}', h=rl.exportFileHash))

@app.route('/cache/<etype>/<urlId>')
def get_cached_export_partial(etype: str, urlId: str) -> Any:
	if etype not in ebook.EXPORT_TYPES:
		# if this is an unsupported export type, 404
		return page_not_found(NotFound())

	# otherwise we have a urlId we need to export
	fname = try_ensure_export(etype, urlId)
	if fname is None:
		# if we failed to generate the export, 404
		return page_not_found(NotFound())

	return get_cached_export(etype, urlId, fname)


@app.route('/api/v0/epub', methods=['GET'])
def api_v0_epub() -> Any:
	q = request.args.get('q', None)
	if q is None or len(q.strip()) < 1:
		return jsonify(getErr(WebError.no_query))

	print(f'api_v0_epub: query: {q}')
	eres = ensure_export('epub', q)
	if 'err' in eres:
		return jsonify(eres)
	for key in ['epub_fname', 'urlId', 'url']:
		if key not in eres:
			return jsonify(getErr(WebError.ensure_failed, {
					'key': key, 'msg': 'please report this on discord'
				}))

	info = '[missing metadata; please report this on discord]'
	if 'info' in eres:
		info = eres['info']
	eh = eres['hash'] if 'hash' in eres else str(random.getrandbits(32))

	res = { 'err':0, 'info':info, 'urlId':eres['urlId'], }

	# build auto-generating links for all formats
	for etype in ebook.EXPORT_TYPES:
		if etype == 'epub':
			continue # we already exported epub
		res[f'{etype}_url'] = url_for(f'get_cached_export_partial', etype=etype,
				urlId=eres['urlId'], cv=CACHE_BUSTER, eh=eh)

	# update epub url to direct download
	res['epub_url'] = eres['url']

	return jsonify(res)

@app.context_processor
def inject_cache_buster() -> Dict[str, str]:
	return {'CACHE_BUSTER': CACHE_BUSTER, 'CURRENT_CSS': CURRENT_CSS,
			'JS_CACHE_BUSTER': JS_CACHE_BUSTER, 'CSS_CACHE_BUSTER': CSS_CACHE_BUSTER}

if __name__ == '__main__':
	app.run(debug=True)

print()
print(__name__)
if __name__ == 'uwsgi_file___main':
	CSS_CACHE_BUSTER = str(time.time())
	JS_CACHE_BUSTER = CSS_CACHE_BUSTER
	print(f'reset JS/CSS CACHE_BUSTER: {JS_CACHE_BUSTER}')

	if os.path.isfile('./static/style/_.css'):
		with open('./static/style/_.css') as f:
			CURRENT_CSS = f.read().strip()
		print(f'reset CURRENT_CSS to len {len(CURRENT_CSS)}')

	if os.path.isfile('./static/js/_.js'):
		import util
		jshash = util.hashFile('./static/js/_.js')
		if len(jshash) == 32:
			JS_CACHE_BUSTER = jshash
		print(f'reset JS_CACHE_BUSTER: {JS_CACHE_BUSTER}')
	print()

