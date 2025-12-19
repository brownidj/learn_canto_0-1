

import builtins
import importlib
import inspect
import sys
from pathlib import Path

import pytest


def _purge_module(name: str) -> None:
    """Remove a module and its submodules from sys.modules."""
    doomed = [m for m in list(sys.modules.keys()) if m == name or m.startswith(name + ".")]
    for m in doomed:
        try:
            del sys.modules[m]
        except Exception:
            pass


def _assert_no_qt_imported() -> None:
    qt_loaded = [
        m
        for m in sys.modules.keys()
        if m.startswith("PySide6")
        or m.startswith("PyQt6")
        or m.startswith("PyQt5")
        or m.startswith("PyQt")
    ]
    assert not qt_loaded, "Qt modules were imported unexpectedly: " + ", ".join(sorted(qt_loaded))


def test_domain_modules_import_without_qt_side_effects():
    """(1) Domain modules must stay UI-free: importing them must not import Qt."""

    # If Qt has already been imported in this interpreter, do NOT try to purge it.
    # Removing PySide6/PyQt modules from sys.modules after the C extensions have loaded
    # can destabilize the process (including segfaults) when Qt is imported again.
    qt_loaded = [
        m
        for m in sys.modules.keys()
        if m.startswith("PySide6") or m.startswith("PyQt")
    ]
    if qt_loaded:
        pytest.skip(
            "Qt already imported in this pytest session; cannot safely assert domain imports "
            "are Qt-free without a fresh interpreter"
        )

    _purge_module("domain.attestation")
    _purge_module("domain.jyutping_validation")

    importlib.import_module("domain.jyutping_validation")
    _assert_no_qt_imported()

    importlib.import_module("domain.attestation")
    _assert_no_qt_imported()


def test_attestation_import_does_not_touch_disk(monkeypatch):
    """(2) Importing domain.attestation must be lazy (no disk reads at import time).

    The attested cache may load on *first use* but should not build at import.
    """

    _purge_module("domain.attestation")

    qt_loaded = [
        m
        for m in sys.modules.keys()
        if m.startswith("PySide6") or m.startswith("PyQt")
    ]
    if qt_loaded:
        pytest.skip(
            "Qt already imported in this pytest session; run domain import laziness checks "
            "in a fresh interpreter"
        )

    def called_from_attestation() -> bool:
        try:
            # Walk a few frames; avoid expensive full stack in normal cases.
            for frameinfo in inspect.stack()[1:12]:
                filename = str(frameinfo.filename)
                # Match both local checkout and packaged layouts.
                if filename.replace("\\", "/").endswith("/domain/attestation.py"):
                    return True
        except Exception:
            return False
        return False

    real_open = builtins.open

    def guarded_open(*args, **kwargs):
        if called_from_attestation():
            raise AssertionError("domain.attestation performed file I/O during import via builtins.open")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    # Guard common pathlib entry points used for reading resources.
    real_path_open = Path.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def guarded_path_open(self, *args, **kwargs):
        if called_from_attestation():
            raise AssertionError("domain.attestation performed file I/O during import via Path.open")
        return real_path_open(self, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        if called_from_attestation():
            raise AssertionError("domain.attestation performed file I/O during import via Path.read_text")
        return real_read_text(self, *args, **kwargs)

    def guarded_read_bytes(self, *args, **kwargs):
        if called_from_attestation():
            raise AssertionError("domain.attestation performed file I/O during import via Path.read_bytes")
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    # Import must succeed without any disk touches from domain.attestation itself.
    importlib.import_module("domain.attestation")

    # Sanity: still must remain UI-free.
    _assert_no_qt_imported()

def test_meaning_facade_candidate_label_filters_brackets_and_parens():
    """Regression: UI used to prefer meanings without '[' or '(' when building labels."""
    from domain.meaning_sources import MeaningFacade

    class _R:
        def meanings_for(self, _hz: str):
            return [
                "bad [1]",
                "nice",
                "meh (alt)",
                "fine",
            ]

    mf = MeaningFacade(resolver=_R(), cleaner=None)
    label = mf.candidate_label("測", "pipeline", preferred=False, max_items=2)

    assert "nice" in label
    assert "fine" in label
    assert "bad [1]" not in label
    assert "meh (alt)" not in label


def test_meaning_facade_candidate_label_falls_back_when_all_filtered():
    """If everything contains '['/'(', fall back to showing something rather than blank."""
    from domain.meaning_sources import MeaningFacade

    class _R:
        def meanings_for(self, _hz: str):
            return [
                "one [x]",
                "two (y)",
            ]

    mf = MeaningFacade(resolver=_R(), cleaner=None)
    label = mf.candidate_label("試", "pipeline", preferred=False, max_items=2)

    assert "試" in label
    assert label.strip() != ""

def test_meaning_facade_candidate_label_filters_brackets_and_parentheses():
    from domain.meaning_sources import MeaningFacade

    class _R:
        def meanings_for(self, hz):
            return ["alpha [x]", "beta (y)", "gamma", "delta"]

    f = MeaningFacade(resolver=_R(), cleaner=None)
    label = f.candidate_label("測", "pipeline", preferred=False, max_items=2)

    assert "測" in label
    # Ensure bracket/paren-bearing gloss entries are excluded (but the source tag uses parentheses).
    assert "alpha [x]" not in label
    assert "beta (y)" not in label
    assert "gamma" in label
    assert "delta" in label


def test_meaning_facade_select_candidate_returns_full_meanings_list():
    from domain.meaning_sources import MeaningFacade

    class _R:
        def meanings_for(self, hz):
            return ["alpha [x]", "beta (y)", "gamma"]

    f = MeaningFacade(resolver=_R(), cleaner=None)
    sel = f.select_candidate("測", "pipeline", preferred=False, max_items=2)

    assert sel.hanzi == "測"
    assert sel.source == "pipeline"
    # meanings list is the full display list (not the preview slice)
    assert len(sel.meanings) == 3
    assert sel.meanings[0].startswith("alpha")
    assert "gamma" in sel.label