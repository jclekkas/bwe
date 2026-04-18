from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..config import Settings
from ..models import FetchResult


class Fetcher(Protocol):
    name: str

    def fetch(self, settings: Settings, since: datetime) -> FetchResult: ...
