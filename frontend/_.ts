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
	if (q().indexOf('tvtropes.org') >= 0) {
		msg += '<br/>(note that tvtropes.org is not directly supported; instead, use the url of the actual fic)';
	}
	if (q().indexOf('http://') != 0 && q().indexOf('https://') != 0) {
		msg += '<br/>(please try a full url including http:// or https:// at the start)';
	}
	if (q().indexOf('fanfiction.net') >= 0) {
		msg += '<br/>fanfiction.net is fragile at the moment; please try again later or check the discord';
	}
	if (q().indexOf('fanfiction.net/u/') >= 0) {
		msg += '<br/>user pages on fanfiction.net are not currently supported -- please try a specific story';
	}
	if (q().indexOf('fictionpress.com') >= 0) {
		msg += '<br/>fictionpress.com is fragile at the moment; please try again later or check the discord';
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
			let htmlRes = '<p><a href="' + res.epub_url + '">Download EPUB</a></p>' +
				'<p>' + res.info.replace('\n', '<br/>') + '</p>';
			if (res.html_url) {
				htmlRes += '<p><a href="' + res.html_url + '">Download as zipped HTML</a></p>';
			}
			if (res.mobi_url) {
				htmlRes += '<p><a href="' + res.mobi_url + '">Download as MOBI (may take time to start)</a></p>';
			}
			if (res.pdf_url) {
				htmlRes += '<p><a href="' + res.pdf_url + '">Download as PDF (may take time to start)</a></p>';
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
	console.log(q());
	if(q()) { epub(); }
}

