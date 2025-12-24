# ---- Public, stable API (used by UI shims and pipelines) ----


def is_category_placeholder(cat: str | None) -> bool:
    """Return True if `cat` is effectively a UI placeholder / not a real category key."""
    s_raw = (cat or "").strip()
    s = s_raw.lower()

    if (not s) or (s in {"unassigned", "none", "n/a", "na", "-", "--", "—"}):
        return True

    # Common UI placeholder strings (be tolerant of punctuation / em-dashes).
    # Examples seen in tests / UI:
    #   "— choose category —"
    #   "choose category"
    #   "select category"
    try:
        if "choose category" in s or "select category" in s:
            return True
        # If the string is mostly punctuation surrounding a known placeholder keyword.
        s_compact = " ".join(s.replace("—", " ").replace("-", " ").split())
        if s_compact in {"choose category", "select category"}:
            return True
    except Exception:
        pass

    return False

def get_cedict_meanings_for(hanzi: str) -> list[str]:
    from domain.meaning_sources import get_cedict_meanings_for as _f
    return _f(hanzi)

def get_cccanto_glosses_for(hanzi: str) -> list[str]:
    from domain.meaning_sources import get_cccanto_glosses_for as _f
    return _f(hanzi)


# Back-compat aliases (some call sites probe these names)
cedict_meanings_for = get_cedict_meanings_for
cccanto_glosses_for = get_cccanto_glosses_for


class MeaningResolver:
    def cedict_meanings_for(self, hanzi: str) -> list[str]:
        return get_cedict_meanings_for(hanzi)

    def cccanto_glosses_for(self, hanzi: str) -> list[str]:
        return get_cccanto_glosses_for(hanzi)

    def meanings_for(self, hanzi: str) -> list[str]:
        hz = (hanzi or "").strip()
        if not hz:
            return []

        out: list[str] = []
        # Prefer CC-Canto (more colloquial Cantonese), then fall back to CEDICT.
        try:
            out.extend(get_cccanto_glosses_for(hz))
        except Exception:
            pass
        try:
            out.extend(get_cedict_meanings_for(hz))
        except Exception:
            pass

        # De-dupe while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for x in out:
            s = str(x).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            deduped.append(s)

        return deduped


class MeaningFacade:
    """Deprecated stub kept for back-compat.

    Meaning resolution moved to `domain.meaning_sources`.
    """
    pass


# ---- Category helpers ----

def should_show_custom_hanzi_button(
    candidates: object | None,
    *,
    min_candidates: int = 1,
) -> bool:
    """Return True when the UI should offer manual Hanzi entry.

    Back-compat shim for older pure tests and UI shims.

    Current contract:
      - If there are *no* viable candidates, allow manual entry.
      - If candidates are present, hide the manual entry prompt.

    The function is intentionally tolerant of input shape and never raises.
    """
    try:
        if candidates is None:
            return True

        # Common shapes: list/tuple of candidates, or a dict keyed by something.
        if isinstance(candidates, dict):
            n = len(candidates)
        elif isinstance(candidates, (list, tuple, set)):
            # Count only viable candidates (non-empty after trimming).
            n = 0
            for x in candidates:
                try:
                    if str(x).strip():
                        n += 1
                except Exception:
                    continue
        else:
            # Unknown shape: best-effort treat as "has something" if truthy.
            return not bool(candidates)

        return n < int(min_candidates)
    except Exception:
        return True


def prefer_meanings(
    primary: object | None,
    fallback: object | None = None,
    *,
    max_items: int | None = None,
) -> list[str]:
    """Choose meanings for display without overwriting better primary glosses.

    Back-compat shim for older pure tests.

    Contract:
      - If `primary` contains any non-empty meaning(s), return those (de-duped, order preserved).
      - Otherwise, fall back to `fallback`.
      - `max_items` is optional; when None, do not cap the list.

    Accepts `str` or `list/tuple/set` for either input; unknown shapes are stringified.
    Never raises.
    """

    def _to_list(x: object | None) -> list[str]:
        if x is None:
            return []
        if isinstance(x, str):
            s = x.strip()
            return [s] if s else []
        if isinstance(x, (list, tuple, set)):
            out_l: list[str] = []
            for it in x:
                try:
                    s = str(it).strip()
                except Exception:
                    continue
                if s:
                    out_l.append(s)
            return out_l
        # Unknown shape: best-effort string conversion.
        try:
            s = str(x).strip()
        except Exception:
            return []
        if not s or s.lower() in {"none", "null"}:
            return []
        return [s]

    try:
        chosen = _to_list(primary)
        if not chosen:
            chosen = _to_list(fallback)

        # De-dupe while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for s in chosen:
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
            if max_items is not None and len(out) >= int(max_items):
                break

        return out
    except Exception:
        return []
