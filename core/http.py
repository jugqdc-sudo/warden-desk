"""Minimal HTTP client. Standard library only, no API keys anywhere.

Every public endpoint this desk touches is read-only and unauthenticated.
A proxy can be supplied through the usual HTTPS_PROXY / HTTP_PROXY variables
(or DESK_PROXY, which wins over both); with none set, requests go out direct.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "warden-desk/1.0 (+https://github.com/ventry089/warden-desk)"
TIMEOUT = 20


def _proxy() -> str | None:
    """Proxy URL to use, or None for a direct connection."""
    return (
        os.environ.get("DESK_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or None
    )


def _opener() -> urllib.request.OpenerDirector:
    proxy = _proxy()
    handlers: list[urllib.request.BaseHandler] = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    retries: int = 3,
    timeout: int = TIMEOUT,
) -> Any | None:
    """GET a JSON document, retrying on transient failures.

    Returns the decoded document, or None when every attempt failed. A None
    here means "the endpoint did not answer", never "the answer was empty" -
    callers must not confuse the two.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    opener = _opener()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(retries):
        try:
            with opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # 4xx other than 429 will not fix itself on retry.
            if exc.code not in (429, 500, 502, 503, 504):
                return None
        except Exception:
            pass
        if attempt + 1 < retries:
            time.sleep(1.5 * (attempt + 1))
    return None
