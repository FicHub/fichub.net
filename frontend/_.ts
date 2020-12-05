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
	info().innerHTML = '<p>an error ocurred :(</p>' +
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

