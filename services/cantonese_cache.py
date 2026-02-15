from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.cantonese_models import CantoneseInfo


class CantoneseCache:
    def __init__(self, *, cache_path: Path):
        self._cache_path = cache_path
        self._cache: dict[str, dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        try:
            if self._cache_path.exists():
                raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._cache = raw
        except Exception:
            self._cache = {}

    def _save_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def norm_key(*, hanzi: str = "", jyutping: str = "") -> str:
        hz = str(hanzi or "").strip()
        if hz:
            return "hz:" + hz
        jy = " ".join(str(jyutping or "").strip().split())
        return "jy:" + jy

    @staticmethod
    def meaning_from_dict(cached: dict[str, Any] | None) -> str:
        if not isinstance(cached, dict):
            return ""
        try:
            return str(cached.get("meaning_colloquial", "") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def info_from_dict(
        cached: dict[str, Any] | None,
        *,
        meaning: str | None = None,
    ) -> CantoneseInfo | None:
        if not isinstance(cached, dict):
            return None
        if meaning is None:
            meaning = CantoneseCache.meaning_from_dict(cached)
        if not meaning:
            return None
        try:
            return CantoneseInfo(
                hanzi=str(cached.get("hanzi", "") or ""),
                jyutping=str(cached.get("jyutping", "") or ""),
                meaning_colloquial=meaning,
                register=str(cached.get("register", "") or ""),
                confidence=float(cached.get("confidence", 0.0) or 0.0),
                notes=str(cached.get("notes", "") or "") or None,
                examples=list(cached.get("examples", []) or []),
                model=str(cached.get("model", "") or "") or None,
                ts=float(cached.get("ts", 0.0) or 0.0),
            )
        except Exception:
            return None

    def get_cached_info(self, *, hanzi: str = "", jyutping: str = "") -> CantoneseInfo | None:
        hz = str(hanzi or "").strip()
        jy = " ".join(str(jyutping or "").strip().split())
        if not hz and not jy:
            return None

        key = self.norm_key(hanzi=hz, jyutping=jy)
        cached = self._cache.get(key)
        return self.info_from_dict(cached)

    def get_entry(self, key: str) -> dict[str, Any] | None:
        cached = self._cache.get(key)
        return cached if isinstance(cached, dict) else None

    def set_entry(self, key: str, info: CantoneseInfo) -> None:
        self._cache[key] = info.to_dict()
        self._save_cache()
