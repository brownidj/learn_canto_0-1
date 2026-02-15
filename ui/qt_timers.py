from __future__ import annotations


def call_later(fn, *, delay_ms: int = 0) -> None:
    """Best-effort defer to Qt event loop (no-op if Qt unavailable)."""
    try:
        from PySide6.QtCore import QTimer
    except (ImportError, TypeError):
        try:
            fn()
        except Exception:
            pass
        return

    try:
        QTimer.singleShot(int(delay_ms), fn)
    except Exception:
        try:
            fn()
        except Exception:
            pass
