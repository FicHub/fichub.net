from typing import Dict, Any, cast
import hashlib
import requests
import authentications as a

def hashFile(fname: str) -> str:
	digest = 'hash_err'
	with open(fname, 'rb') as f:
		data = f.read()
		digest = hashlib.md5(data).hexdigest()
	return digest

def reqJson(link: str, retryCount: int = 5, timeout: float = 300.0) -> Dict[Any, Any]:
	params = {'apiKey': a.AX_API_KEY}
	headers = {'User-Agent': 'fichub.net/0.1.0'}
	r = requests.get(link, headers=headers, timeout=timeout,
			params=params, auth=(a.AX_USER, a.AX_PASS))
	try:
		p = r.json()
	except ValueError:
		if retryCount < 1:
			return {
					'err': -1,
					'msg': f"reqJson: received status code: {str(r.status_code)}"
				}
		else:
			return reqJson(link, retryCount - 1)
	return cast(Dict[Any, Any], p)

