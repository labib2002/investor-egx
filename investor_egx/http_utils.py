from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_retrying_session(
    user_agent: str,
    max_retries: int = 4,
    backoff_factor: float = 0.8,
) -> Session:
    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@dataclass
class RateLimiter:
    min_interval_sec: float
    jitter_max_sec: float = 0.15

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._last_call_ts = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_ts
            sleep_for = self.min_interval_sec - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
            if self.jitter_max_sec > 0:
                time.sleep(random.random() * self.jitter_max_sec)
            self._last_call_ts = time.monotonic()


def safe_get_json(
    session: Session,
    url: str,
    timeout_sec: int,
    limiter: RateLimiter | None = None,
) -> dict:
    if limiter:
        limiter.wait()
    response: Response = session.get(url, timeout=timeout_sec)
    response.raise_for_status()
    return response.json()
