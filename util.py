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

def reqJson(link: str, retryCount: int = 5) -> Dict[Any, Any]:
	cookies = {'session': a.SESSION}
	r = requests.get(link, cookies = cookies)
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

