from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


def _digest(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


class HtmlCache:
    def __init__(self, dir_path: Path, ttl_seconds: float):
        self.dir = dir_path
        self.ttl = ttl_seconds
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / f"{_digest(key)}.html"

    def get(self, key: str) -> Optional[str]:
        p = self._path(key)
        if not p.exists():
            return None
        if (time.time() - p.stat().st_mtime) > self.ttl:
            return None
        return p.read_text(encoding="utf-8", errors="replace")

    def put(self, key: str, content: str) -> None:
        self._path(key).write_text(content, encoding="utf-8")


class JsonCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
            except Exception:
                self._data = {}

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))
