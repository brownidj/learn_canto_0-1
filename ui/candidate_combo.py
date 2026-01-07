from __future__ import annotations

from typing import Iterable, Tuple, Optional

try:
    from PySide6.QtWidgets import QComboBox
except Exception:  # pragma: no cover
    QComboBox = None  # type: ignore


HanziCandidate = Tuple[str, str, int]


class CandidateComboController:
    """
    UI-only controller for the Hanzi candidate QComboBox.

    Responsibilities:
      - Populate candidates
      - Clear/hide safely
      - Show and focus when appropriate

    This class contains NO domain logic and NO state-machine logic.
    """

    def __init__(self, combo: Optional[QComboBox]) -> None:
        self._combo = combo

    # ------------------------------------------------------------------
    # Basic guards
    # ------------------------------------------------------------------

    def _is_ready(self) -> bool:
        return self._combo is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear and hide the combo safely."""
        if not self._is_ready():
            return

        combo = self._combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.setVisible(False)
        finally:
            combo.blockSignals(False)

    def populate(self, candidates: Iterable[HanziCandidate]) -> int:
        """
        Populate the combo with candidates.

        Returns the number of candidates added.
        """
        if not self._is_ready():
            return 0

        combo = self._combo
        combo.blockSignals(True)
        try:
            combo.clear()

            count = 0
            for hz, src, freq in candidates:
                # Display text: just Hanzi; metadata stored as itemData
                combo.addItem(hz, (hz, src))
                count += 1

            combo.setVisible(count > 0)
            return count
        finally:
            combo.blockSignals(False)

    def has_candidates(self) -> bool:
        if not self._is_ready():
            return False
        return self._combo.count() > 0

    def show_and_focus(self) -> None:
        """Make the combo visible, popup, and focus it."""
        if not self._is_ready():
            return

        combo = self._combo
        combo.setVisible(True)
        try:
            combo.showPopup()
        except Exception:
            pass
        combo.setFocus()