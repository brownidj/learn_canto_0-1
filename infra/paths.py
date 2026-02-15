

"""Centralised project path helpers.

This module defines a single, authoritative notion of the project root
and provides helpers for resolving data/, ui/, and other infrastructure
paths. No application code should compute paths from __file__ directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


# --- Project root resolution -------------------------------------------------

# We define project root as the directory that contains the `data/` folder.
# This makes path resolution robust regardless of how or where main.py is run.


def _resolve_project_root() -> Path:
    here = Path(__file__).resolve()

    # Walk upwards looking for a directory that contains `data/`
    for parent in (here.parent, *here.parents):
        try:
            if (parent / "data").is_dir():
                return parent
        except Exception:
            continue

    # Fallback: two levels up from this file (repo default layout)
    return here.parents[1]


_PROJECT_ROOT: Path = _resolve_project_root()


# --- Public helpers -----------------------------------------------------------


def project_root() -> Path:
    """Return the resolved project root directory."""
    return _PROJECT_ROOT


def data_dir() -> Path:
    """Return the data directory (<project_root>/data)."""
    return _PROJECT_ROOT / "data"


def ui_dir() -> Path:
    """Return the UI directory (<project_root>/ui)."""
    return _PROJECT_ROOT / "ui"


def infra_dir() -> Path:
    """Return the infra directory (<project_root>/infra)."""
    return _PROJECT_ROOT / "infra"


# --- Convenience joiners ------------------------------------------------------


def data_path(*parts: Iterable[str]) -> Path:
    """Join path parts under the data directory."""
    return data_dir().joinpath(*parts)


def ui_path(*parts: Iterable[str]) -> Path:
    """Join path parts under the UI directory."""
    return ui_dir().joinpath(*parts)


def infra_path(*parts: Iterable[str]) -> Path:
    """Join path parts under the infra directory."""
    return infra_dir().joinpath(*parts)


# --- Diagnostics --------------------------------------------------------------


def _debug_dump() -> str:
    """Return a short diagnostic string for logging/debugging."""
    return (
        f"project_root={_PROJECT_ROOT} | "
        f"data_dir={data_dir()} | "
        f"ui_dir={ui_dir()}"
    )