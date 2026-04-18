from __future__ import annotations

import time
from typing import Optional

import requests


USER_AGENT = (
    "moco-safety/0.1 (+https://github.com/) "
    "personal neighborhood safety digest"
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
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
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
