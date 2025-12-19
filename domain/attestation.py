"""Jyutping phrase attestation (lazy).

This module provides a single public predicate, `is_attested_phrase`, that can be
passed into `domain.category_rules.attested_or_structural_ok`.

Design goals:
- Pure domain logic (no UI imports).
- Lazy cache construction (no loading at import time).
- Best-effort file discovery; absence of data files should be non-fatal.
"""

from __future__ import annotations

from pathlib import Path
import csv

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


_ATTESTED_CACHE: set[str] | None = None


def _reset_attestation_cache() -> None:
    """Clear the attested phrase cache (for tests)."""
    global _ATTESTED_CACHE
    _ATTESTED_CACHE = None

def _norm_jy(jy: str) -> str:
    """Normalize Jyutping for cache keys."""
    return " ".join(str(jy).strip().lower().split())


def _find_project_root(start: Path) -> Path:
    """Best-effort project root discovery for data lookups."""
    here = start
    for _ in range(8):
        if (here / "pyproject.toml").exists() or (here / "requirements.txt").exists() or (here / ".git").exists():
            return here
        if here.parent == here:
            break
        here = here.parent
    return start


def _load_attested_phrases() -> set[str]:
    """Lazy-load attested Jyutping phrases from common data files.

    Supported (if present):
      - data/attested_phrases.txt (one phrase per line)
      - data/attested_phrases.csv (phrase in first column)
      - data/attested_phrases.yaml / .yml (list of phrases, or {phrases: [...]})

    If none are present, returns an empty set.
    """
    phrases: set[str] = set()

    project_root = _find_project_root(Path(__file__).resolve().parent)
    data_dir = project_root / "data"

    candidates = [
        data_dir / "attested_phrases.txt",
        data_dir / "attested_phrases.csv",
        data_dir / "attested_phrases.yaml",
        data_dir / "attested_phrases.yml",
    ]

    for path in candidates:
        if not path.exists() or not path.is_file():
            continue

        try:
            suffix = path.suffix.lower()

            if suffix == ".txt":
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    phrases.add(_norm_jy(line))

            elif suffix == ".csv":
                with path.open("r", encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if not row:
                            continue
                        val = str(row[0]).strip()
                        if not val or val.startswith("#"):
                            continue
                        phrases.add(_norm_jy(val))

            elif suffix in (".yaml", ".yml") and yaml is not None:
                obj = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(obj, list):
                    for item in obj:
                        if item:
                            phrases.add(_norm_jy(item))
                elif isinstance(obj, dict):
                    items = obj.get("phrases") or obj.get("attested") or obj.get("items")
                    if isinstance(items, list):
                        for item in items:
                            if item:
                                phrases.add(_norm_jy(item))

        except Exception:
            # Attestation is optional; malformed files must not crash importers.
            continue

    return phrases


def is_attested_phrase(jy: str) -> bool:
    """Return True if the Jyutping phrase appears in the attested list.

    This function is intentionally lazy (no cache built at import time).
    """
    global _ATTESTED_CACHE

    if not jy:
        return False

    if _ATTESTED_CACHE is None:
        _ATTESTED_CACHE = _load_attested_phrases()

    return _norm_jy(jy) in _ATTESTED_CACHE

__all__ = [
    "is_attested_phrase",
    "_reset_attestation_cache",
]
