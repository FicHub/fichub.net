from typing import Any, Dict, Union, Tuple
import os
import os.path
import hashlib
import time
import traceback
import json
import random
from enum import IntEnum
from flask import Flask, Response, jsonify, request, render_template, \
	send_from_directory, redirect, url_for
from werkzeug.exceptions import NotFound
from util import FicInfo, RequestLog, RequestSource
#from oil import oil
#import weaver.enc as enc
#from weaver import Web, WebScraper, WebQueue

#db = oil.open()
app = Flask(__name__, static_url_path='')

import ax
import ebook
import authentications as a

CACHE_BUSTER=9

class WebError(IntEnum):
	success = 0
	no_body = -1

errorMessages = {
		WebError.success: 'success',
		WebError.no_body: 'no body',
	}

def getErr(err: WebError) -> Dict[str, Any]:
	return {'error':int(err),'msg':errorMessages[err]}

@app.errorhandler(404)
def page_not_found(e):
	return render_template('404.html'), 404

@app.route('/')
def index() -> str:
	return render_template('index.html', CACHE_BUSTER=CACHE_BUSTER)

def hashFile(fname: str) -> str:
	digest = 'hash_err'
	with open(fname, 'rb') as f:
		data = f.read()
		digest = hashlib.md5(data).hexdigest()
	return digest

@app.route('/cache/')
def cache_listing() -> str:
	fis = {fi.id: fi for fi in FicInfo.select()}
	rls = {rl.urlId: rl for rl in RequestLog.mostRecent()}
	items = []
	if not os.path.isdir(ebook.EPUB_CACHE_DIR):
		os.makedirs(ebook.EPUB_CACHE_DIR)
	for f in os.listdir(ebook.EPUB_CACHE_DIR):
		if len(str(f).strip()) < 1:
			continue
		href = url_for('get_cached_export', etype='epub', fname=f, cv=CACHE_BUSTER)
		urlId = f.split('-')[-1]
		if not urlId.endswith('.epub'):
			continue
		urlId = urlId[:-len('.epub')]
		fi = fis[urlId] if urlId in fis else None
		rl = rls[urlId] if urlId in rls else None
		if rl is None:
			continue
		dt = rl.created

		sourceUrl = ''
		try:
			info = json.loads(rl.ficInfo)
			if 'source' in info:
				sourceUrl = info['source']
		except:
			pass

		items.append({'href':href, 'fname':f, 'ficInfo':fi, 'requestLog':rl,
			'created':dt, 'sourceUrl':sourceUrl})
	sitems = sorted(items, key=lambda e: e['created'], reverse=True)
	return render_template('cache.html', cache=sitems, CACHE_BUSTER=CACHE_BUSTER)

def try_ensure_export(etype: str, query: str) -> str:
	key = f'{etype}_fname'
	res = ensure_export(etype, query)
	if res is None or 'error' in res or key not in res:
		return None
	return res[key]

def ensure_export(etype: str, query: str) -> str:
	if etype not in ebook.EXPORT_TYPES:
		return {'error': -2, 'msg': 'invalid ensure_export etype', 'etype': etype}
	remoteAddr = request.headers.get('X-Real-IP', 'unknown')
	urlRoot = request.headers.get('X-Real-Root', request.url_root)
	isAutomated = (request.args.get('automated', None) == 'true')
	source = RequestSource.upsert(isAutomated, urlRoot, remoteAddr)

	initTimeMs = int(time.time() * 1000)
	meta = ax.lookup(query)
	if 'error' in meta:
		endTimeMs = int(time.time() * 1000)
		RequestLog.insert(source, etype, query, endTimeMs - initTimeMs, None,
				json.dumps(meta), None, None, None, None)
		return meta
	infoTimeMs = int(time.time() * 1000)
	infoRequestMs = infoTimeMs - initTimeMs

	urlId = None
	if meta is not None and 'urlId' in meta:
		urlId = meta['urlId']

	try:
		# TODO we could be timing this too...
		info, ficName = ebook.metaDataString(meta)
		chapters = ax.fetchChapters(meta)

		# actually do the export
		fname = None
		if etype == 'epub':
			fname = ebook.createEpub(meta, chapters)
		elif etype == 'html':
			fname = ebook.createHtmlBundle(meta, chapters)
		elif etype in ['mobi', 'pdf']:
			fname = ebook.convertEpub(meta, chapters, etype)
		else:
			raise Exception('FIXME')

		edir = os.path.join(ebook.CACHE_DIR, etype)
		exportFileName = os.path.join(edir, fname)
		# TODO technically this has a race condition...
		exportFileHash = hashFile(exportFileName)
		exportUrl = url_for(f'get_cached_export', etype=etype, fname=fname,
				h=exportFileHash, cv=CACHE_BUSTER)

		endTimeMs = int(time.time() * 1000)
		exportMs = endTimeMs - infoTimeMs

		RequestLog.insert(source, etype, query, infoRequestMs, urlId,
				json.dumps(meta), exportMs, exportFileName, exportFileHash, exportUrl)

		return {'urlId': urlId, 'info': info,
				f'{etype}_fname': fname, 'hash': exportFileHash, 'url': exportUrl}
	except Exception as e:
		endTimeMs = int(time.time() * 1000)
		exportMs = endTimeMs - infoTimeMs
		RequestLog.insert(source, etype, query, endTimeMs - initTimeMs, urlId,
				json.dumps(meta), exportMs, None, None, None)

		traceback.print_exc()
		print(e)
		print('^ something went wrong :/')

	return {'error': -1, 'msg': 'please report this on discord'}

@app.route('/epub/<fname>')
def get_cached_epub_v0(fname: str) -> Any:
	h = request.args.get('h', str(random.getrandbits(32)))
	return redirect(url_for('get_cached_export', etype='epub', fname=fname,
		cv=CACHE_BUSTER, h=h))

@app.route('/html/<fname>')
def get_cached_html_v0(fname: str) -> Any:
	h = request.args.get('h', str(random.getrandbits(32)))
	return redirect(url_for('get_cached_export', etype='html', fname=fname,
		cv=CACHE_BUSTER, h=h))

@app.route('/cache/<etype>/<fname>')
def get_cached_export(etype: str, fname: str) -> Any:
	if etype not in ebook.EXPORT_TYPES:
		# if this is an unsupported export type, 404
		return page_not_found(NotFound())

	suff = ebook.EXPORT_SUFFIXES[etype]
	# if the request is for a specific bundle, try to serve it directly
	if fname.endswith(suff):
		return send_from_directory(os.path.join(ebook.CACHE_DIR, etype), fname)

	# otherwise we probably have a urlId, ensure the export exists/get its name
	fname = try_ensure_export(etype, fname)
	if fname is None:
		# if we failed to generate the export, 404
		return page_not_found(NotFound())
	# redirect back to ourself with the correct bundle filename
	return redirect(url_for('get_cached_export', etype=etype, fname=fname,
		cv=CACHE_BUSTER))


@app.route('/api/v0/epub', methods=['GET'])
def api_v0_epub() -> Any:
	q = request.args.get('q', None)
	if q is None:
		return jsonify(getErr(WebError.no_body))

	eres = ensure_export('epub', q)
	if eres is None:
		return jsonify({'error': -3, 'msg': 'please report this on discord'})
	if 'error' in eres:
		return jsonify(eres)
	for key in ['epub_fname', 'urlId', 'url']:
		if key not in eres:
			return jsonify({'error': -4, 'key': key,
				'msg': f'please report this on discord'})

	info = '[missing metadata; please report this on discord]'
	if 'info' in eres:
		info = eres['info']
	eh = eres['hash'] if 'hash' in eres else str(random.getrandbits(32))

	res = { 'error':0, 'info':info, 'urlId':eres['urlId'], }

	# build auto-generating links for all formats
	for etype in ebook.EXPORT_TYPES:
		res[f'{etype}_url'] = url_for(f'get_cached_export', etype=etype,
				fname=eres['urlId'], cv=CACHE_BUSTER, eh=eh)

	# update epub url to direct download
	res['epub_url'] = eres['url']

	return jsonify(res)

if __name__ == '__main__':
	app.run(debug=True)

