from typing import Any, cast
import hashlib

import requests

import fichub_net.authentications as a


def hash_file(fname: str) -> str:
    with open(fname, "rb") as f:
        data = f.read()
        return hashlib.md5(data).hexdigest()


def req_json(link: str, retry_count: int = 5, timeout: float = 300.0) -> dict[Any, Any]:
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
        if retry_count < 1:
            return {
                "err": -1,
                "msg": f"req_json: received status code: {r.status_code!s}",
            }
        return req_json(link, retry_count - 1)
    return cast(dict[Any, Any], p)
