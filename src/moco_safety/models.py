from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional

Status = Literal["ok", "degraded", "error"]


@dataclass
class FetchResult:
    source: str
    status: Status
    note: str = ""
    records: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Incident:
    id: str
    source: str
    category: str
    subcategory: str
    description: str
    occurred_at: Optional[str]  # ISO8601 UTC
    reported_at: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    address: str
    zip_code: str
    raw_url: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StationSummary:
    station: str
    date: str
    ems_count: int
    fire_count: int

    def to_dict(self) -> dict:
        return asdict(self)
