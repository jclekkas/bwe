from __future__ import annotations

import time
from typing import Optional

import requests


# Pose as a mainstream browser; some open-data fronts reject obvious bot UAs.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


class RateLimiter:
    def __init__(self, min_interval_seconds: float):
        self.min_interval = min_interval_seconds
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()


def get(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 20.0,
    retries: int = 3,
    backoff: float = 1.5,
    limiter: Optional[RateLimiter] = None,
) -> requests.Response:
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }
    if headers:
        h.update(headers)
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        if limiter is not None:
            limiter.wait()
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"{r.status_code} at {url}")
            return r
        except Exception as e:
            last_exc = e
            time.sleep(backoff ** attempt)
    assert last_exc is not None
    raise last_exc
