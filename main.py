import os
import os.path
import time
from typing import Any, Dict, Union
from enum import IntEnum
from flask import Flask, Response, jsonify, request, render_template, \
	send_from_directory, redirect, url_for
#from oil import oil
#import weaver.enc as enc
#from weaver import Web, WebScraper, WebQueue

#db = oil.open()
app = Flask(__name__, static_url_path='')

import epubCreator as ec
import authentications as a

class WebError(IntEnum):
	success = 0
	no_body = -1
	no_json_body = -2

	url_not_found = -3
	url_null = -4
	unknown_encoding = -5
	invalid_url = -6

errorMessages = {
		WebError.success: 'success',
		WebError.no_body: 'no body',
		WebError.no_json_body: 'no json body',
		WebError.url_not_found: 'not found',
		WebError.url_null: 'url null',
		WebError.unknown_encoding: 'unknown encoding',
		WebError.invalid_url: 'invalid url',
	}

def getErr(err: WebError) -> Dict[str, Any]:
	return {'error':int(err),'msg':errorMessages[err]}

@app.route('/')
def index() -> str:
	return render_template('index.html')

@app.route('/cache/')
def cache_listing() -> str:
	items = []
	for f in os.listdir(ec.CACHE_DIR):
		items.append({'href':url_for('epub', fname=f), 'fname':f})
	return render_template('cache.html', cache=items)

@app.route('/api/v0/lookup', methods=['GET'])
def lookup_fic() -> Any:
	q = request.args.get('q', None)
	if q is None:
		return jsonify(getErr(WebError.no_body))
	p = ec.reqJson('/'.join([a.AX_LOOKUP_ENDPOINT, q]))
	if 'error' in p:
		return jsonify(p)
		return jsonify(getErr(WebError.url_not_found))
	ficInfo = ec.metaDataString(p)[0]
	return jsonify({'error':0,'info':ficInfo})

@app.route('/epub/<fname>')
def epub(fname: str) -> Any:
	return send_from_directory(ec.CACHE_DIR, fname)

@app.route('/api/v0/epub', methods=['GET'])
def epub_fic() -> Any:
	q = request.args.get('q', None)
	if q is None:
		return jsonify(getErr(WebError.no_body))

	p = ec.reqJson('/'.join([a.AX_LOOKUP_ENDPOINT, q]))
	if 'error' in p:
		return jsonify(p)
	ficInfo = ec.metaDataString(p)[0]

	fic = p['urlId']
	ficInfo, ficName = ec.metaDataString(p)
	epub_fname = ec.createEpub('/'.join([a.AX_FIC_ENDPOINT, fic, '']))
	return jsonify({'error':0,'url':url_for('epub', fname=epub_fname),'info':ficInfo})

if __name__ == '__main__':
	app.run(debug=True)

