from __future__ import annotations

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_category_commit_flow import decide_category_commit
from ui.category_manager_category_ops_services import CategoryOpsServices


class CategoryOpsCommitLogic:
    """Category commit logic + state updates (no widget effects)."""

    def __init__(self, dialog):
        self._dlg = CategoryManagerDialogAdapter(dialog)
        self._services = CategoryOpsServices(dialog)

    def add_new_category(self, cat: str) -> bool:
        return self._services.add_new_category(cat)

    def ensure_category_services(self):
        return self._services.ensure_category_services()

    def decide_commit(self, *, cat_raw: str, has_jy: bool, confirm_add_fn=None):
        repo, svc = self._services.ensure_category_services()
        if repo is None or svc is None:
            return None
        decision = decide_category_commit(
            cat_raw=cat_raw,
            has_jy=has_jy,
            repo=repo,
            svc=svc,
            confirm_add_fn=confirm_add_fn,
        )
        try:
            print(
                "DBG[CAT] decide_commit",
                f"ok={decision.ok}",
                f"cat='{decision.category}'",
                f"exists={decision.exists_now}",
                f"fill={decision.should_fill_candidates}",
            )
        except Exception:
            pass
        return decision

    def apply_commit_state(self, *, cat: str, exists_now: bool, user_confirmed_add: bool) -> None:
        self._sync_category_map(cat, exists_now, user_confirmed_add)
        self._sync_view_model(cat)

    def _sync_category_map(self, cat: str, exists_now: bool, user_confirmed_add: bool) -> None:
        if (not exists_now) and user_confirmed_add:
            self._ensure_category_in_map(cat)

        self._ensure_category_in_map(cat)
        self._sync_all_cats_list(cat)

    def _sync_view_model(self, cat: str) -> None:
        try:
            cat_l = cat.lower()
            cat_ok = bool(cat) and cat_l not in ("unassigned", "all")
        except Exception:
            cat_ok = False
        self._dlg.call("_update_add_edit_state", category=cat, cat_ok=bool(cat_ok))
        self._dlg.set("_last_committed_category", cat)

    def _ensure_category_in_map(self, cat: str) -> None:
        try:
            cats_map = self._dlg.get("_cats")
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        if not isinstance(cats_map, dict):
            return

        try:
            cat_s = str(cat or "").strip()
        except Exception:
            cat_s = ""

        if not cat_s:
            return

        try:
            if cat_s not in cats_map:
                cats_map[cat_s] = []
        except Exception:
            pass

    def _sync_all_cats_list(self, cat: str) -> None:
        try:
            all_cats = self._dlg.get("_all_cats")
        except (TypeError, AttributeError, RuntimeError):
            all_cats = None

        if not isinstance(all_cats, list):
            return

        try:
            cat_s = str(cat or "").strip()
        except Exception:
            cat_s = ""

        if not cat_s:
            return

        try:
            if cat_s not in all_cats:
                all_cats.append(cat_s)
                all_cats.sort(key=lambda s: str(s).lower())
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass
