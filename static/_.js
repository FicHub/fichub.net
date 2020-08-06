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
function lookup() {
	console.log('lookup');
	working();
	var lookupReq = new XMLHttpRequest();
	lookupReq.addEventListener("load", function () {
		var res = JSON.parse(this.responseText);
		if (!res || res.err != 0) {
			console.log('uh-oh');
			info().innerHTML = '<p>an error ocurred :(</p>' +
				'<p>' + this.responseText + '</p>';
			return;
		}
		info().innerHTML = '<p>' + res.info + '</p>';
	});
	var data = null;
	lookupReq.open('GET', '/api/v0/lookup?q=' + q());
	lookupReq.send(data);
}
function epub() {
	console.log('epub');
	working();
	var lookupReq = new XMLHttpRequest();
	lookupReq.addEventListener("load", function () {
		var res = JSON.parse(this.responseText);
		if (!res || res.err != 0) {
			console.log('uh-oh');
			info().innerHTML = '<p>an error ocurred :(</p>' +
				'<p>' + this.responseText + '</p>';
			return;
		}
		info().innerHTML = '<p><a href="' + res.url + '">Download</a></p>' +
			'<p>' + res.info + '</p>';
	});
	var data = null;
	lookupReq.open('GET', '/api/v0/epub?q=' + q());
	lookupReq.send(data);
}
