from __future__ import annotations


class CategoryManagerVocabSearch:
    """Search filter handling for vocab table."""

    @staticmethod
    def on_search_changed(dialog, text: str) -> None:
        vocab_table_ctrl = getattr(dialog, "_vocab_table_ctrl", None)
        if vocab_table_ctrl is not None:
            try:
                vocab_table_ctrl.set_search_filter(text)
            except (TypeError, AttributeError, RuntimeError):
                pass
