from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtWidgets import QComboBox, QLineEdit, QMessageBox

logger = logging.getLogger(__name__)


class CategoryComboController:
    """UI-only controller for the Add-panel Category combobox.

    Responsibilities:
      - Normalised read/write of category text
      - Focus/select-all/popup helpers
      - A single commit entry point (Enter)
      - UI prompt for adding a brand-new category (delegates actual add via callback)
    """

    def __init__(
        self,
        *,
        combo: QComboBox,
        on_commit: Callable[[], None] | None,
    ):
        self._combo = combo
        self._on_commit = on_commit
        self._last_commit_text: str | None = None

        # Must be editable to allow free-text entry.
        try:
            if hasattr(self._combo, "setEditable"):
                self._combo.setEditable(True)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            # Best-effort only; UI must remain responsive.
            pass

        # Wire Enter/Return on the editable line edit to commit.
        le = self._line_edit()
        if le is not None:
            try:
                sig = getattr(le, "returnPressed", None)
                if sig is not None:
                    sig.connect(self.commit)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

    def combo(self) -> QComboBox:
        return self._combo

    def line_edit(self) -> Optional[QLineEdit]:
        return self._line_edit()

    def current_text(self) -> str:
        try:
            return (self._combo.currentText() or "").strip()
        except (TypeError, AttributeError, RuntimeError):
            return ""

    def set_text(self, text: str) -> None:
        t = (text or "").strip()
        self._ensure_item_present(t)
        try:
            self._combo.setCurrentText(t)
            return
        except (TypeError, AttributeError, RuntimeError):
            pass
        try:
            self._combo.setEditText(t)
        except (TypeError, AttributeError, RuntimeError):
            pass

    def focus(self, *, select_all: bool = True, show_popup: bool = False) -> None:
        try:
            self._combo.setFocus()
        except (TypeError, AttributeError, RuntimeError):
            return

        le = self._line_edit()
        if le is not None:
            try:
                le.setFocus()
            except (TypeError, AttributeError, RuntimeError):
                pass
            if select_all:
                try:
                    le.selectAll()
                except (TypeError, AttributeError, RuntimeError):
                    pass

        if show_popup:
            try:
                self._combo.showPopup()
            except (TypeError, AttributeError, RuntimeError):
                pass

    def clear_and_refocus(self) -> None:
        """Clear the category combo and refocus.

        WARNING: This should NOT be called during normal Add flow.
        Only call this explicitly when resetting the entire form.
        """
        logger.debug("CATDBG: clear_and_refocus called (should only happen on explicit reset)")

        # If there's a committed category, don't clear it!
        # This prevents accidental clearing during the Add flow.
        if self._last_commit_text:
            logger.debug("CATDBG: Skipping clear - category already committed: %r", self._last_commit_text)
            return

        w = self._combo

        try:
            w.blockSignals(True)
        except (TypeError, AttributeError, RuntimeError):
            pass

        le = self._line_edit()
        if le is not None:
            try:
                le.clear()
            except (TypeError, AttributeError, RuntimeError):
                pass

        try:
            logger.debug("CATDBG: CategoryComboController clearing combo (setCurrentIndex(-1))")
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
            self._last_commit_text = None
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

        self.focus(select_all=True, show_popup=True)

    def commit(self) -> None:
        """Forward a category commit event to the dialog adapter.

        IMPORTANT:
            - This controller must NOT open confirmation dialogs.
            - This controller must NOT add/persist categories.

        The dialog adapter (category_manager.py) owns UI prompting + domain mutation
        via CategoryCommitService/CategoryRepo.
        """
        # De-bounce: avoid double commit firing from multiple Qt signals
        # (e.g., returnPressed + editingFinished).
        try:
            text = (self._combo.currentText() or "").strip()
        except (TypeError, AttributeError, RuntimeError, ValueError):
            text = ""

        try:
            last = getattr(self, "_last_commit_text", None)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            last = None

        if text and last == text:
            return

        try:
            self._last_commit_text = text
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

        try:
            fn = self._on_commit
        except (TypeError, AttributeError, RuntimeError):
            fn = None

        if callable(fn):
            try:
                fn(user_action=True)
            except TypeError:
                # Back-compat: older on_commit did not accept kwargs.
                try:
                    fn()
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

    def confirm_add_new_category(self, *, text: str | None = None) -> bool:
        """UI-only: ask whether to add a brand-new category. Does not mutate any maps."""
        cat = (text or self.current_text() or "").strip()
        if not cat:
            return False

        try:
            res = QMessageBox.question(
                self._combo,
                "Add new category?",
                "The category ‘{0}’ does not exist.\n\nAdd it now?".format(cat),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
        except (TypeError, AttributeError, RuntimeError):
            return False

        return bool(res == QMessageBox.StandardButton.Yes)

    def _ensure_item_present(self, text: str) -> None:
        """Ensure `text` exists as an item in the combo list (best-effort)."""
        t = (text or "").strip()
        if not t:
            return

        try:
            find = getattr(self._combo, "findText", None)
            add = getattr(self._combo, "addItem", None)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return

        if not callable(find) or not callable(add):
            return

        try:
            idx = int(find(t))
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return

        if idx >= 0:
            return

        try:
            add(t)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            return

    def _line_edit(self) -> Optional[QLineEdit]:
        try:
            return self._combo.lineEdit()
        except (TypeError, AttributeError, RuntimeError):
            return None
