from __future__ import annotations

from typing import Callable

from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_ui_services import CategoryManagerUIService


class MeaningResolverService:
    """Small dependency wrapper for meaning resolution."""

    def __init__(
        self,
        *,
        get_facade: Callable[[], object | None],
        get_vocab_service: Callable[[], object | None],
        get_jyutping_text: Callable[[], str],
    ) -> None:
        self._get_facade = get_facade
        self._get_vocab_service = get_vocab_service
        self._get_jyutping_text = get_jyutping_text

    def facade(self) -> object | None:
        try:
            return self._get_facade()
        except Exception:
            return None

    def vocab_service(self) -> object | None:
        try:
            return self._get_vocab_service()
        except Exception:
            return None

    def jyutping_text(self) -> str:
        try:
            return str(self._get_jyutping_text() or "").strip()
        except Exception:
            return ""


def build_meaning_resolver_service(dialog) -> MeaningResolverService:
    dlg = CategoryManagerDialogAdapter(dialog)

    def _get_facade():
        return dlg.get("_meaning_facade")

    def _get_vocab_service():
        return dlg.get("_vocab_service")

    def _get_jyutping_text() -> str:
        try:
            ui = CategoryManagerUIService(dlg)
            return str(ui.get_text("add_jy") or "").strip()
        except Exception:
            return ""

    return MeaningResolverService(
        get_facade=_get_facade,
        get_vocab_service=_get_vocab_service,
        get_jyutping_text=_get_jyutping_text,
    )
