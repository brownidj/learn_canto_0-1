"""
CategoryManager category ops services.

Infrastructure wiring for CategoryRepo/CategoryCommitService and category adds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_widgets import resolve_category_manager_widgets

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog


class CategoryOpsServices:
    """Service wiring for CategoryManager category operations."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)

    def ensure_category_services(self):
        """Ensure CategoryRepo + CategoryCommitService are available (UI-free, best-effort)."""
        try:
            repo = self._dlg.get("_cat_repo")
        except (TypeError, AttributeError, RuntimeError):
            repo = None

        try:
            svc = self._dlg.get("_cat_commit_svc")
        except (TypeError, AttributeError, RuntimeError):
            svc = None

        if repo is not None and svc is not None:
            return repo, svc

        try:
            from domain.category_repo import CategoryRepo
            from domain.category_commit import CategoryCommitService
        except (ImportError, ModuleNotFoundError):
            return None, None

        try:
            canon_fn = self._dlg.get("_canon_cat_name")
            canon_cb = canon_fn if callable(canon_fn) else None
        except (TypeError, AttributeError, RuntimeError):
            canon_cb = None

        def _persist_cb(_cats_map: dict) -> None:
            try:
                from persistence.categories_store import persist_categories_yaml
                persist_categories_yaml(_cats_map)
            except Exception:
                return

        try:
            cats_map = self._dlg.get("_cats")
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        if not isinstance(cats_map, dict):
            cats_map = {}
            try:
                self._dlg.set("_cats", cats_map)
            except (TypeError, AttributeError, RuntimeError):
                pass

        try:
            try:
                repo = CategoryRepo(cats_map, canon=canon_cb, persist=_persist_cb)
            except TypeError:
                try:
                    repo = CategoryRepo(cats_map, canon_cb, _persist_cb)
                except TypeError:
                    repo = CategoryRepo(cats_map)

            try:
                from typing import cast
                from domain.category_commit import CategoryRepoLike
                repo_like = cast(CategoryRepoLike, repo)
            except Exception:
                repo_like = repo

            svc = CategoryCommitService(repo_like)
        except Exception:
            return None, None

        try:
            try:
                from typing import cast
                from domain.category_commit import CategoryRepoLike
                self._dlg.set("_cat_repo", cast(CategoryRepoLike, repo))
            except Exception:
                self._dlg.set("_cat_repo", repo)
            self._dlg.set("_cat_commit_svc", svc)
        except (TypeError, AttributeError, RuntimeError):
            pass

        return repo, svc

    def add_new_category(self, cat: str) -> bool:
        """Add a new category via the authoritative CategoryRepo (best-effort)."""
        try:
            cat_s = str(cat or "").strip()
        except Exception:
            cat_s = ""

        if not cat_s:
            return False

        repo = self._dlg.get("_cat_repo")
        if repo is not None and hasattr(repo, "add"):
            try:
                ok = bool(repo.add(cat_s))
            except Exception:
                ok = False

            if ok:
                try:
                    widgets = resolve_category_manager_widgets(self._dlg)
                    w_cat = widgets.get("add_cat")
                except Exception:
                    w_cat = None

                if w_cat is not None:
                    try:
                        if hasattr(w_cat, "findText") and hasattr(w_cat, "addItem"):
                            if int(w_cat.findText(repo.canon(cat_s))) < 0:
                                w_cat.addItem(repo.canon(cat_s))
                    except Exception:
                        pass

            return ok

        try:
            cats_map = self._dlg.get("_cats")
        except Exception:
            cats_map = None

        if not isinstance(cats_map, dict):
            return False

        try:
            canon = self._dlg.get("_canon_cat_name")
            cat_key = str(canon(cat_s) if callable(canon) else cat_s).strip()
        except Exception:
            cat_key = cat_s

        if not cat_key:
            return False

        if cat_key not in cats_map:
            cats_map[cat_key] = []
        return True
