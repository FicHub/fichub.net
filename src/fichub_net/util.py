from typing import Any, Dict, cast
import hashlib

import requests

import fichub_net.authentications as a


def hashFile(fname: str) -> str:
    with open(fname, "rb") as f:
        data = f.read()
        return hashlib.md5(data).hexdigest()


def reqJson(link: str, retryCount: int = 5, timeout: float = 300.0) -> Dict[Any, Any]:
    params = {"apiKey": a.AX_API_KEY}
    headers = {"User-Agent": "fichub.net/0.1.0"}
    r = requests.get(
        link,
        headers=headers,
        timeout=timeout,
        params=params,
        auth=(a.AX_USER, a.AX_PASS),
    )
    try:
        p = r.json()
    except ValueError:
        if retryCount < 1:
            return {
                "err": -1,
                "msg": f"reqJson: received status code: {r.status_code!s}",
            }
        return reqJson(link, retryCount - 1)
    return cast(Dict[Any, Any], p)
