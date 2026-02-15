"""Cantonese language service backed by OpenAI Responses API."""

from __future__ import annotations

from pathlib import Path

from services.cantonese_cache import CantoneseCache
from services.cantonese_client import CantoneseClient
from services.cantonese_models import CantoneseInfo


class CantoneseLanguageService:
    """Fetch Cantonese metadata with a local JSON cache."""

    def __init__(self, *, cache_path: Path, model: str = "gpt-4o-mini"):
        self._model = str(model or "gpt-4o-mini")
        self._cache = CantoneseCache(cache_path=cache_path)
        self._client = CantoneseClient(model=self._model)

    def get_cached(self, *, hanzi: str = "", jyutping: str = "") -> CantoneseInfo | None:
        """Return cached entry if it has a non-empty meaning."""
        return self._cache.get_cached_info(hanzi=hanzi, jyutping=jyutping)

    def lookup(self, *, hanzi: str = "", jyutping: str = "") -> CantoneseInfo | None:
        logger = None
        try:
            import logging
            logger = logging.getLogger("category_manager")
        except Exception:
            logger = None

        hz = str(hanzi or "").strip()
        jy = " ".join(str(jyutping or "").strip().split())
        if not hz and not jy:
            return None

        key = self._cache.norm_key(hanzi=hz, jyutping=jy)
        cached = self._cache.get_entry(key)
        if isinstance(cached, dict):
            meaning_cached = CantoneseCache.meaning_from_dict(cached)
            if meaning_cached:
                if logger is not None:
                    logger.debug("CANTO: cache hit key=%r meaning=%r", key, meaning_cached)
                info = CantoneseCache.info_from_dict(cached, meaning=meaning_cached)
                if info is not None:
                    return info
            else:
                if logger is not None:
                    logger.debug("CANTO: cache miss (empty meaning) key=%r", key)

        info = self._client.lookup(hanzi=hz, jyutping=jy, logger=logger)
        if info is None:
            return None

        if logger is not None:
            try:
                logger.debug(
                    "CANTO: parsed hanzi=%r jyutping=%r meaning=%r register=%r conf=%r",
                    info.hanzi,
                    info.jyutping,
                    info.meaning_colloquial,
                    info.register,
                    info.confidence,
                )
            except Exception:
                pass

        self._cache.set_entry(key, info)
        return info


__all__ = ["CantoneseInfo", "CantoneseLanguageService"]
