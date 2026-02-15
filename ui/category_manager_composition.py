from __future__ import annotations


class CategoryManagerComposition:
    """Composition root for CategoryManagerDialog controllers."""

    def __init__(self, dialog):
        self._dlg = dialog

    def build(self) -> None:
        dlg = self._dlg

        from ui.category_manager_vocab_display import on_search_changed
        dlg._on_search_changed = lambda text: on_search_changed(dlg, text)

        from ui.category_manager_initializer import CategoryManagerInitializer
        dlg._initializer = CategoryManagerInitializer(dlg)

        from ui.category_manager_focus import CategoryManagerFocusController
        dlg._focus_ctrl = CategoryManagerFocusController(dlg)

        from ui.category_manager_typography import CategoryManagerTypographyController
        dlg._typography_ctrl = CategoryManagerTypographyController(dlg)

        from ui.category_manager_add_edit_flow import CategoryManagerAddEditFlowController
        dlg._add_edit_flow = CategoryManagerAddEditFlowController(dlg)

        from ui.category_manager_meaning_resolver import CategoryManagerMeaningResolver
        from ui.category_manager_meaning_resolver_service import build_meaning_resolver_service
        dlg._meaning_resolver_service = build_meaning_resolver_service(dlg)
        dlg._meaning_resolver = CategoryManagerMeaningResolver(
            dlg, service=dlg._meaning_resolver_service
        )

        from ui.category_manager_category_ops import CategoryManagerCategoryOpsController
        dlg._category_ops = CategoryManagerCategoryOpsController(dlg)

        from ui.category_manager_candidate_pipeline import CategoryManagerCandidatePipeline
        dlg._candidate_pipeline = CategoryManagerCandidatePipeline(dlg)

        from ui.category_manager_manual_hanzi import CategoryManagerManualHanziController
        dlg._manual_hanzi = CategoryManagerManualHanziController(dlg)

        from ui.category_manager_field_reset import CategoryManagerFieldResetController
        dlg._field_reset = CategoryManagerFieldResetController(dlg)

        from ui.category_manager_save_commit import CategoryManagerSaveCommitController
        dlg._save_commit = CategoryManagerSaveCommitController(dlg)

        from ui.category_manager_preview_confirm import CategoryManagerPreviewConfirmController
        dlg._preview_confirm = CategoryManagerPreviewConfirmController(dlg)

        from ui.category_manager_add_edit_state_service import AddEditStateService
        from ui.category_manager_add_edit_state_coordinator import AddEditStateCoordinator
        dlg._state_svc = AddEditStateService(dlg)
        dlg._state_coord = AddEditStateCoordinator(dlg)

    def build_ui(self) -> None:
        from ui.category_manager_ui_builder import CategoryManagerUIBuilder

        CategoryManagerUIBuilder(self._dlg).build_ui()

    def wire_signals(self) -> None:
        from ui.category_manager_signal_wiring import CategoryManagerSignalWiring

        CategoryManagerSignalWiring(self._dlg).wire_add_edit_signals()
