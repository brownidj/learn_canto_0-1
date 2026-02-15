from __future__ import annotations


class CategoryManagerVocabTable:
    """Table refresh handling for vocab display."""

    @staticmethod
    def refresh_table(dialog) -> None:
        vocab_table_ctrl = getattr(dialog, "_vocab_table_ctrl", None)
        if vocab_table_ctrl is not None:
            try:
                vocab_table_ctrl.refresh_from_data()
            except (TypeError, AttributeError, RuntimeError):
                pass
        else:
            try:
                fn = getattr(dialog, "_rebuild_items_model", None)
                if callable(fn):
                    fn()
            except (TypeError, AttributeError, RuntimeError):
                pass
