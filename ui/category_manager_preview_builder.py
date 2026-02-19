"""
Add/Edit preview builder for CategoryManager.

UI-aware builder that reads widget state with minimal fallbacks.
"""

from dataclasses import dataclass, field

from ui.category_manager_add_edit_state_service import AddEditStateService
from ui.category_manager_ui_services import CategoryManagerUIService


@dataclass(frozen=True)
class AddEntryPreview:
    jyutping: str = ""
    hanzi: str = ""
    meaning: str = ""
    category: str = ""
    categories: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        jy = (self.jyutping or "").strip()
        hz = (self.hanzi or "").strip()
        mn = (self.meaning or "").strip()
        cat = (self.category or "").strip()
        cats_list = [str(c).strip() for c in (self.categories or []) if str(c).strip()]

        # Canonical keys are always present.
        payload = {
            "jyutping": jy,
            "hanzi": hz,
            "meaning": mn,
            "category": cat,
        }

        # Required legacy/test aliases.
        payload["gloss"] = mn
        if cats_list:
            payload["categories"] = cats_list
        else:
            payload["categories"] = ([cat] if cat else [])

        return payload


class AddEntryPreviewBuilder:
    """
    Best-effort preview builder for the Add/Edit entry flow.

    Goals:
      - Deterministic in offscreen tests
      - Minimal, predictable fallbacks
      - No long attribute-fishing ladders
    """

    @staticmethod
    def _resolve_vocab_service(dialog):
        try:
            return dialog.__dict__.get("_vocab_service")
        except Exception:
            return None

    @staticmethod
    def _meaning_from_service(vocab_svc, hanzi: str) -> str:
        if vocab_svc is None or not hasattr(vocab_svc, "get_meanings_raw"):
            return ""
        hz = (hanzi or "").strip()
        if not hz:
            return ""
        try:
            meanings = vocab_svc.get_meanings_raw(hz)
        except Exception:
            return ""
        if not isinstance(meanings, (list, tuple)):
            return ""
        out = []
        for g in meanings:
            try:
                s = str(g).strip()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                s = ""
            if s:
                out.append(s)
        return ", ".join(out)

    @staticmethod
    def _meaning_from_vocab_fallback(dialog, hanzi: str) -> str:
        """Fallback for tests/dummy dialogs without a vocab service."""
        try:
            vocab = dialog.__dict__.get("_vocab")
        except Exception:
            vocab = None
        if not isinstance(vocab, dict):
            return ""
        hz = (hanzi or "").strip()
        if not hz or hz not in vocab:
            return ""
        row = vocab.get(hz)
        if not isinstance(row, (list, tuple)) or len(row) < 1:
            return ""
        meanings = row[0]
        if not isinstance(meanings, (list, tuple)):
            return ""
        out = []
        for g in meanings:
            try:
                s = str(g).strip()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                s = ""
            if s:
                out.append(s)
        return ", ".join(out)

    @staticmethod
    def build(dialog) -> AddEntryPreview:
        """Canonical Add/Edit preview builder."""
        jy = hz = mn = cat = ""
        ui = CategoryManagerUIService(dialog)

        # 1) Read fields directly (best effort)
        try:
            jy_widget = ui.widget("add_jy")
            if jy_widget is not None:
                jy = ui.get_text_widget(jy_widget)
        except Exception:
            jy = ""

        try:
            hz_widget = ui.widget("add_hz")
            if hz_widget is not None:
                hz = ui.get_text_widget(hz_widget)
        except Exception:
            hz = ""

        try:
            mn_widget = ui.widget("add_mn")
            if mn_widget is not None:
                mn = ui.get_text_widget(mn_widget)
        except Exception:
            mn = ""

        try:
            cat_widget = ui.widget("add_cat")
            if cat_widget is not None:
                cat = ui.get_text_widget(cat_widget)
        except Exception:
            cat = ""
        cats_multi: list[str] = []
        try:
            cats_multi = list(getattr(dialog, "_selected_categories", []) or [])
        except Exception:
            cats_multi = []

        # 2) Normalise Jyutping using the dialog normaliser when available
        if jy:
            try:
                from domain.jyutping_validation import normalize_jyutping
                normalized_jy = normalize_jyutping(jy)

                # Ensure tone is preserved
                tone_match = next((char for char in jy if char.isdigit()), "")
                if tone_match and not any(char.isdigit() for char in normalized_jy):
                    normalized_jy += tone_match
                jy = normalized_jy
            except Exception:
                jy = ""

        # 3) Enrich from ViewModel when widgets are blank
        vm = None
        try:
            vm = AddEditStateService(dialog).get_state()
        except Exception:
            vm = None

        if vm is not None:
            if not jy:
                try:
                    jy = str(getattr(vm, "jy", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    jy = ""
            if not hz:
                try:
                    hz = str(getattr(vm, "hanzi", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    hz = ""
            if not mn:
                try:
                    mn = str(getattr(vm, "meaning", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    mn = ""
            if not cat:
                try:
                    cat = str(getattr(vm, "category", "") or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    cat = ""

        # If Hanzi still blank, allow candidate combobox currentText
        if not hz:
            try:
                combo = ui.widget("cand_combo")
                if combo is not None and hasattr(combo, "currentText"):
                    txt = str((combo.currentText() or "")).strip()
                    if txt and not txt.startswith("—"):
                        hz = txt
            except (TypeError, AttributeError, RuntimeError, ValueError):
                hz = hz or ""

        # Legacy reader removed (ViewModel + widgets are authoritative).

        # Final fallback: vocab-derived meanings (only if still blank)
        if not mn and hz:
            try:
                vocab_svc = AddEntryPreviewBuilder._resolve_vocab_service(dialog)
                mn = AddEntryPreviewBuilder._meaning_from_service(vocab_svc, hz)
                if not mn:
                    mn = AddEntryPreviewBuilder._meaning_from_vocab_fallback(dialog, hz)
            except Exception:
                mn = ""

        # Prefer multi-select categories if present
        if cats_multi and not cat:
            cat = cats_multi[0]

        return AddEntryPreview(jyutping=jy, hanzi=hz, meaning=mn, category=cat, categories=cats_multi)
