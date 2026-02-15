from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_ui_services import CategoryManagerUIService


class CategoryManagerComboService:
    """Shared combobox utilities for CategoryManager."""

    def __init__(self, dialog_or_adapter):
        if isinstance(dialog_or_adapter, CategoryManagerDialogAdapter):
            self._dlg = dialog_or_adapter
        else:
            self._dlg = CategoryManagerDialogAdapter(dialog_or_adapter)
        self._ui = CategoryManagerUIService(self._dlg)

    # ---- Candidates combo ----

    def populate_candidates(self, cands_list: list) -> None:
        try:
            from ui.candidate_combo import CandidateComboController
        except (ImportError, ModuleNotFoundError):
            return
        combo = self._ui.widget("cand_combo")
        if combo is None:
            return
        try:
            ctrl = self._dlg.get("_cand_combo_ctrl")
        except (TypeError, AttributeError, RuntimeError):
            ctrl = None
        if ctrl is None:
            try:
                ctrl = CandidateComboController(combo)
                self._dlg.set("_cand_combo_ctrl", ctrl)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                return
        try:
            ctrl.clear()
            ctrl.populate(cands_list)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def candidate_text_for_index(self, idx: int) -> str:
        combo = self._ui.widget("cand_combo")
        if combo is None:
            return ""
        try:
            if hasattr(combo, "itemText"):
                return str(combo.itemText(idx) or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return ""
        try:
            return str(combo.currentText() or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return ""

    def candidate_src_for_index(self, idx: int) -> str:
        combo = self._ui.widget("cand_combo")
        if combo is None:
            return ""
        try:
            from PySide6.QtCore import Qt as _Qt
            data = None
            try:
                data = combo.itemData(idx)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                data = None
            if (data is None) and (_Qt is not None):
                try:
                    data = combo.itemData(idx, _Qt.ItemDataRole.UserRole)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    data = None
            if isinstance(data, dict):
                return str(data.get("src", "") or "").strip()
            if isinstance(data, (list, tuple)) and len(data) >= 2:
                return str(data[1] or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return ""
        return ""

    def current_candidate_index(self) -> int:
        combo = self._ui.widget("cand_combo")
        if combo is None:
            return -1
        try:
            return int(combo.currentIndex())
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return -1

    def candidate_index_from_args(self, args) -> int:
        combo = self._ui.widget("cand_combo")
        if combo is None:
            return -1
        idx = None
        if args:
            a0 = args[0]
            if isinstance(a0, int):
                idx = a0
            elif isinstance(a0, str):
                try:
                    idx = int(combo.findText(a0))
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    idx = None
        if idx is None:
            idx = self.current_candidate_index()
        try:
            return int(idx)
        except (TypeError, ValueError):
            return -1

    # ---- Category combo ----

    def ensure_category_in_combo(self, cat: str) -> None:
        combo = self._ui.widget("add_cat")
        if combo is None:
            return
        try:
            cat_s = str(cat or "").strip()
        except Exception:
            cat_s = ""
        if not cat_s:
            return
        try:
            existing = []
            try:
                n = int(combo.count())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                n = 0
            for i in range(max(0, n)):
                try:
                    t = str(combo.itemText(i) or "").strip()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    t = ""
                if t:
                    existing.append(t)
            if cat_s not in existing:
                merged = sorted(set(existing + [cat_s]), key=lambda s: str(s).lower())
                with self._ui.block_signals("add_cat"):
                    try:
                        combo.clear()
                        combo.addItems(list(merged))
                    except (TypeError, AttributeError, RuntimeError):
                        pass
                    try:
                        combo.setEditable(True)
                    except (TypeError, AttributeError, RuntimeError):
                        pass
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def set_category_selection(self, cat: str) -> None:
        combo = self._ui.widget("add_cat")
        if combo is None:
            return
        try:
            cat_s = str(cat or "").strip()
        except Exception:
            cat_s = ""
        if not cat_s:
            return
        try:
            if hasattr(combo, "setCurrentText"):
                combo.setCurrentText(cat_s)
                return
        except (TypeError, AttributeError, RuntimeError):
            pass
        try:
            idx = int(combo.findText(cat_s))
            if idx >= 0:
                combo.setCurrentIndex(idx)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def refresh_category_dropdown(self, cats_map: dict, *, selected: str = "") -> None:
        if not isinstance(cats_map, dict):
            return
        try:
            keys = [str(k).strip() for k in cats_map.keys() if str(k).strip()]
        except (TypeError, ValueError):
            keys = []
        try:
            keys = [k for k in keys if k.lower() != "all"]
        except (TypeError, ValueError):
            pass
        if not any((k.lower() == "unassigned") for k in keys):
            keys.append("unassigned")
        try:
            self._dlg.set("_all_cats", sorted(set(keys), key=lambda s: str(s).lower()))
        except (TypeError, ValueError):
            try:
                self._dlg.set("_all_cats", list(dict.fromkeys(keys)))
            except (TypeError, ValueError):
                return

        combo = self._ui.widget("add_cat")
        if combo is None or not hasattr(combo, "clear") or not hasattr(combo, "addItems"):
            return
        with self._ui.block_signals("add_cat"):
            try:
                combo.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass
            try:
                combo.addItems(self._dlg.get("_all_cats", []))
            except (TypeError, AttributeError, RuntimeError):
                pass

        sel = (selected or "").strip()
        if sel:
            try:
                if hasattr(combo, "findText") and int(combo.findText(sel)) < 0 and hasattr(combo, "addItem"):
                    combo.addItem(sel)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass
            try:
                combo.setCurrentText(sel)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                try:
                    idx = int(combo.findText(sel))
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass
        else:
            try:
                combo.setCurrentIndex(-1)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass
