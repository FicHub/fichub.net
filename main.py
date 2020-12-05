import os
import os.path
import hashlib
import time
import traceback
import json
import random
from typing import Any, Dict, Union
from enum import IntEnum
from flask import Flask, Response, jsonify, request, render_template, \
	send_from_directory, redirect, url_for
from werkzeug.exceptions import NotFound
import util
from util import FicInfo, RequestLog
#from oil import oil
#import weaver.enc as enc
#from weaver import Web, WebScraper, WebQueue

#db = oil.open()
app = Flask(__name__, static_url_path='')

import ax
import ebook
import authentications as a

CACHE_BUSTER=7

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

def hashEPUB(fname: str) -> str:
	digest = 'hash_err'
	with open(os.path.join(ebook.EPUB_CACHE_DIR, fname), 'rb') as f:
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
		href = url_for('get_cached_epub', fname=f, cv=CACHE_BUSTER)
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

@app.route('/epub/<fname>')
def get_cached_epub_v0(fname: str) -> Any:
	h = request.args.get('h', str(random.getrandbits(32)))
	return redirect(url_for('get_cached_epub', fname=fname, cv=CACHE_BUSTER, h=h))

@app.route('/cache/epub/<fname>')
def get_cached_epub(fname: str) -> Any:
	return send_from_directory(ebook.EPUB_CACHE_DIR, fname)

def try_ensure_html(urlId: str) -> str:
	initTimeMs = int(time.time() * 1000)
	meta = ax.lookup(urlId)
	if 'error' in meta:
		return None
	infoTimeMs = int(time.time() * 1000)

	try:
		chapters = ax.fetchChapters(meta)

		# try to build html bundle
		html_fname = ebook.createHtmlBundle(meta, chapters)
		html_url = url_for('get_cached_html', fname=html_fname, cv=CACHE_BUSTER)

		endTimeMs = int(time.time() * 1000)

		# TODO we need per filetype request logs
		#util.logRequest(infoTimeMs - initTimeMs, endTimeMs - infoTimeMs, urlId, q,
		#	meta, epub_fname, h, epub_url, isAutomated)

		return html_fname
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('^ something went wrong :/')

	return None

@app.route('/html/<fname>')
def get_cached_html_v0(fname: str) -> Any:
	h = request.args.get('h', str(random.getrandbits(32)))
	return redirect(url_for('get_cached_html', fname=fname, cv=CACHE_BUSTER, h=h))

@app.route('/cache/html/<fname>')
def get_cached_html(fname: str) -> Any:
	# if the request is for a specific bundle, try to serve it directly
	if fname.endswith('.zip'):
		return send_from_directory(ebook.HTML_CACHE_DIR, fname)

	# otherwise we probably have a urlId, ensure the bundle exists/get its name
	fname = try_ensure_html(fname)
	if fname is None:
		# if we failed to generate an html bundle, 404
		return page_not_found(NotFound())
	# redirect back to ourself with the correct bundle filename
	return redirect(url_for('get_cached_html', fname=fname, cv=CACHE_BUSTER))


@app.route('/api/v0/epub', methods=['GET'])
def api_v0_epub() -> Any:
	isAutomated = (request.args.get('automated', None) == 'true')
	q = request.args.get('q', None)
	if q is None:
		return jsonify(getErr(WebError.no_body))

	initTimeMs = int(time.time() * 1000)
	meta = ax.lookup(q)
	if 'error' in meta:
		return jsonify(meta)
	infoTimeMs = int(time.time() * 1000)

	try:
		urlId = meta['urlId']
		ficInfo, ficName = ebook.metaDataString(meta)
		chapters = ax.fetchChapters(meta)

		# build epub
		epub_fname = ebook.createEpub(meta, chapters)
		h = hashEPUB(epub_fname)
		epub_url = url_for('get_cached_epub', fname=epub_fname, cv=CACHE_BUSTER,
				h=h)

		# build auto-generating html bundle link
		html_url = url_for('get_cached_html', fname=urlId, cv=CACHE_BUSTER)

		endTimeMs = int(time.time() * 1000)
		util.logRequest(infoTimeMs - initTimeMs, endTimeMs - infoTimeMs, \
				urlId, q, meta, epub_fname, h, epub_url, isAutomated)

		return jsonify({
				'error':0, 'info':ficInfo, 'urlId':urlId,
				'url':epub_url,
				'zurl':html_url,
			})
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('^ something went wrong :/')
		return jsonify({'error':-9,'msg':'exception encountered while building epub'})

if __name__ == '__main__':
	app.run(debug=True)

