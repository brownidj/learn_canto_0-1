"""
Cantonese meaning controller.

Isolates cache/network lookup and UI application for colloquial meanings.
"""

import threading

from ui.ui_services import get_text, set_text

try:
    from PySide6.QtCore import QObject, Slot
except Exception:  # pragma: no cover - optional in non-Qt test contexts
    QObject = object
    def Slot(*_a, **_k):  # type: ignore
        def _wrap(fn):
            return fn
        return _wrap

class CantoneseMeaningController(QObject):
    """Cache-first Cantonese meaning lookup and UI application."""

    def __init__(self, dialog, service=None):
        super().__init__()
        self.dialog = dialog
        self._service = service
        self._inflight = set()
        self._pending = None

    def set_service(self, service) -> None:
        """Swap the backing CantoneseLanguageService (tests can stub this)."""
        self._service = service

    def request(self, *, hanzi: str, jyutping: str = "") -> None:
        """Fetch Cantonese info and apply meaning if still empty."""
        svc = self._service
        if svc is None:
            self._set_notes("Cantonese service unavailable")
            return

        hz = str(hanzi or "").strip()
        jy = str(jyutping or "").strip()
        if not hz:
            return

        key = "hz:" + hz if hz else "jy:" + jy
        if key in self._inflight:
            return
        self._inflight.add(key)

        # Cache-first lookup
        try:
            cached = svc.get_cached(hanzi=hz, jyutping=jy) if hasattr(svc, "get_cached") else None
        except Exception:
            cached = None
        if cached is not None and str(getattr(cached, "meaning_colloquial", "") or "").strip():
            # Apply immediately for cached results to avoid UI timing flakiness.
            self._pending = (hz, key, cached.meaning_colloquial)
            self._apply_pending()
            return

        # Surface status in Notes while fetching.
        self._set_notes("Fetching colloquial meaning… please wait")

        def _worker() -> None:
            info = None
            try:
                info = svc.lookup(hanzi=hz, jyutping=jy)
            except Exception:
                info = None

            if info is None:
                self._schedule_clear_notes()
                self._inflight.discard(key)
                return

            self._schedule_apply(hz, key, info.meaning_colloquial or "")

        threading.Thread(target=_worker, daemon=True).start()

    def apply_cached_if_available(self, *, hanzi: str, jyutping: str = "") -> bool:
        """Apply cached meaning synchronously if present. Returns True if applied."""
        svc = self._service
        if svc is None:
            return False
        hz = str(hanzi or "").strip()
        jy = str(jyutping or "").strip()
        if not hz:
            return False
        try:
            cached = svc.get_cached(hanzi=hz, jyutping=jy) if hasattr(svc, "get_cached") else None
        except Exception:
            cached = None
        if cached is None:
            return False
        meaning = str(getattr(cached, "meaning_colloquial", "") or "").strip()
        if not meaning:
            return False
        key = "hz:" + hz if hz else "jy:" + jy
        # Apply directly to avoid timing issues; respect hanzi match + empty meaning.
        try:
            w_mn = getattr(self.dialog, "_add_mn", None)
        except Exception:
            w_mn = None
        try:
            w_hz = getattr(self.dialog, "_add_hz", None)
        except Exception:
            w_hz = None
        if w_mn is None:
            return False
        try:
            current_hz = get_text(w_hz) if w_hz is not None else ""
        except Exception:
            current_hz = ""
        if current_hz and current_hz != hz:
            return False
        try:
            current_mn = get_text(w_mn)
        except Exception:
            current_mn = ""
        if current_mn:
            return False
        set_text(w_mn, meaning)
        self._pending = (hz, key, meaning)
        return True

    def set_pending(self, *, hanzi: str, key: str, meaning: str) -> None:
        """Set a pending result (test helper)."""
        self._pending = (hanzi, key, meaning)

    def apply_pending(self) -> None:
        """Apply the most recent pending result on the UI thread."""
        try:
            self._apply_pending()
        except Exception:
            pass

    def _schedule_apply(self, hz: str, key: str, meaning: str) -> None:
        self._pending = (hz, key, meaning)
        try:
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_apply_pending", Qt.ConnectionType.QueuedConnection)
            return
        except Exception:
            pass
        from ui.qt_timers import call_later
        call_later(self._apply_pending, delay_ms=0)

    def _schedule_clear_notes(self) -> None:
        def _clear() -> None:
            self._set_notes("")
        from ui.qt_timers import call_later
        call_later(_clear, delay_ms=0)

    def _set_notes(self, text: str) -> None:
        try:
            fn_notes = getattr(self.dialog, "_set_notes", None)
            if callable(fn_notes):
                fn_notes(text, source="canto-service")
        except Exception:
            pass

    @Slot()
    def _apply_pending(self) -> None:
        pending = self._pending
        if not pending or not isinstance(pending, tuple) or len(pending) != 3:
            return

        hz, key, meaning_raw = pending
        meaning = str(meaning_raw or "").strip()

        w_mn = getattr(self.dialog, "_add_mn", None)
        if w_mn is None:
            return

        w_hz = getattr(self.dialog, "_add_hz", None)
        if w_hz is not None:
            try:
                current_hz = get_text(w_hz)
            except Exception:
                current_hz = ""
            if current_hz and current_hz != hz:
                self._set_notes("")
                return

        current = get_text(w_mn)
        if current:
            self._set_notes("")
            self._inflight.discard(key)
            return

        if not meaning:
            self._set_notes("")
            self._inflight.discard(key)
            return

        set_text(w_mn, meaning)
        self._set_notes("")
        self._inflight.discard(key)
