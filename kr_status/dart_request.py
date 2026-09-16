"""One GET against a DART endpoint, with the API key kept out of the error text.

DART authenticates by the ``crtfc_key`` query parameter, and `requests` quotes
the whole URL in every exception it raises — a dropped connection, a timeout, a
non-200 status. The key therefore reached every log that recorded a failed
crawl, and every screen that printed one.
"""
from __future__ import annotations

import requests


def dart_get(url: str, params: dict, timeout: int = 30) -> requests.Response:
    """GET `url` with `params`, raising on a network failure or an error status.

    The raised message is the one `requests` wrote with the key replaced, and it
    is raised `from None` so the chained original — which quotes the URL again —
    does not reach the traceback either.
    """
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        key = str(params.get("crtfc_key") or "")
        msg = str(e).replace(key, "<redacted>") if key else str(e)
        raise RuntimeError(f"{type(e).__name__}: {msg}") from None
    return r
