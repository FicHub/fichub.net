window.onload = setup;
function setup() {
	console.log('setup');
}
function q() {
	return document.getElementById('q').value;
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
		var res = JSON.parse(this.responseText);
		if (!res || res.error != 0) {
			return error(this);
		}
		info().innerHTML = '<p><a href="' + res.url + '">Download</a></p>' +
			'<p>' + res.info.replace('\n', '<br/>') + '</p>';
	});
	var data = null;
	exportReq.open('GET', '/api/v0/epub?q=' + q());
	exportReq.send(data);
}

