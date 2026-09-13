"""One FinMind request loop for every collector in this package.

Eight files used to carry their own loop, each with its own answer to a 402, and
``download.py`` duplicated the token read because it ran as a script and could
not import ``auth``. This is the one loop, and a collector does none of the
following itself.

**It paces to the account's quota.** The quota is a fixed hourly window. Its
size is read from ``user_info`` at the first request rather than typed in: the
register tier allows 600 an hour and the sponsor tier 6,000, and a pace written
for one is ten times wrong for the other. Requests are spaced at
``3600 / (0.9 * limit)`` seconds by a lock shared across threads, so any number
of workers together stay inside the window. Backoff with jitter is the wrong
tool for this: a fixed window does not care how retries are spaced, only how
many requests land inside it.

**It answers a 402 by sleeping to the top of the hour.** That is when the window
resets. Nothing shorter helps and nothing longer is needed. A second 402 in one
call raises, because another process is spending the same quota.

**It refuses what the vendor refuses.** A body carrying ``status != 200``, or a
400 whose message asks for a higher tier, raises ``VendorRefused`` rather than
returning an empty frame. Returned empty, it would be written as a stock that
had no rows, which is the silent failure this package has paid for once.

**It retries the network, not the answer.** A connection error or a 5xx is
retried with a widening sleep. A 200 is final.

The token travels in the ``Authorization`` header (``auth.headers``), never in
the query string that ``requests`` writes into its error messages.
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import requests

from .auth import headers

API = "https://api.finmindtrade.com/api/v4/data"
USER_INFO = "https://api.web.finmindtrade.com/v2/user_info"

# The share of the hourly window the pacer spends. A steady 90 % never trips the
# window; the round trip is what the other 10 % absorbs.
_HEADROOM = 0.9
_NET_RETRIES = 8
_RATE_LIMIT_WAITS = 2


class VendorRefused(RuntimeError):
    """The vendor answered, and the answer was no: a tier gate, an unknown
    dataset, or a body whose own status is not 200. Not retried."""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def quota() -> int:
    """Requests per hour the account may make, as the vendor reports it."""
    r = requests.get(USER_INFO, headers=headers(), timeout=60)
    r.raise_for_status()
    limit = int(r.json().get("api_request_limit_hour") or 0)
    if limit <= 0:
        raise RuntimeError(f"user_info reports no hourly limit: {r.json()}")
    return limit


class _Pacer:
    """Hands out send times `interval` apart, across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next = 0.0
        self._interval: float | None = None

    def wait(self) -> None:
        with self._lock:
            if self._interval is None:
                limit = quota()
                self._interval = 3600.0 / (_HEADROOM * limit)
                log(f"quota {limit}/hour; pacing one request per {self._interval:.2f}s")
            slot = max(time.monotonic(), self._next)
            self._next = slot + self._interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


_pacer = _Pacer()


def get(dataset: str, *, data_id: str | None = None, start: str | None = None,
        end: str | None = None, timeout: int = 180) -> pd.DataFrame:
    """One answer from `/data`, as a frame; empty where the vendor had no rows.

    Without `data_id` the endpoint answers for every stock on `start` (all but
    the capital-reduction table ignore `end`); with it, for one stock over the
    span. Which of the two a dataset supports is the vendor's to say and
    `catalogue.py` holds its word on it.
    """
    params = {"dataset": dataset}
    if data_id is not None:
        params["data_id"] = data_id
    if start is not None:
        params["start_date"] = start
    if end is not None:
        params["end_date"] = end
    what = " ".join(f"{k}={v}" for k, v in params.items())
    backoff = 30.0
    waits = 0
    for _ in range(_NET_RETRIES):
        _pacer.wait()
        try:
            r = requests.get(API, params=params, headers=headers(), timeout=timeout)
        except requests.RequestException as e:
            log(f"  net-err {what}: {e}; sleep {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 1.8, 600)
            continue
        if r.status_code in (402, 429):
            waits += 1
            if waits > _RATE_LIMIT_WAITS:
                raise VendorRefused(f"{what}: rate-limited {waits} times in one call; "
                                    f"another process is spending this quota")
            sleep_s = 3600 - (time.time() % 3600) + 60
            log(f"  rate-limit {what} (HTTP {r.status_code}); sleep {sleep_s:.0f}s to the reset")
            time.sleep(sleep_s)
            continue
        if r.status_code == 200:
            payload = r.json()
            if payload.get("status") == 200:
                return pd.DataFrame(payload.get("data") or [])
            raise VendorRefused(f"{what}: {payload.get('msg')}")
        if r.status_code in (400, 422):
            try:
                msg = r.json().get("msg", r.text[:200])
            except ValueError:
                msg = r.text[:200]
            raise VendorRefused(f"{what}: HTTP {r.status_code} {msg}")
        log(f"  http-{r.status_code} {what}: {r.text[:100]}; sleep {backoff:.0f}s")
        time.sleep(backoff)
        backoff = min(backoff * 1.8, 600)
    raise ConnectionError(f"{what}: no answer after {_NET_RETRIES} attempts")
