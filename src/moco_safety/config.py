from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"


@dataclass
class Settings:
    raw: dict[str, Any]

    @property
    def zip(self) -> str:
        return str(self.raw["zip"])

    @property
    def center(self) -> tuple[float, float]:
        c = self.raw["center"]
        return float(c["lat"]), float(c["lon"])

    @property
    def bbox(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw["bbox"].items()}

    @property
    def digest_hours(self) -> int:
        return int(self.raw["windows"]["digest_hours"])

    @property
    def ui_days(self) -> int:
        return int(self.raw["windows"]["ui_days"])

    @property
    def history_days(self) -> int:
        return int(self.raw["windows"].get("history_days", 30))

    def source(self, name: str) -> dict[str, Any]:
        return self.raw["sources"][name]

    @property
    def digest(self) -> dict[str, Any]:
        return self.raw["digest"]


def load_settings(path: Path | None = None) -> Settings:
    path = path or (CONFIG_DIR / "settings.yaml")
    with path.open() as f:
        return Settings(raw=yaml.safe_load(f))


def load_categories(path: Path | None = None) -> dict[str, str]:
    path = path or (CONFIG_DIR / "categories.yaml")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    mapping: dict[str, str] = {}
    for group, names in (data.get("groups") or {}).items():
        for name in names or []:
            mapping[name.lower()] = group
    return mapping


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v else default


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"required env var {name} is not set")
    return v
