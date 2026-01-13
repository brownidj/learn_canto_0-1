"""
CategoryManager category operations extracted for maintainability.

Handles category creation, commit flow, and dropdown synchronization.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox
from ui.widget_utils import WidgetAccessor, SignalBlocker

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerCategoryOpsController:
    """Manages category operations for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def ensure_category_services(self):
        """Ensure CategoryRepo + CategoryCommitService are available (UI-free, best-effort).

        Returns:
            (repo, svc) or (None, None) if unavailable.
        """
        try:
            repo = getattr(self.dialog, "_cat_repo", None)
        except (TypeError, AttributeError, RuntimeError):
            repo = None

        try:
            svc = getattr(self.dialog, "_cat_commit_svc", None)
        except (TypeError, AttributeError, RuntimeError):
            svc = None

        if repo is not None and svc is not None:
            return repo, svc

        # Lazy import
        try:
            from category_repo import CategoryRepo
            from category_commit import CategoryCommitService
        except (ImportError, ModuleNotFoundError):
            return None, None

        # Canonicaliser
        try:
            canon_fn = getattr(self.dialog, "_canon_cat_name", None)
            canon_cb = canon_fn if callable(canon_fn) else None
        except (TypeError, AttributeError, RuntimeError):
            canon_cb = None

        # Persist callback
        def _persist_cb(_cats_map: dict) -> None:
            try:
                from persistence.categories_store import persist_categories_yaml
                persist_categories_yaml(_cats_map)
            except Exception:
                return

        # Authoritative map
        try:
            cats_map = getattr(self.dialog, "_cats", None)
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        if not isinstance(cats_map, dict):
            cats_map = {}
            try:
                setattr(self.dialog, "_cats", cats_map)
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
                from category_commit import CategoryRepoLike
                repo_like = cast(CategoryRepoLike, repo)
            except Exception:
                repo_like = repo

            svc = CategoryCommitService(repo_like)
        except Exception:
            return None, None

        try:
            try:
                from typing import cast
                from category_commit import CategoryRepoLike
                self.dialog._cat_repo = cast(CategoryRepoLike, repo)
            except Exception:
                self.dialog._cat_repo = repo
            self.dialog._cat_commit_svc = svc
        except (TypeError, AttributeError, RuntimeError):
            pass

        # Debug
        try:
            cats_self = getattr(self.dialog, "_cats", None)
            cats_repo = getattr(repo, "_cats", None)
            logger.debug(
                "DBG[A] ensure_services: self._cats id=%s keys_n=%s | repo._cats id=%s keys_n=%s | same_obj=%s",
                (id(cats_self) if cats_self is not None else None),
                (len(cats_self) if isinstance(cats_self, dict) else None),
                (id(cats_repo) if cats_repo is not None else None),
                (len(cats_repo) if isinstance(cats_repo, dict) else None),
                bool(cats_self is cats_repo),
            )
        except Exception:
            pass

        return repo, svc

    def add_new_category(self, cat: str) -> bool:
        """Add a new category via the authoritative CategoryRepo (best-effort, never raise)."""
        try:
            cat_s = str(cat or "").strip()
        except Exception:
            cat_s = ""

        if not cat_s:
            return False

        # Prefer repo-based mutation
        repo = getattr(self.dialog, "_cat_repo", None)
        if repo is not None and hasattr(repo, "add"):
            try:
                logger.debug("_add_new_category: repo.add(%r) starting", str(cat_s or ""))
                ok = bool(repo.add(cat_s))
                logger.debug("_add_new_category: repo.add(%r) -> ok=%s", str(cat_s or ""), bool(ok))
            except Exception as e:
                ok = False
                logger.debug("_add_new_category: repo.add(%r) raised: %s", str(cat_s or ""), e)

            # Ensure UI dropdown contains it
            if ok:
                try:
                    w_cat = getattr(self.dialog, "_add_cat", None)
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

        # Fallback: minimal in-memory add
        try:
            cats_map = getattr(self.dialog, "_cats", None)
        except Exception:
            cats_map = None

        if not isinstance(cats_map, dict):
            return False

        try:
            canon = getattr(self.dialog, "_canon_cat_name", None)
            cat_key = str(canon(cat_s) if callable(canon) else cat_s).strip()
        except Exception:
            cat_key = cat_s

        if not cat_key:
            return False

        if cat_key not in cats_map:
            cats_map[cat_key] = []
        return True


    def do_category_commit_internal(self, user_action: bool = False) -> None:
        """Internal category commit handler (extracted from misnamed _build_add_entry_preview).

        This massive method handles the full category commitment workflow including
        UI confirmation, repo mutation, and UI effects. Should eventually be broken
        down further into smaller pieces.

        Args:
            user_action: Whether this commit was triggered by explicit user action
        """
        dialog = self._dialog

        # Guard against re-entrant / duplicate commits caused by QComboBox signal churn.
        try:
            if bool(getattr(dialog, "_in_cat_commit", False)):
                try:
                    logger.debug("Add/Edit category commit: re-entrant call suppressed")
                except Exception:
                    pass
                return
        except Exception:
            pass

        try:
            dialog._in_cat_commit = True
        except Exception:
            pass

        try:
            # 1) Read category text
            try:
                w_cat = getattr(dialog, "_add_cat", None)
            except (TypeError, AttributeError, RuntimeError):
                w_cat = None

            try:
                cat_raw = (w_cat.currentText() or "").strip() if w_cat is not None else ""
            except (TypeError, AttributeError, RuntimeError):
                cat_raw = ""

            if (not cat_raw) and (w_cat is not None):
                try:
                    le = w_cat.lineEdit() if hasattr(w_cat, "lineEdit") else None
                except (TypeError, AttributeError, RuntimeError):
                    le = None
                if le is not None:
                    try:
                        cat_raw = (le.text() or "").strip()
                    except (TypeError, AttributeError, RuntimeError):
                        cat_raw = cat_raw or ""

            if not cat_raw:
                try:
                    logger.debug(
                        "Add/Edit category commit: raw=%r user_action=%s",
                        str(cat_raw or ""),
                        bool(user_action),
                    )
                except (TypeError, AttributeError, RuntimeError):
                    pass

                try:
                    fn_gate = getattr(dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # 2) Jyutping present?
            try:
                w_jy = getattr(dialog, "_add_jy", None)
                jy = (w_jy.text() or "").strip() if w_jy is not None else ""
            except (TypeError, AttributeError, RuntimeError):
                jy = ""
            has_jy = bool(jy)

            # 3) Acquire repo + service (lazy init; UI-free). If unavailable, fail safe.
            try:
                repo, svc = self.ensure_category_services()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                repo, svc = None, None

            if repo is None or svc is None:
                try:
                    fn_gate = getattr(dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # UI-only helper: clear category input and refocus
            def _clear_and_refocus() -> None:
                try:
                    ctrl2 = getattr(dialog, "_cat_combo_ctrl", None)
                except (TypeError, AttributeError, RuntimeError):
                    ctrl2 = None

                if ctrl2 is not None and hasattr(ctrl2, "clear_and_refocus"):
                    try:
                        ctrl2.clear_and_refocus()
                        return
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        pass

                try:
                    w = getattr(dialog, "_add_cat", None)
                except (TypeError, AttributeError, RuntimeError):
                    w = None

                if w is not None:
                    try:
                        w.blockSignals(True)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

                    try:
                        le2 = w.lineEdit() if hasattr(w, "lineEdit") else None
                    except (TypeError, AttributeError, RuntimeError):
                        le2 = None

                    if le2 is not None:
                        try:
                            le2.clear()
                        except (TypeError, AttributeError, RuntimeError):
                            pass

                    try:
                        w.setCurrentIndex(-1)
                    except (TypeError, AttributeError, RuntimeError):
                        try:
                            w.setCurrentText("")
                        except (TypeError, AttributeError, RuntimeError):
                            pass

                    try:
                        w.blockSignals(False)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

                try:
                    dialog._focus_category(select_all=True, show_popup=True)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # 4) Determine confirmation only if unknown
            user_confirmed_add = False

            try:
                canon = repo.canon(cat_raw)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                canon = str(cat_raw or "").strip()

            try:
                exists_now = bool(canon) and bool(repo.exists(canon))
            except (TypeError, AttributeError, RuntimeError, ValueError):
                exists_now = False

            if not exists_now:
                # UI confirmation lives at the adapter boundary (tests monkeypatch QMessageBox.question).
                user_confirmed_add = False
                try:
                    from PySide6.QtWidgets import QMessageBox
                except (ImportError, ModuleNotFoundError):
                    QMessageBox = None

                if QMessageBox is not None:
                    try:
                        resp = QMessageBox.question(
                            dialog,
                            "Add category?",
                            "Add new category '{0}'?".format(str(canon or "")),
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.Yes,
                        )
                        user_confirmed_add = bool(resp == QMessageBox.StandardButton.Yes)
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        user_confirmed_add = False

            if (not exists_now) and (not bool(user_confirmed_add)):
                _clear_and_refocus()
                try:
                    fn_gate = getattr(dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # 5) Core commit (pure decision + repo mutation)
            try:
                res = svc.commit(
                    requested=canon,
                    has_jy=has_jy,
                    confirmed_add=bool(user_confirmed_add),
                )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                _clear_and_refocus()
                try:
                    fn_gate = getattr(dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            if not bool(getattr(res, "ok", False)):
                _clear_and_refocus()
                try:
                    fn_gate = getattr(dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            try:
                cat = str(getattr(res, "category", "") or "").strip()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                cat = ""

            if not cat:
                _clear_and_refocus()
                try:
                    fn_gate = getattr(dialog, "_update_save_enabled", None)
                    if callable(fn_gate):
                        fn_gate()
                except (TypeError, AttributeError, RuntimeError):
                    pass
                return

            # Regression guard: ensure authoritative in-memory map records brand-new categories.
            try:
                if (not bool(exists_now)) and bool(user_confirmed_add):
                    cats_map_auth = getattr(dialog, "_cats", None)
                    if isinstance(cats_map_auth, dict) and cat not in cats_map_auth:
                        cats_map_auth[cat] = []
            except Exception:
                pass

            try:
                if isinstance(getattr(dialog, "_cats", None), dict) and cat and (cat not in dialog._cats):
                    dialog._cats[cat] = []
            except (TypeError, AttributeError, RuntimeError):
                pass

            # ---- UI list sync (ensure new categories appear in the dropdown) ----
            try:
                all_cats = getattr(dialog, "_all_cats", None)
            except (TypeError, AttributeError, RuntimeError):
                all_cats = None

            try:
                if isinstance(all_cats, list) and cat and (cat not in all_cats):
                    all_cats.append(cat)
                    all_cats.sort(key=lambda s: str(s).lower())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            # Ensure the combobox model contains the category as an item (not just edit text).
            if w_cat is not None:
                try:
                    existing = []
                    try:
                        n = int(w_cat.count())
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        n = 0
                    for i in range(max(0, n)):
                        try:
                            t = str(w_cat.itemText(i) or "").strip()
                        except (TypeError, AttributeError, RuntimeError, ValueError):
                            t = ""
                        if t:
                            existing.append(t)

                    if cat and (cat not in existing):
                        # Rebuild items in sorted order (keeps list stable with InsertPolicy.NoInsert).
                        merged = sorted(set(existing + [cat]), key=lambda s: str(s).lower())
                        try:
                            w_cat.blockSignals(True)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                        try:
                            w_cat.clear()
                            w_cat.addItems(list(merged))
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                        try:
                            w_cat.setEditable(True)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                        try:
                            w_cat.blockSignals(False)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass

            # Debug: verify repo/_cats now contains the committed category
            try:
                cats_map_dbg = getattr(dialog, "_cats", None)
                in_cats = bool(isinstance(cats_map_dbg, dict) and cat in cats_map_dbg)
                # Safety: ensure the authoritative in-memory map reflects the committed category.
                if isinstance(cats_map_dbg, dict) and cat and (cat not in cats_map_dbg):
                    cats_map_dbg[cat] = []
                    in_cats = True
            except Exception:
                pass

            # 6) Apply success effects
            try:
                if w_cat is not None and hasattr(w_cat, "setCurrentText"):
                    w_cat.setCurrentText(cat)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # If we just created a new category, refresh the derived list + dropdown
            # from the authoritative map so it remains available after field clears.
            try:
                if not bool(exists_now):
                    dialog._refresh_category_dropdown_from_cats(selected=cat)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            try:
                ctx = getattr(dialog, "_add_edit_ctx", None)
            except (TypeError, AttributeError, RuntimeError):
                ctx = None

            try:
                cat_l = cat.lower()
                cat_ok = bool(cat) and cat_l not in ("unassigned", "all")
            except Exception:
                cat_ok = False

            if ctx is not None:
                try:
                    setattr(ctx, "category", cat)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                try:
                    setattr(ctx, "cat_ok", bool(cat_ok))
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Candidate fill should happen whenever we have Jyutping and a committed category.
            try:
                should_fill = bool(has_jy)
            except (TypeError, AttributeError, RuntimeError):
                should_fill = False

            if bool(should_fill):
                try:
                    fn_fill = getattr(dialog, "_fill_hanzi_candidates", None)
                except (TypeError, AttributeError, RuntimeError):
                    fn_fill = None

                if callable(fn_fill):
                    try:
                        fn_fill(jy, category=cat)
                    except TypeError:
                        try:
                            fn_fill(jy)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                    except (TypeError, AttributeError, RuntimeError):
                        pass

            try:
                fn_gate = getattr(dialog, "_update_save_enabled", None)
                if callable(fn_gate):
                    fn_gate()
            except (TypeError, AttributeError, RuntimeError):
                pass

            # 7) Focus advance
            try:
                combo = getattr(dialog, "_cand_combo", None)
            except (TypeError, AttributeError, RuntimeError):
                combo = None

            n_items = 0
            if combo is not None:
                try:
                    n_items = int(combo.count())
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    n_items = 0

            if n_items > 0:
                dialog._defer_focus("cand")
            else:
                dialog._defer_focus("hz")

        finally:
            try:
                dialog._in_cat_commit = False
            except Exception:
                pass

    def on_add_category_committed(self, *args, user_action: bool = False, **kwargs) -> None:
        """Commit the Add/Edit category selection.

        UI prompting for unknown categories is delegated to CategoryComboController.
        This method must remain best-effort and never raise.
        """
        # Guard against re-entrant commits
        try:
            if bool(getattr(self.dialog, "_in_cat_commit", False)):
                logger.debug("Add/Edit category commit: re-entrant call suppressed")
                return
        except Exception:
            pass

        try:
            self.dialog._in_cat_commit = True
        except Exception:
            pass

        try:
            # Read category text
            try:
                w_cat = getattr(self.dialog, "_add_cat", None)
            except (TypeError, AttributeError, RuntimeError):
                w_cat = None

            cat_raw = WidgetAccessor.get_text(w_cat)

            if not cat_raw and w_cat is not None:
                try:
                    le = w_cat.lineEdit() if hasattr(w_cat, "lineEdit") else None
                except (TypeError, AttributeError, RuntimeError):
                    le = None
                if le is not None:
                    cat_raw = WidgetAccessor.get_text(le)

            if not cat_raw:
                logger.debug("Add/Edit category commit: raw=%r user_action=%s", cat_raw, user_action)
                self._update_save_enabled()
                return

            # Jyutping present?
            try:
                w_jy = getattr(self.dialog, "_add_jy", None)
                jy = WidgetAccessor.get_text(w_jy)
            except (TypeError, AttributeError, RuntimeError):
                jy = ""
            has_jy = bool(jy)

            # Acquire repo + service
            try:
                repo, svc = self.ensure_category_services()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                repo, svc = None, None

            if repo is None or svc is None:
                self._update_save_enabled()
                return

            # Clear and refocus helper
            def _clear_and_refocus() -> None:
                try:
                    ctrl2 = getattr(self.dialog, "_cat_combo_ctrl", None)
                except (TypeError, AttributeError, RuntimeError):
                    ctrl2 = None

                if ctrl2 is not None and hasattr(ctrl2, "clear_and_refocus"):
                    try:
                        ctrl2.clear_and_refocus()
                        return
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        pass

                try:
                    w = getattr(self.dialog, "_add_cat", None)
                except (TypeError, AttributeError, RuntimeError):
                    w = None

                if w is not None:
                    with SignalBlocker(w):
                        try:
                            le2 = w.lineEdit() if hasattr(w, "lineEdit") else None
                        except (TypeError, AttributeError, RuntimeError):
                            le2 = None

                        if le2 is not None:
                            try:
                                le2.clear()
                            except (TypeError, AttributeError, RuntimeError):
                                pass

                        try:
                            w.setCurrentIndex(-1)
                        except (TypeError, AttributeError, RuntimeError):
                            try:
                                w.setCurrentText("")
                            except (TypeError, AttributeError, RuntimeError):
                                pass

                try:
                    self.dialog._focus_category(select_all=True, show_popup=True)
                except (TypeError, AttributeError, RuntimeError):
                    pass

            # Determine if unknown
            user_confirmed_add = False

            try:
                canon = repo.canon(cat_raw)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                canon = str(cat_raw or "").strip()

            logger.debug("DBG[B1] cat_commit: cat_raw=%r canon=%r user_action=%s", cat_raw, canon, user_action)

            try:
                exists_now = bool(canon) and bool(repo.exists(canon))
            except (TypeError, AttributeError, RuntimeError, ValueError):
                exists_now = False

            logger.debug("DBG[B2] cat_commit: exists_now=%s", exists_now)
            logger.debug("Add/Edit category commit: canon=%r exists_now=%s", canon, exists_now)

            if not exists_now:
                # UI confirmation
                user_confirmed_add = False
                try:
                    resp = QMessageBox.question(
                        self.dialog,
                        "Add category?",
                        f"Add new category '{canon}'?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )
                    user_confirmed_add = bool(resp == QMessageBox.StandardButton.Yes)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    user_confirmed_add = False

                logger.debug("Add/Edit category commit: unknown category confirmation -> confirmed=%s", user_confirmed_add)

            # Guard after confirmation
            if (not exists_now) and (not user_confirmed_add):
                _clear_and_refocus()
                self._update_save_enabled()
                return

            # Core commit
            logger.debug("Add/Edit category commit: calling svc.commit(requested=%r has_jy=%s confirmed_add=%s)", canon, has_jy, user_confirmed_add)

            # After category commit, if we have Jyutping, fill Hanzi candidates
            if has_jy:
                try:
                    jy_widget = getattr(self.dialog, "_add_jy", None)
                    if jy_widget is not None:
                        jy_text = jy_widget.text().strip()
                        if jy_text:
                            logger.debug("Category commit: triggering fill_hanzi_candidates jy=%r cat=%r", jy_text, canon)
                            if hasattr(self.dialog, "_fill_hanzi_candidates"):
                                self.dialog._fill_hanzi_candidates(jy_text, canon)
                            else:
                                logger.debug("Category commit: _fill_hanzi_candidates method not found on dialog")
                except (TypeError, AttributeError, RuntimeError) as e:
                    logger.debug("Category commit: failed to fill candidates: %s", e)
            try:
                res = self.dialog._cat_commit_svc.commit(
                    requested=canon,
                    has_jy=has_jy,
                    confirmed_add=bool(user_confirmed_add),
                )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                _clear_and_refocus()
                self._update_save_enabled()
                return

            # Debug
            try:
                cats_dbg = getattr(self.dialog, "_cats", None)
                ok_dbg = bool(getattr(res, "ok", False))
                cat_dbg = str(getattr(res, "category", "") or "").strip()
                logger.debug(
                    "DBG[B3] cat_commit: res.ok=%s res.category=%r self._cats_has=%s self._cats_n=%s",
                    ok_dbg,
                    cat_dbg,
                    bool(isinstance(cats_dbg, dict) and cat_dbg and (cat_dbg in cats_dbg)),
                    (len(cats_dbg) if isinstance(cats_dbg, dict) else None),
                )
            except Exception:
                pass

            logger.debug("Add/Edit category commit: svc result ok=%s category=%r should_fill=%s",
                        bool(getattr(res, "ok", False)),
                        str(getattr(res, "category", "") or ""),
                        bool(getattr(res, "should_fill_candidates", False)))

            if not bool(getattr(res, "ok", False)):
                _clear_and_refocus()
                self._update_save_enabled()
                return

            try:
                cat = str(getattr(res, "category", "") or "").strip()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                cat = ""

            if not cat:
                _clear_and_refocus()
                self._update_save_enabled()
                return

            # Regression guard: ensure authoritative map records new categories
            try:
                if (not exists_now) and user_confirmed_add:
                    cats_map_auth = getattr(self.dialog, "_cats", None)
                    if isinstance(cats_map_auth, dict) and cat not in cats_map_auth:
                        cats_map_auth[cat] = []
            except Exception:
                pass

            try:
                if isinstance(getattr(self.dialog, "_cats", None), dict) and cat and (cat not in self.dialog._cats):
                    self.dialog._cats[cat] = []
            except (TypeError, AttributeError, RuntimeError):
                pass

            # UI list sync
            try:
                all_cats = getattr(self.dialog, "_all_cats", None)
            except (TypeError, AttributeError, RuntimeError):
                all_cats = None

            try:
                if isinstance(all_cats, list) and cat and (cat not in all_cats):
                    all_cats.append(cat)
                    all_cats.sort(key=lambda s: str(s).lower())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            # Ensure combobox model contains category
            if w_cat is not None:
                try:
                    existing = []
                    try:
                        n = int(w_cat.count())
                    except (TypeError, AttributeError, RuntimeError, ValueError):
                        n = 0
                    for i in range(max(0, n)):
                        try:
                            t = str(w_cat.itemText(i) or "").strip()
                        except (TypeError, AttributeError, RuntimeError, ValueError):
                            t = ""
                        if t:
                            existing.append(t)

                    if cat and (cat not in existing):
                        merged = sorted(set(existing + [cat]), key=lambda s: str(s).lower())
                        with SignalBlocker(w_cat):
                            try:
                                w_cat.clear()
                                w_cat.addItems(list(merged))
                            except (TypeError, AttributeError, RuntimeError):
                                pass
                            try:
                                w_cat.setEditable(True)
                            except (TypeError, AttributeError, RuntimeError):
                                pass
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass

            # Debug: verify
            try:
                cats_map_dbg = getattr(self.dialog, "_cats", None)
                in_cats = bool(isinstance(cats_map_dbg, dict) and cat in cats_map_dbg)
                if isinstance(cats_map_dbg, dict) and cat and (cat not in cats_map_dbg):
                    cats_map_dbg[cat] = []
                    in_cats = True
                logger.debug("Add/Edit category commit: after commit cat=%r in _cats=%s cats_n=%s",
                            cat, in_cats, (len(cats_map_dbg) if isinstance(cats_map_dbg, dict) else "?"))
                if isinstance(cats_map_dbg, dict) and not in_cats:
                    logger.debug("Add/Edit category commit: _cats keys sample=%s", sorted(list(cats_map_dbg.keys()))[:30])
            except Exception:
                pass

            try:
                logger.debug("Add/Edit category commit: repo.exists(%r)=%s", cat,
                            bool(repo.exists(cat) if hasattr(repo, "exists") else False))
            except Exception:
                pass

            # Apply success effects
            try:
                if w_cat is not None and hasattr(w_cat, "setCurrentText"):
                    w_cat.setCurrentText(cat)
            except (TypeError, AttributeError, RuntimeError):
                pass

            # Refresh dropdown if new category
            try:
                if not exists_now:
                    self.refresh_category_dropdown_from_cats(selected=cat)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            # Update context
            try:
                ctx = getattr(self.dialog, "_add_edit_ctx", None)
            except (TypeError, AttributeError, RuntimeError):
                ctx = None

            try:
                cat_l = cat.lower()
                cat_ok = bool(cat) and cat_l not in ("unassigned", "all")
            except Exception:
                cat_ok = False

            if ctx is not None:
                try:
                    setattr(ctx, "category", cat)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                for _k, _v in (("cat_ok", bool(cat_ok)),):
                    try:
                        setattr(ctx, _k, _v)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

            # Candidate fill
            try:
                should_fill = bool(has_jy)
            except (TypeError, AttributeError, RuntimeError):
                should_fill = False

            if bool(should_fill):
                try:
                    fn_fill = getattr(self.dialog, "_fill_hanzi_candidates", None)
                except (TypeError, AttributeError, RuntimeError):
                    fn_fill = None

                if callable(fn_fill):
                    try:
                        fn_fill(jy, category=cat)
                    except TypeError:
                        try:
                            fn_fill(jy)
                        except (TypeError, AttributeError, RuntimeError):
                            pass
                    except (TypeError, AttributeError, RuntimeError):
                        pass

            self._update_save_enabled()

            # Focus advance
            try:
                combo = getattr(self.dialog, "_cand_combo", None)
            except (TypeError, AttributeError, RuntimeError):
                combo = None

            n_items = 0
            if combo is not None:
                try:
                    n_items = int(combo.count())
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    n_items = 0

            if n_items > 0:
                self.dialog._defer_focus("cand")
            else:
                self.dialog._defer_focus("hz")

        finally:
            try:
                self.dialog._in_cat_commit = False
            except Exception:
                pass

    def on_add_category_changed(self, *args, **kwargs) -> None:
        """Category text changed while typing.

        Do NOT treat this as a commit. Users must be able to type-to-select without triggering changes.
        """
        return

    def refresh_category_dropdown_from_cats(self, *, selected: str = "") -> None:
        """Refresh the Add/Edit category dropdown from authoritative in-memory map."""
        combo = None
        try:
            cats_map = getattr(self.dialog, "_cats", None)
        except (TypeError, AttributeError, RuntimeError):
            cats_map = None

        if not isinstance(cats_map, dict):
            return

        # Rebuild derived list
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
            self.dialog._all_cats = sorted(set(keys), key=lambda s: str(s).lower())
        except (TypeError, ValueError):
            try:
                self.dialog._all_cats = list(dict.fromkeys(keys))
            except (TypeError, ValueError):
                return

        # Repopulate combobox
        try:
            combo = getattr(self.dialog, "_add_cat", None)
        except (TypeError, AttributeError, RuntimeError):
            combo = None

        if combo is None or not hasattr(combo, "clear") or not hasattr(combo, "addItems"):
            return

        with SignalBlocker(combo):
            try:
                combo.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

            try:
                combo.addItems(self.dialog._all_cats)
            except (TypeError, AttributeError, RuntimeError):
                pass

        # Preserve selection
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

        try:
            combo.blockSignals(False)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _update_save_enabled(self) -> None:
        """Delegate to dialog's save gating."""
        try:
            fn = getattr(self.dialog, "_update_save_enabled", None)
            if callable(fn):
                fn()
        except (TypeError, AttributeError, RuntimeError):
            pass
