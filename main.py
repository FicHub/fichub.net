import os
import os.path
import hashlib
import time
import traceback
from typing import Any, Dict, Union
from enum import IntEnum
from flask import Flask, Response, jsonify, request, render_template, \
	send_from_directory, redirect, url_for
import util
from util import FicInfo
#from oil import oil
#import weaver.enc as enc
#from weaver import Web, WebScraper, WebQueue

#db = oil.open()
app = Flask(__name__, static_url_path='')

import epubCreator as ec
import authentications as a

CACHE_BUSTER=3

class WebError(IntEnum):
	success = 0
	no_body = -1

errorMessages = {
		WebError.success: 'success',
		WebError.no_body: 'no body',
	}

def getErr(err: WebError) -> Dict[str, Any]:
	return {'error':int(err),'msg':errorMessages[err]}

@app.route('/')
def index() -> str:
	return render_template('index.html', CACHE_BUSTER=CACHE_BUSTER)

def hashEPUB(fname: str) -> str:
	digest = 'hash_err'
	with open(os.path.join(ec.CACHE_DIR, fname), 'rb') as f:
		data = f.read()
		digest = hashlib.md5(data).hexdigest()
	return digest

@app.route('/cache/')
def cache_listing() -> str:
	fis = {fi.id: fi for fi in FicInfo.select()}
	items = []
	for f in os.listdir(ec.CACHE_DIR):
		if len(str(f).strip()) < 1:
			continue
		href = url_for('epub', fname=f, cv=CACHE_BUSTER)
		urlId = f.split('-')[-1]
		if not urlId.endswith('.epub'):
			continue
		urlId = urlId[:-len('.epub')]
		fi = fis[urlId] if urlId in fis else None
		items.append({'href':href, 'fname':f, 'ficInfo':fi})
	return render_template('cache.html', cache=items, CACHE_BUSTER=CACHE_BUSTER)

@app.route('/epub/<fname>')
def epub(fname: str) -> Any:
	return send_from_directory(ec.CACHE_DIR, fname)

@app.route('/api/v0/epub', methods=['GET'])
def epub_fic() -> Any:
	q = request.args.get('q', None)
	if q is None:
		return jsonify(getErr(WebError.no_body))

	initTimeMs = int(time.time() * 1000)
	p = ec.reqJson('/'.join([a.AX_LOOKUP_ENDPOINT, q]))
	if 'error' in p:
		return jsonify(p)
	infoTimeMs = int(time.time() * 1000)
	ficInfo = ec.metaDataString(p)[0]

	try:
		fic = p['urlId']
		ficInfo, ficName = ec.metaDataString(p)
		epub_fname = ec.createEpub('/'.join([a.AX_FIC_ENDPOINT, fic, '']))
		h = 'hash_err'
		try:
			h = hashEPUB(epub_fname)
		except Exception as e:
			traceback.print_exc()
			print(e)
			print('^ something went wrong hashing :/')
		url = url_for('epub', fname=epub_fname, cv=CACHE_BUSTER, h=h)
		endTimeMs = int(time.time() * 1000)
		util.logRequest(infoTimeMs - initTimeMs, endTimeMs - infoTimeMs, \
				p['urlId'], q, p, epub_fname, h, url)
		return jsonify({'error':0,'url':url,'info':ficInfo})
	except Exception as e:
		traceback.print_exc()
		print(e)
		print('^ something went wrong :/')
		return jsonify({'error':-9,'msg':'exception encountered while building epub'})

if __name__ == '__main__':
	app.run(debug=True)

