"""
CategoryManager meaning resolution extracted for maintainability.

Centralizes all meaning lookup, resolution, and display formatting logic.
"""

import logging
from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_meaning_resolver_service import (
    MeaningResolverService,
    build_meaning_resolver_service,
)
from ui.category_manager_ui_services import CategoryManagerUIService

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerMeaningResolver:
    """Manages meaning resolution for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog", service: MeaningResolverService | None = None):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._service = service or build_meaning_resolver_service(dialog)

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
            vocab_svc = self._service.vocab_service()
            if vocab_svc is not None and hz_key:
                entry = vocab_svc.get_entry_raw(hz_key) if hasattr(vocab_svc, "get_entry_raw") else None
                if entry is not None:
                    raw_meanings, entry_jy = entry

                    # Flatten meanings
                    flat = self.flatten_vocab_meanings(raw_meanings)

                    # Compare normalized Jyutping where possible
                    cand_jy = self._service.jyutping_text()

                    try:
                        from domain.jyutping_validation import normalize_jyutping
                        n_cand = normalize_jyutping(cand_jy)
                        n_entry = normalize_jyutping(entry_jy)
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
        facade = self._service.facade()
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

        facade = self._service.facade()
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
            vocab_svc = self._service.vocab_service()
            if vocab_svc is not None and hasattr(vocab_svc, "get_meanings_raw"):
                raw = vocab_svc.get_meanings_raw(hz_s)
                if raw is not None:
                    return self.flatten_vocab_meanings(raw)
        except (TypeError, AttributeError, RuntimeError):
            pass
        return []

    def resolve_for_add_edit(
        self,
        *,
        hanzi: str,
        src: str,
        jyutping: str,
        allow_canto: bool,
    ) -> tuple[str, str]:
        """Resolve meaning for Add/Edit in one place.

        Returns (meaning, source) where source is 'resolver' or 'canto' (or '').
        """
        dlg = self._dlg
        ui = CategoryManagerUIService(dlg)
        hz = str(hanzi or "").strip()
        if not hz:
            return "", ""

        meanings = self.resolve_meanings_for_candidate(hz, src)

        joined = ui.join_meanings(meanings)
        if str(joined or "").strip():
            return joined, "resolver"

        if not allow_canto:
            return "", ""

        try:
            from ui.category_manager_add_edit_flow_services import apply_cantonese_cache
            applied = apply_cantonese_cache(dlg, hanzi=hz, jyutping=jyutping)
        except Exception:
            applied = False
        if applied:
            return str(ui.get_meaning_text() or "").strip(), "canto"

        return "", ""
