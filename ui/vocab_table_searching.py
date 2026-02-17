"""Search field wiring for vocab table."""

from __future__ import annotations


def wire_search_field(search, on_text_changed) -> None:
    """Wire search field to handler and enable clear icon."""
    if search is None or not callable(on_text_changed):
        return
    try:
        search.setClearButtonEnabled(True)
    except Exception:
        pass
    try:
        search.textChanged.connect(on_text_changed)
    except Exception:
        pass
    try:
        sig = getattr(search, "returnPressed", None)
        if sig is not None and hasattr(sig, "connect"):
            sig.connect(lambda: on_text_changed(search.text()))
    except Exception:
        pass


__all__ = ["wire_search_field"]
