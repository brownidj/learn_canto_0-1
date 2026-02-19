"""
Pure utility functions extracted from main.py.

These are stateless helper functions with no UI dependencies.
"""
import re
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


def perf_start(name: str) -> float:
    """Start a performance timing measurement.

    Args:
        name: Name of the operation being timed

    Returns:
        Start time in seconds (or 0.0 if timing fails)
    """
    try:
        t0 = time.perf_counter()
        try:
            logger.debug("PERF start: %s", name)
        except (RuntimeError, AttributeError):
            pass
        return t0
    except (RuntimeError, AttributeError):
        return 0.0


def perf_end(name: str, t0: float) -> None:
    """End a performance timing measurement and log the duration.

    Args:
        name: Name of the operation being timed
        t0: Start time from perf_start()
    """
    try:
        if not t0:
            return
        dt_ms = (time.perf_counter() - float(t0)) * 1000.0
        try:
            logger.debug("PERF end: %s (%.1f ms)", name, dt_ms)
        except (RuntimeError, AttributeError):
            pass
    except (RuntimeError, AttributeError):
        pass


def normalize_jy(jy: str) -> str:
    """Normalize jyutping: lowercase, collapse spaces."""
    return " ".join((jy or "").strip().lower().split())


def ensure_jyut(hanzi: str, jyut: str) -> str:
    """Return provided jyut if present; otherwise leave empty (no 3rd-party fallback)."""
    return jyut or ""


def normalize_reverse_index(obj: Any) -> dict:
    """Normalize reverse-index payloads to the expected shape.

    Expected shape:
      {"jyutping": [("漢字", "src", 123), ...], ...}

    Some loaders may return a wrapper dict of size 1 (e.g., {"reverse": {...}})
    or a dict mapping jyutping -> ["漢字", ...]. We coerce these into the
    canonical form used by reverse lookup functions.
    """
    # Unwrap common one-key wrapper dicts
    if isinstance(obj, dict) and len(obj) == 1:
        try:
            only_val = next(iter(obj.values()))
            if isinstance(only_val, dict):
                obj = only_val
        except Exception:
            pass

    if not isinstance(obj, dict) or not obj:
        return {}

    out = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if not v:
            continue

        # Already canonical: list of triples
        if isinstance(v, list) and v and isinstance(v[0], (tuple, list)):
            triples = []
            ok = True
            for item in v:
                try:
                    hz = str(item[0]).strip()
                    src = str(item[1]).strip() if len(item) > 1 else "tier1"
                    score = int(item[2]) if len(item) > 2 else 100
                except Exception:
                    ok = False
                    break
                if hz:
                    triples.append((hz, src or "tier1", score))
            if ok and triples:
                out[k] = triples
                continue

        # Coerce: list of strings -> list of triples
        if isinstance(v, list) and v and isinstance(v[0], str):
            triples = []
            for hz in v:
                hz_s = str(hz).strip()
                if hz_s:
                    triples.append((hz_s, "tier1", 100))
            if triples:
                out[k] = triples
                continue

        # Coerce: single string -> one triple
        if isinstance(v, str):
            hz_s = v.strip()
            if hz_s:
                out[k] = [(hz_s, "tier1", 100)]
            continue

    return out


def normalize_categories_yaml_payload(doc: Any) -> dict:
    """Coerce a categories mapping into category -> list[hanzi].

    Supports both:
      - {category: ["漢字", ...], ...}
      - {category: {items: ["漢字", ...], ...}, ...}
    """
    if not isinstance(doc, dict):
        return {}
    out = {}
    for k, v in doc.items():
        try:
            key = str(k).strip()
        except Exception:
            continue
        if not key:
            continue
        if isinstance(v, list):
            items = []
            for hz in v:
                try:
                    s = str(hz).strip()
                except Exception:
                    s = ""
                if s:
                    items.append(s)
            out[key] = items
            continue
        if isinstance(v, dict):
            raw_items = v.get("items")
            if isinstance(raw_items, list):
                items = []
                for hz in raw_items:
                    try:
                        s = str(hz).strip()
                    except Exception:
                        s = ""
                    if s:
                        items.append(s)
                out[key] = items
                continue
        # Unknown shape: keep an empty list so the category still exists
        out.setdefault(key, [])
    return out


def parse_base_point_size_from_stylesheet(stylesheet: str) -> int:
    """Extract font-size in pt from a Qt stylesheet string."""
    try:
        m = re.search(r"font-size\s*:\s*(\d+)\s*pt", stylesheet, re.IGNORECASE)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 96  # default if not found
