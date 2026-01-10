# category_repo.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


CatsMap = Dict[str, list]


def _default_canon(name: str) -> str:
    # Conservative canonicalisation: strip only.
    # If you already have a stricter normaliser in the dialog, pass it in.
    return (name or "").strip()


@dataclass(frozen=True, slots=True)
class CategoryRepoSnapshot:
    """Pure snapshot useful for tests/debugging."""
    cats: CatsMap


class CategoryRepo:
    """Authoritative category store.

    Contract:
      - Exactly one authoritative structure: self._cats
      - After any successful add-category flow, self._cats[cat] exists.
      - Any other map (e.g. legacy self._categories_map) is a derived/synced view.

    This repo is intentionally small and UI-agnostic.
    Persistence is best-effort and is injected via a callback.
    """

    def __init__(
            self,
            cats: Optional[CatsMap] = None,
            *,
            canon: Optional[Callable[[str], str]] = None,
            persist: Optional[Callable[[CatsMap], None]] = None,
    ) -> None:
        # Single source of truth: keep a reference to the caller's dict.
        # Normalise keys/values in-place so all owners observe the same mutations.
        if isinstance(cats, dict):
            self._cats = cats
        else:
            self._cats = {}

        # Normalise in-place: canonicalise keys and ensure list values.
        try:
            normalised: CatsMap = {}
            for k, v in list(self._cats.items()):
                key = _default_canon(str(k))
                if not key:
                    continue
                normalised[key] = list(v or [])
            self._cats.clear()
            self._cats.update(normalised)
        except (TypeError, ValueError, RuntimeError):
            # Best-effort: never raise in repo init.
            pass

        self._canon: Callable[[str], str] = canon if callable(canon) else _default_canon
        self._persist: Optional[Callable[[CatsMap], None]] = persist if callable(persist) else None

        # Default persistence: write to data/categories.yaml using domain.storage_paths.
        # This keeps persistence logic out of category_manager.py.
        if self._persist is None:
            self._persist = self._persist_to_categories_yaml

        # Ensure "unassigned" exists (repo-level invariant).
        if not self.exists("unassigned"):
            self._cats["unassigned"] = []

    def snapshot(self) -> CategoryRepoSnapshot:
        # Copy for safety in tests/debugging.
        out: CatsMap = {k: list(v or []) for k, v in self._cats.items()}
        return CategoryRepoSnapshot(cats=out)

    def canon(self, raw: str) -> str:
        try:
            return _default_canon(str(self._canon(raw)))
        except (TypeError, ValueError):
            return _default_canon(str(raw or ""))

    def exists(self, cat: str) -> bool:
        c = self.canon(cat)
        return bool(c) and c in self._cats

    def ensure(self, cat: str) -> str:
        """Ensure category exists in authoritative map and return canonical name."""
        c = self.canon(cat)
        if not c:
            return ""
        if c not in self._cats:
            self._cats[c] = []
        return c

    def add(self, cat: str) -> bool:
        """Add category if missing. Returns True iff it now exists in authoritative map."""
        c = self.ensure(cat)
        if not c:
            return False
        self._best_effort_persist()
        return True

    def keys(self) -> list[str]:
        return list(self._cats.keys())

    def sorted_keys(self, *, include_all: bool = False) -> list[str]:
        keys = []
        for k in self._cats.keys():
            if (not include_all) and str(k).strip().lower() == "all":
                continue
            keys.append(k)
        keys.sort(key=lambda s: s.lower())
        return keys

    def as_dict(self) -> CatsMap:
        """Direct view for legacy integration; do not mutate externally."""
        return self._cats

    def sync_to(self, target: Optional[CatsMap]) -> None:
        """Best-effort: make target contain at least the keys of authoritative _cats."""
        if not isinstance(target, dict):
            return
        for k, v in self._cats.items():
            if k not in target:
                target[k] = list(v or [])

    def _persist_to_categories_yaml(self, cats_map: CatsMap) -> None:
        """Default persistence implementation.

        Writes the authoritative categories mapping to the canonical categories.yaml
        location resolved by domain.storage_paths.categories_yaml_path().

        Best-effort only: callers must not rely on persistence succeeding.
        """
        # Avoid importing project path logic unless persistence is needed.
        try:
            from domain.storage_paths import categories_yaml_path
        except Exception:
            return

        if yaml is None:
            return

        try:
            path = categories_yaml_path()
        except Exception:
            return

        try:
            # Deterministic output for diffs.
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(
                    cats_map,
                    fh,
                    allow_unicode=True,
                    sort_keys=True,
                    default_flow_style=False,
                )
        except Exception:
            # Must never raise from persistence.
            return

    def _best_effort_persist(self) -> None:
        if self._persist is None:
            return
        try:
            self._persist(self._cats)
        except (OSError, RuntimeError, TypeError, ValueError):
            # Persistence failures must not break in-memory invariants.
            return