"""category_repo.py

Domain repository for category membership.

Responsibilities:
  - Own the authoritative in-memory categories mapping (cat -> [hanzi...])
  - Apply canonicalisation of category names (optional)
  - Provide a small API used by CategoryCommitService / CategoryManagerDialog
  - Persist categories via an injected callback (preferred) or via
    services.vocab_loader.persist_categories_block (best-effort)

This module must not import any UI / Qt code.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    # Single source of truth for persistence (vocab.yaml categories block).
    from services.vocab_loader import persist_categories_block as _persist_categories_block
except Exception:  # pragma: no cover
    _persist_categories_block = None  # type: ignore[assignment]


CatsMap = Dict[str, List[str]]
CanonFn = Callable[[str], str]
PersistFn = Callable[[Dict[str, Any]], None]


class CategoryRepo:
    """Small, defensive repository for categories."""

    def __init__(
            self,
            cats: Optional[Dict[str, Any]] = None,
            *,
            canon: Optional[CanonFn] = None,
            persist: Optional[PersistFn] = None,
    ) -> None:
        # Keep the caller-provided mapping as the backing store when possible.
        self._cats: Dict[str, Any]
        if isinstance(cats, dict):
            self._cats = cats
        else:
            self._cats = {}

        self._canon = canon if callable(canon) else None
        self._persist_cb = persist if callable(persist) else None

    # ------------------------------------------------------------------
    # Canonicalisation
    # ------------------------------------------------------------------
    def canon(self, name: str) -> str:
        try:
            raw = str(name or "").strip()
        except Exception:
            raw = ""
        if not raw:
            return ""

        if self._canon is not None:
            try:
                out = str(self._canon(raw) or "").strip()
            except Exception:
                out = ""
            return out or raw

        return raw

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def exists(self, name: str) -> bool:
        key = self.canon(name)
        if not key:
            return False
        try:
            return key in self._cats
        except Exception:
            return False

    def get_map(self) -> Dict[str, Any]:
        """Return the authoritative backing mapping (best-effort)."""
        return self._cats

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------
    def ensure_category(self, name: str) -> bool:
        """Ensure a category key exists.

        Returns True if the key was added, False if it already existed or was invalid.
        """
        key = self.canon(name)
        if not key:
            return False

        try:
            if key in self._cats:
                # Normalise shape defensively.
                node = self._cats.get(key)
                if node is None:
                    self._cats[key] = []
                return False

            self._cats[key] = []
            self._persist_best_effort()
            return True
        except Exception:
            return False

    def add(self, name: str) -> bool:
        """Compatibility alias for CategoryCommitService."""
        return self.ensure_category(name)

    def add_hanzi(self, category: str, hanzi: str) -> None:
        key = self.canon(category)
        try:
            hz = str(hanzi or "").strip()
        except Exception:
            hz = ""
        if not key or not hz:
            return

        try:
            node = self._cats.get(key)
            if not isinstance(node, list):
                # If the node is not a list (richer structure), do not mutate it.
                return
            if hz not in node:
                node.append(hz)
                self._persist_best_effort()
        except Exception:
            return

    def remove_hanzi(self, category: str, hanzi: str) -> None:
        key = self.canon(category)
        try:
            hz = str(hanzi or "").strip()
        except Exception:
            hz = ""
        if not key or not hz:
            return

        try:
            node = self._cats.get(key)
            if not isinstance(node, list):
                return
            if hz in node:
                node[:] = [x for x in node if x != hz]
                self._persist_best_effort()
        except Exception:
            return

    def sync_to(self, other: Dict[str, Any]) -> None:
        """Best-effort: copy current mapping into `other` without changing identity."""
        if not isinstance(other, dict):
            return
        try:
            other.clear()
            other.update(self._cats)
        except Exception:
            return

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist_best_effort(self) -> None:
        """Persist categories.

        Priority:
          1) injected persist callback (tests/UI can provide)
          2) services.vocab_loader.persist_categories_block

        Must never raise.
        """
        try:
            if callable(self._persist_cb):
                self._persist_cb(self._cats)
                return
        except Exception:
            pass

        try:
            if _persist_categories_block is not None:
                _persist_categories_block(self._cats)
        except Exception:
            return
