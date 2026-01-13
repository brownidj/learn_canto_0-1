"""
CategoryManager meaning resolution extracted for maintainability.

Centralizes all meaning lookup, resolution, and display formatting logic.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerMeaningResolver:
    """Manages meaning resolution for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    @staticmethod
    def flatten_vocab_meanings(raw_meanings) -> list[str]:
        """Flatten vocab meanings into a simple list of non-empty strings.

        The vocab store may contain meanings as a list of lists, or a flat list.
        This helper is intentionally conservative and never raises.
        """
        out: list[str] = []
        try:
            if isinstance(raw_meanings, (list, tuple)):
                for item in raw_meanings:
                    if isinstance(item, (list, tuple)):
                        for sub in item:
                            try:
                                s = str(sub or "").strip()
                            except (TypeError, ValueError):
                                s = ""
                            if s:
                                out.append(s)
                    else:
                        try:
                            s = str(item or "").strip()
                        except (TypeError, ValueError):
                            s = ""
                        if s:
                            out.append(s)
            else:
                try:
                    s = str(raw_meanings or "").strip()
                except (TypeError, ValueError):
                    s = ""
                if s:
                    out.append(s)
        except (TypeError, ValueError):
            return out

        return out

    def resolve_meanings_for_candidate(
        self,
        hz: str,
        src: str = "",
        *,
        preferred: bool = False,
        max_items: int = 2,
    ) -> list[str]:
        """Single meaning-resolution path for the UI.

        Rule: all meaning resolutions shown in this dialog must flow through this method.

        Authoritative source:
          1) MeaningFacade.select_candidate(...).meanings

        Fallback:
          2) MeaningFacade.meanings_for_display(hanzi)

        Display cleaning (applied exactly once here):
          - strip whitespace
          - drop empty entries
          - prefer entries without '[' or '(' (but fall back to the original list if that removes everything)
          - cap to `max_items`

        NOTE:
            UI must not call pipeline gloss resolvers directly.
            Any pipeline involvement must be encapsulated inside the facade.
        """
        # Prefer user's vocab meanings first when we have exact Hanzi match
        hz_key = (hz or "").strip()
        try:
            v = getattr(self.dialog, "_vocab", None)
            if isinstance(v, dict) and hz_key:
                entry = v.get(hz_key)
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    raw_meanings = entry[0]
                    entry_jy = entry[1]

                    # Flatten meanings
                    flat = self.flatten_vocab_meanings(raw_meanings)

                    # Compare normalized Jyutping where possible
                    try:
                        jy_widget = getattr(self.dialog, "_add_jy", None)
                        cand_jy = (jy_widget.text() or "").strip() if jy_widget is not None else ""
                    except (TypeError, AttributeError, RuntimeError):
                        cand_jy = ""

                    try:
                        norm = getattr(self.dialog, "_normalize_jy", None)
                        n_cand = str(norm(cand_jy) if callable(norm) else cand_jy).strip()
                        n_entry = str(norm(entry_jy) if callable(norm) else entry_jy).strip()
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        n_cand = str(cand_jy or "").strip()
                        n_entry = str(entry_jy or "").strip()

                    if flat and (not n_cand or not n_entry or n_cand == n_entry):
                        if isinstance(max_items, int) and max_items > 0:
                            return flat[:max_items]
                        return flat
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

        hz_s = (hz or "").strip()
        if not hz_s:
            return []

        try:
            n = int(max_items or 2)
        except (TypeError, ValueError):
            n = 2
        if n < 1:
            n = 1

        def _clean(items: list[str] | None) -> list[str]:
            if not items:
                return []

            raw: list[str] = []
            for x in items:
                s = str(x).strip()
                if s:
                    raw.append(s)

            if not raw:
                return []

            preferred_items = [g for g in raw if ("[" not in g and "(" not in g)]
            out = preferred_items if preferred_items else raw
            return out[:n]

        # Domain façade (authoritative)
        facade = getattr(self.dialog, "_meaning_facade", None)
        if facade is not None and hasattr(facade, "select_candidate"):
            try:
                selected = facade.select_candidate(
                    hz_s,
                    (src or "").strip(),
                    preferred=bool(preferred),
                    max_items=n,
                )
                ms_obj = getattr(selected, "meanings", None) if selected is not None else None
                ms_list = list(ms_obj) if ms_obj is not None else []
                cleaned = _clean([str(x) for x in ms_list])
                if cleaned:
                    return cleaned
            except (TypeError, AttributeError, RuntimeError) as e:
                try:
                    logger.debug("MeaningFacade.select_candidate failed for %r (%s): %s", hz_s, src, e)
                except (RuntimeError, TypeError, AttributeError):
                    pass

        # Final fallback: meanings_for_display for Hanzi
        try:
            ms2 = self.meanings_for_hanzi(hz_s) or []
        except (TypeError, AttributeError, RuntimeError) as e:
            try:
                logger.debug("_meanings_for_hanzi failed for %r: %s", hz_s, e)
            except (RuntimeError, TypeError, AttributeError):
                pass
            ms2 = []

        return _clean([str(x) for x in (ms2 or [])])

    def meanings_for_hanzi(self, hz: str) -> list[str]:
        """Hanzi-only meaning lookup fallback.

        This is intentionally conservative:
          1) If the MeaningFacade provides meanings_for_display(hz), use it.
          2) Else, fall back to the current vocab entry (if present).
        """
        hz_s = str(hz or "").strip()
        if not hz_s:
            return []

        facade = getattr(self.dialog, "_meaning_facade", None)
        if facade is not None and hasattr(facade, "meanings_for_display"):
            try:
                ms = facade.meanings_for_display(hz_s)
                out = []
                if ms is not None:
                    for x in list(ms):
                        s = str(x or "").strip()
                        if s:
                            out.append(s)
                return out
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Vocab fallback
        try:
            v = getattr(self.dialog, "_vocab", None)
            if isinstance(v, dict) and hz_s in v:
                row = v.get(hz_s)
                if isinstance(row, (list, tuple)) and len(row) >= 1:
                    meanings = row[0]
                    return self.flatten_vocab_meanings(meanings)
        except (TypeError, AttributeError, RuntimeError):
            pass

        return []
