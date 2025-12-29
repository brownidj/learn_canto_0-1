"""Duplicate detection rules (domain-only).

The project currently prefers the unified `vocab.yaml` structure:

    vocab = {
        "categories": {...},
        "entries": {
            "nei5 hou2": {
                "headword": "你好",          # optional
                "jyutping": "nei5 hou2",     # optional/redundant
                "senses": [
                    {"hanzi": "你好", "gloss": "hello", "categories": ["greetings"]},
                    ...
                ]
            },
            ...
        }
    }

Duplicate detection should primarily treat `entries` keys as authoritative.

This module is deliberately UI-free. Callers inject `normalize` if they want
project-specific normalisation; otherwise we use a safe default.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


def _default_norm(x: str) -> str:
    return " ".join((x or "").strip().lower().split())


def _norm_fn(normalize: Callable[[str], str] | None) -> Callable[[str], str]:
    return normalize if callable(normalize) else _default_norm


def _as_entries_mapping(vocab: Any) -> Mapping[str, Any] | None:
    """Return the preferred entries mapping (jyutping -> entry) if present."""
    if not isinstance(vocab, dict):
        return None

    entries = vocab.get("entries")
    if isinstance(entries, dict):
        return entries

    # Tolerant: sometimes callers pass entries directly.
    try:
        sample = list(vocab.items())[:5]
    except Exception:
        sample = []

    looks_like_entries = False
    for _k, _v in sample:
        if isinstance(_v, dict) and (
            "senses" in _v or "jyutping" in _v or "headword" in _v or "hanzi" in _v
        ):
            looks_like_entries = True
            break

    return vocab if looks_like_entries else None


def _legacy_hanzi_keyed(vocab: Any) -> bool:
    """True if vocab looks like the legacy hanzi->tuple/list shape."""
    if not isinstance(vocab, dict) or not vocab:
        return False
    try:
        k, v = next(iter(vocab.items()))
    except Exception:
        return False
    if not isinstance(k, str):
        return False
    return isinstance(v, (list, tuple))


def is_duplicate_jy(
    jy: str,
    reverse_index: Any = None,
    vocab: Any = None,
    normalize: Callable[[str], str] | None = None,
) -> bool:
    """Compatibility wrapper to detect duplicate Jyutping strings.

    Accepts both old and new calling conventions:
      - jy: Jyutping string to check.
      - reverse_index: Ignored, present for signature compatibility.
      - vocab: The vocabulary data structure to check against.
      - normalize: Optional normalization function for Jyutping strings.

    Returns True if the Jyutping already exists in vocab after normalization.
    """
    try:
        jy_s = (jy or "").strip()
        if not jy_s or vocab is None:
            return False

        norm = _norm_fn(normalize)
        jy_n = norm(jy_s)

        entries = _as_entries_mapping(vocab)
        if entries is not None:
            # Fast path: exact key hit
            try:
                if jy_s in entries:
                    return True
            except Exception:
                pass

            # Normalised key match
            try:
                for k in entries.keys():
                    if norm(str(k)) == jy_n:
                        return True
            except Exception:
                return False

            return False

        # Legacy fallback: scan hanzi->(..., jy, ...)
        if _legacy_hanzi_keyed(vocab):
            try:
                for _hz, _val in vocab.items():
                    try:
                        vjy = (
                            _val[1]
                            if isinstance(_val, (list, tuple)) and len(_val) > 1
                            else ""
                        )
                        if norm(str(vjy or "")) == jy_n:
                            return True
                    except Exception:
                        continue
            except Exception:
                return False

        return False
    except Exception:
        return False


def is_exact_duplicate_entry(
    vocab: Any,
    jy: str,
    hz: str,
    normalize: Callable[[str], str] | None = None,
) -> bool:
    """Return True iff the exact (jy, hanzi) already exists.

    Why this exists:
      - `is_duplicate_jy` blocks re-using a Jyutping at all.
      - `is_exact_duplicate_entry` is useful when you *allow* a Jyutping to exist
        multiple times but want to block the identical entry being added twice.

    In the unified vocab.yaml structure this checks the entry under the jy key
    (or normalised equivalent) and then compares against:
      - entry['headword'] (if present)
      - any sense['hanzi'] values

    In legacy shape it checks vocab[hanzi][1] == jy (normalised).
    """
    try:
        hz_s = (hz or "").strip()
        jy_s = (jy or "").strip()
        if not hz_s or not jy_s:
            return False

        norm = _norm_fn(normalize)
        jy_n = norm(jy_s)

        entries = _as_entries_mapping(vocab)
        if entries is not None:
            entry: Any = None

            # Exact key first
            try:
                entry = entries.get(jy_s)
            except Exception:
                entry = None

            # Normalised key fallback
            if entry is None:
                try:
                    for k, v in entries.items():
                        if norm(str(k)) == jy_n:
                            entry = v
                            break
                except Exception:
                    entry = None

            if not isinstance(entry, dict):
                return False

            # 1) headword / top-level hanzi
            try:
                head = entry.get("headword") or entry.get("hanzi") or entry.get("hz") or ""
            except Exception:
                head = ""

            if (str(head) or "").strip() == hz_s and head:
                return True

            # 2) senses[*].hanzi
            try:
                senses = entry.get("senses")
            except Exception:
                senses = None

            if isinstance(senses, list):
                for s in senses:
                    if not isinstance(s, dict):
                        continue
                    try:
                        shz = (s.get("hanzi") or "").strip()
                    except Exception:
                        shz = ""
                    if shz == hz_s and shz:
                        return True

            return False

        # Legacy fallback
        if not isinstance(vocab, dict):
            return False

        val = vocab.get(hz_s)
        if not isinstance(val, (list, tuple)) or len(val) < 2:
            return False

        vjy = val[1]
        return norm(str(vjy or "")) == jy_n
    except Exception:
        return False