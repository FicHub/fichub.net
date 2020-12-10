function q() {
	let qe = (<HTMLInputElement>document.getElementById('q'));
	if(!qe) return '';
	return qe.value;
}
function info() {
	return document.getElementById('info');
}
function working() {
	info().innerHTML = '<p>working...</p>';
}
function error(r) {
	console.log('uh-oh');
	let msg = 'an error ocurred :(';
	if (q().indexOf('tvtropes.org') >= 0) {
		msg += '<br/>(note that tvtropes.org is not directly supported; instead, use the url of the actual fic)';
	}
	if (q().indexOf('http://') != 0 && q().indexOf('https://') != 0) {
		msg += '<br/>(please try a full url including http:// or https:// at the start)';
	}
	info().innerHTML = '<p>' + msg + '</p>' +
		'<pre>' + r.responseText + '</pre>';
}
function epub() {
	console.log('epub');
	working();
	var exportReq = new XMLHttpRequest();
	exportReq.addEventListener("load", function () {
		try {
			var res = JSON.parse(this.responseText);
			if (!res || res.error != 0) {
				return error(this);
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
			return error("response was not valid :/");
		}
	});
	var data = null;
	exportReq.open('GET', '/api/v0/epub?q=' + q());
	exportReq.send(data);
}

window['epub'] = epub;

window.onload = setup;
function setup() {
	console.log('setup');
	console.log(q());
	if(q()) { epub(); }
}

