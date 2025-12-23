# ---- Public, stable API (used by UI shims and pipelines) ----


def is_category_placeholder(cat: str | None) -> bool:
    s = (cat or "").strip().lower()
    return (not s) or (s in {"unassigned", "none", "n/a", "na", "-", "--", "—"})

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

def is_category_placeholder(cat: str | None) -> bool:
    """
    Legacy helper used by pure tests and older UI shims.
    """
    s = (cat or "").strip()
    if not s:
        return True
    lowered = s.lower()
    return lowered in {"unassigned", "none", "n/a", "na", "-", "--", "—"}