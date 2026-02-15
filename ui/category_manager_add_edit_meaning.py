from __future__ import annotations

from ui.category_manager_meaning_resolver import CategoryManagerMeaningResolver
from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter


def resolve_meaning_for_add_edit(
    dialog_or_adapter,
    *,
    hanzi: str,
    src: str,
    jyutping: str,
    allow_canto: bool,
) -> tuple[str, str]:
    """Resolve meaning for Add/Edit flow in a single place."""
    dlg = dialog_or_adapter
    if not isinstance(dlg, CategoryManagerDialogAdapter):
        dlg = CategoryManagerDialogAdapter(dialog_or_adapter)

    resolver = dlg.get("_meaning_resolver")
    if isinstance(resolver, CategoryManagerMeaningResolver):
        return resolver.resolve_for_add_edit(
            hanzi=hanzi,
            src=src,
            jyutping=jyutping,
            allow_canto=allow_canto,
        )

    # Fallback: build a resolver on the fly if not attached.
    return CategoryManagerMeaningResolver(dlg.dialog).resolve_for_add_edit(
        hanzi=hanzi,
        src=src,
        jyutping=jyutping,
        allow_canto=allow_canto,
    )
