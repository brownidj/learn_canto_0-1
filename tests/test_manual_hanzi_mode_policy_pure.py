"""domain/manual_hanzi_mode.py

Pure (UI-free) policy for deciding when the Add/Edit dialog should enter
"manual Hanzi mode".

This module must not import any Qt/UI code.
"""


class ManualHanziModePolicy:
    """UI-free policy decisions for manual Hanzi entry."""

    @staticmethod
    def should_enter_manual_mode(*, hanzi_is_read_only: bool, candidates_count: int) -> bool:
        """Return True when the dialog should switch to manual Hanzi mode.

        Contract:
          - If Hanzi is read-only AND there are zero candidates, enter manual mode.
          - Otherwise, do not force manual mode.

        Args:
            hanzi_is_read_only: Whether the Hanzi field is currently read-only.
            candidates_count: Number of candidate Hanzi entries available.

        Returns:
            bool
        """
        try:
            n = int(candidates_count)
        except Exception:
            n = 0

        return bool(hanzi_is_read_only) and n <= 0