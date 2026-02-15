from __future__ import annotations

from ui.category_manager_helpers import CategoryManagerHelpers
from ui.category_manager_widgets import resolve_category_manager_widgets


def wire_add_edit(wiring, fn_gate) -> None:
    widgets = resolve_category_manager_widgets(wiring._dlg)
    w_jy = widgets.get("add_jy")
    w_mn = widgets.get("add_mn")
    w_cat = widgets.get("add_cat")
    w_hz = widgets.get("add_hz")
    combo = widgets.get("cand_combo")

    # Jyutping
    fn_jy_enter = None
    try:
        coord = getattr(wiring, "_coord", None)
        if coord is not None and hasattr(coord, "on_jyut_enter"):
            fn_jy_enter = coord.on_jyut_enter
    except (TypeError, AttributeError, RuntimeError):
        fn_jy_enter = None
    wiring._wire_line_edit_common(w_jy, on_enter=fn_jy_enter, on_change=fn_gate)

    fn_reset = None
    try:
        fn_reset = lambda *args, **kwargs: CategoryManagerHelpers.on_add_jy_user_edited(
            wiring.dialog, *args, **kwargs
        )
    except Exception:
        fn_reset = None
    if w_jy is not None and callable(fn_reset):
        wiring._try_connect(getattr(w_jy, "textEdited", None), fn_reset)

    fn_jy_done = None
    try:
        fn_jy_done = lambda *args, **kwargs: CategoryManagerHelpers.on_add_jy_editing_finished(
            wiring.dialog, *args, **kwargs
        )
    except Exception:
        fn_jy_done = None
    if w_jy is not None and callable(fn_jy_done):
        wiring._try_connect(getattr(w_jy, "editingFinished", None), fn_jy_done)

    # Meaning
    fn_mn_enter = None
    try:
        coord = getattr(wiring, "_coord", None)
        if coord is not None and hasattr(coord, "on_meaning_enter"):
            fn_mn_enter = coord.on_meaning_enter
    except (TypeError, AttributeError, RuntimeError):
        fn_mn_enter = None
    wiring._wire_line_edit_common(w_mn, on_enter=fn_mn_enter, on_change=fn_gate)

    # Category
    if w_cat is not None and hasattr(w_cat, "setEditable"):
        try:
            w_cat.setEditable(True)
        except (TypeError, AttributeError, RuntimeError):
            pass
    wiring._wire_combo_common(w_cat, on_change=fn_gate)

    fn_cat_commit = None
    try:
        ops = wiring._dlg.get("_category_ops")
        if ops is not None and hasattr(ops, "on_add_category_committed"):
            fn_cat_commit = ops.on_add_category_committed
    except (TypeError, AttributeError, RuntimeError):
        fn_cat_commit = None
    if w_cat is not None and callable(fn_cat_commit):
        sig = getattr(w_cat, "activated", None)
        if sig is not None:
            try:
                sig_int = sig[int] if hasattr(sig, "__getitem__") else sig
                wiring._try_connect(sig_int, fn_cat_commit)
            except Exception:
                wiring._try_connect(sig, fn_cat_commit)

    # Hanzi
    if w_hz is not None:
        try:
            w_hz.setReadOnly(False)
        except (TypeError, AttributeError, RuntimeError):
            pass

        def _on_hanzi_enter() -> None:
            try:
                try:
                    hz_text = str(w_hz.text() or "").strip()
                except Exception:
                    hz_text = ""
                if not hz_text:
                    return
                coord = getattr(wiring, "_coord", None)
                if coord is not None and hasattr(coord, "on_hanzi_enter"):
                    coord.on_hanzi_enter(hz_text)
                if callable(fn_gate):
                    fn_gate()
            except Exception:
                fn_log = getattr(wiring, "_log_handler_error", None)
                if callable(fn_log):
                    fn_log("Hanzi enter handler failed")

        wiring._try_connect(getattr(w_hz, "returnPressed", None), _on_hanzi_enter)

    # Candidates
    if combo is not None:
        def _on_candidate_selected(index: int) -> None:
            try:
                try:
                    idx = int(index)
                except Exception:
                    idx = -1
                if idx < 0:
                    return
                coord = getattr(wiring, "_coord", None)
                if coord is not None and hasattr(coord, "on_candidate_selected"):
                    coord.on_candidate_selected(idx)
                else:
                    try:
                        hanzi_text = str(combo.itemText(idx) or "").strip()
                    except Exception:
                        hanzi_text = ""
                    if not hanzi_text or hanzi_text.startswith("—"):
                        return

                    hz_widget = widgets.get("add_hz")
                    if hz_widget is not None and hasattr(hz_widget, "setText"):
                        try:
                            hz_widget.setText(hanzi_text)
                        except Exception:
                            pass

                    if hasattr(wiring, "_resolve_meanings_for_combo") and hasattr(wiring, "_apply_meaning_text"):
                        meanings, joined = wiring._resolve_meanings_for_combo(
                            hanzi_text, combo, idx_override=idx
                        )
                        w_mn_local = widgets.get("add_mn")
                        wiring._apply_meaning_text(w_mn_local, joined)
                if callable(fn_gate):
                    fn_gate()

            except Exception:
                fn_log = getattr(wiring, "_log_handler_error", None)
                if callable(fn_log):
                    fn_log("Candidate selection handler failed")

        sig_activated = getattr(combo, "activated", None)
        if sig_activated is not None:
            try:
                sig_int = sig_activated[int] if hasattr(sig_activated, "__getitem__") else sig_activated
                wiring._try_connect(sig_int, _on_candidate_selected)
            except Exception:
                wiring._try_connect(sig_activated, _on_candidate_selected)


def wire_basic(wiring, fn_gate) -> None:
    wire_add_edit(wiring, fn_gate)
