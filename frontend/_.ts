function f() {
	return <HTMLFormElement>document.getElementById('f');
}
function x() {
	return <HTMLButtonElement>document.getElementById('x');
}
function q() {
	let qe = (<HTMLInputElement>document.getElementById('q'));
	if(!qe) return '';
	return qe.value;
}
function info() {
	return document.getElementById('i');
}
function working() {
	info().innerHTML = '<p class=w>Working <img class=l src="/img/loading.gif"></p>';
}
function contentEncode(str) {
	var p = document.createElement("p");
	p.textContent = str;
	return p.innerHTML;
}
function repeat(str, cnt) {
	let res = '';
	for (let i = 0; i < cnt; ++i)
		res += str;
	return res;
}
function buildCodeBlockContent(str) {
	str = contentEncode(str);
	let lines = str.split('\n');
	let ret = '';
	for (let i = 0; i < lines.length; ++i) {
		let spaceCount = lines[i].search(/[^ ]/);
		ret += repeat('&nbsp;', spaceCount) + lines[i].substr(spaceCount) + '<br/>';
	}
	return ret;
}
function error(msg, r, obj) {
	console.log('uh-oh');
	if (obj && obj.fixits && obj.fixits.length > 0) {
		for (let i = 0; i < obj.fixits.length; ++i) {
			msg += '<br/>' + obj.fixits[i];
		}
		obj.fixits = undefined;
	}
	msg = '<p>' + msg + '</p>';

	if (obj) {
		if ('msg' in obj) {
			msg += '<p><code>msg: ' + buildCodeBlockContent(obj.msg) + '\n</code></p>';
		}
		msg += '<p><code>' + buildCodeBlockContent(JSON.stringify(obj, null, 2)) + '</code></p>';
	} else if (r) {
		msg += '<p><code>' + buildCodeBlockContent(r.responseText) + '</code></p>';
	}

	info().innerHTML = msg;
}

function extractUrls(res) {
	let urls = {};
	if (res.epub_url && res.epub_url.length)
		urls['epub'] = res.epub_url;
	if (res.html_url && res.html_url.length)
		urls['html'] = res.html_url;
	if (res.mobi_url && res.mobi_url.length)
		urls['mobi'] = res.mobi_url;
	if (res.pdf_url && res.pdf_url.length)
		urls['pdf'] = res.pdf_url;

	if (!res.urls)
		return urls;

	let types = ['epub', 'html', 'mobi', 'pdf'];
	for (let i = 0; i < types.length; ++i) {
		if (res.urls[types[i]]) {
			urls[types[i]] = res.urls[types[i]];
		}
	}
	return urls;
}

function explodeNewlines(str) {
	while(str.indexOf('\n') >= 0) {
		str = str.replace('\n', '<br/>');
	}
	return str;
}

function epub() {
	if(x().disabled)
		return;
	x().disabled = true;
	console.log('epub');
	working();
	var exportReq = new XMLHttpRequest();
	exportReq.addEventListener("load", function () {
		try {
			var res = JSON.parse(this.responseText);
			if (!res
					|| ('error' in res && res.error != 0)
					|| ('err' in res && res.err != 0)) {
				x().disabled = false;
				return error('an error ocurred :(', this, res);
			}
			let urls = extractUrls(res);
			let htmlRes = '<p>' + explodeNewlines(res.info) + '</p>' +
				'<p><a href="' + urls['epub'] + '">Download as EPUB</a></p>';
			if ('html' in urls) {
				htmlRes += '<p><a href="' + urls['html'] + '">Download as zipped HTML</a></p>';
			}
			if ('mobi' in urls) {
				htmlRes += '<p><a href="' + urls['mobi'] + '">Download as MOBI (may take time to start)</a></p>';
			}
			if ('pdf' in urls) {
				htmlRes += '<p><a href="' + urls['pdf'] + '">Download as PDF (may take time to start)</a></p>';
			}
			if (res.urlId && res.urlId.length) {
				htmlRes += '<p><a href="/fic/' + res.urlId + '">Re-export Link</a></p>'
			}
			info().innerHTML = htmlRes;
		} catch (e) {
			x().disabled = false;
			return error("response was not valid :/", this, null);
		}
		x().disabled = false;
	});
	var data = null;
	exportReq.open('GET', '/api/v0/epub?q=' + encodeURIComponent(q()));
	exportReq.send(data);
}

window['epub'] = epub;

window.onload = setup;
function setup() {
	if(navigator.userAgent.indexOf('ooglebot') >= 0) { return; }
	if(navigator.userAgent.indexOf('BingPreview') >= 0) { return; }
	if(f()) {
		f().action = 'javascript:void(0);';
	}
	if(q()) { epub(); }
}

