# CategoryManagerDialog Architecture

## Overview

The CategoryManagerDialog has been refactored from a monolithic 4488-line file into a modular architecture with specialized controllers, achieving a reduction to ~525 lines in the dialog.

## Design Principles

1. **Single Responsibility**: Each controller handles one cohesive concern
2. **Thin Coordinator**: The main dialog delegates all logic to controllers
3. **Best-Effort UI**: All UI operations are defensive and never raise exceptions
4. **State Management**: Centralized via `AddEditContext` and controller coordination
5. **Testability**: Controllers are independently testable with minimal Qt dependencies

## Controller Responsibilities

### Data & Initialization
- **CategoryManagerInitializer**: Loads and caches vocab, categories, and pipeline data
- **CategoryManagerComposition**: Composition root that constructs controllers and delegates UI build + signal wiring

### UI Controllers
- **CategoryManagerUIBuilder**: Constructs widgets and layouts
- **CategoryManagerSignalWiring**: Connects Qt signals directly to controllers
- **CategoryManagerTypographyController**: Fonts and typography
- **CategoryManagerVocabDisplay**: Table display + refresh
- **CategoryManagerVocabCategories**: Category dropdown refresh for vocab display
- **CategoryManagerVocabSearch**: Search filter handling for vocab display
- **CategoryManagerVocabTable**: Table refresh handling for vocab display
- **CategoryManagerFieldResetController**: Field clearing and reset operations
- **FieldResetEffects**: Applies UI + state reset actions for a reset plan
- **FieldResetWidgets**: Widget-only reset helpers
- **FieldResetState**: State/VM reset helpers
- **CategoryComboController** (`ui/category_combo.py`): Category combo UI, including add‑new confirmation + optional add callback
- **CategoryComboAddController** (`ui/category_combo_add.py`): Orchestrates confirm + add (keeps mutation out of combo UI)
- **CategoryManagerUIService**: Centralized UI actions + widget access

### Workflow Controllers
- **CategoryManagerAddEditFlowController**: Orchestrates the Add/Edit workflow (Jyutping → Category → Hanzi → Meanings → Save)
- **AddEditJyutpingHandler**: Jyutping validation + duplicate checks
- **AddEditCategoryHandler**: Candidate population + selection path
- **AddEditMeaningHandler**: Meaning commit + preview confirmation
- **AddEditUIActions**: UI actions used by Add/Edit handlers (preview, focus, reset, commit)
- **AddEditMeaningApplyService**: Meaning resolution + UI/state application
- **AddEditCandidateListService**: Candidate list population and initial selection
- **AddEditCandidateSelectionService**: Candidate selection + meaning application
- **CategoryManagerFocusController**: Focus management and focus policy enforcement
- **CategoryManagerFocusService**: Unified focus policy + effects
- **CategoryManagerManualHanziController**: Manual Hanzi entry mode
- **AddEditStateCoordinator**: ViewModel sync + save gating (derivation + reactions)

### Domain Adapters
- **CategoryManagerMeaningResolver**: Adapts MeaningFacade for UI needs
- **MeaningResolverService**: Small dependency wrapper (facade/vocab/jyutping getter)
- **CategoryManagerCategoryOpsController**: Category CRUD operations + UI side effects
- **CategoryOpsCommitLogic**: Category commit decisions + state updates (no widget effects)
- **CategoryCommitFlow** (`ui/category_manager_category_commit_flow.py`): Pure category-commit decision logic (no Qt)
- **CategoryOpsServices** (`ui/category_manager_category_ops_services.py`): Service wiring + category add
- **CategoryOpsUI** (`ui/category_manager_category_ops_ui.py`): UI helpers for commit side effects and widget access
- **CategoryOpsComboEffects**: Category combo refresh + selection effects
- **CategoryOpsFocusEffects**: Focus + popup effects for category ops
- **CategoryOpsCommitEffects**: Commit-side UI effects (clear/refocus, fill candidates, gating)
- **CandidateProvider** (`domain/candidate_provider.py`): Candidate lookup interface

### Save/Commit
- **CategoryManagerSaveCommitController**: Save orchestration and persistence
- **CategoryManagerPreviewConfirmController**: Entry preview and confirmation dialogs

### Utilities
- **CategoryManagerHelpers**: Standalone utility functions (perf timing, field readers)
- **CategoryManagerConstants**: UI-only constants (tooltips, labels)

## Key Workflows

### Add Workflow
1. User types Jyutping → `AddEditFlowController.on_jyut_enter()`
2. Jyutping validated → Focus moves to Category
3. User selects Category → `CategoryOpsController.on_add_category_committed()`
4. Category commit decision → `CategoryCommitFlow.decide_category_commit(...)` (pure decision)
5. If new category, `CategoryComboController` prompts and optionally adds via callback
6. Category committed → `AddEditFlowController.fill_hanzi_candidates()` (via `CandidateProvider`)
5. User selects Hanzi → `MeaningResolver` autofills meanings
6. User reviews/edits meanings → Save enabled
7. User presses Save → `SaveCommitController.save_add_item()`
8. Entry persisted → Table refreshed

### Edit Workflow
- Select table row → Fields populated in Add/Edit panel
- Modify any field → Same validation/save path as Add workflow
- Live category changes in table → Autosave + resort

## State Management

### AddEditContext
Centralized state for Add/Edit panel:
- `jy`, `jy_ok`: Jyutping and validation status
- `hanzi`, `hz_ok`: Hanzi and validation status
- `meaning`, `mn_ok`: Meaning and validation status
- `category`, `cat_ok`: Category and validation status
- `manual_hanzi`: Manual entry mode flag
- `duplicate`: Duplicate detection result
- `saving`: Save in progress flag

### AddEditState
State machine states:
- `EMPTY`: Initial state
- `JY_COMMITTED`: Jyutping validated
- `CATEGORY_COMMITTED`: Category selected
- `HANZI_COMMITTED`: Hanzi confirmed
- `READY_TO_SAVE`: All fields valid

## Meaning Resolution

**Single Resolver Rule**: All meaning resolution flows through:
1. `MeaningFacade.select_candidate(hanzi, source)` (authoritative)
2. `MeaningFacade.meanings_for_display(hanzi)` (fallback)

The UI **must never**:
- Call pipeline gloss resolvers directly
- Call CCCanto/CEDICT helpers directly
- Clean or filter glosses itself

This ensures consistent, testable meaning resolution across all UI contexts.

## Testing Strategy

- **Pure controllers**: Test without Qt (e.g., `test_category_manager_*_pure.py`)
- **UI integration**: Test with QApplication (e.g., `test_category_manager_add_new_category_ui.py`)
- **Golden tests**: Candidate ranking regression tests
- **State machine**: State transition tests

## Refactoring Progress

| Phase | Lines | Reduction |
|-------|-------|-----------|
| Original | 4488 | - |
| Current dialog | ~525 | **88%** |

## Future Enhancements

- Move remaining perf helpers into a utilities module or initializer
- Replace remaining dialog accessors with controller APIs (where sensible)
- Reduce Qt-specific logic in controllers for easier pure testing

## Remaining Separation Issues (Short)

- `CategoryManagerDialog` still exposes small orchestration helpers (`_perf_*`, `_update_save_enabled`) that could live in controllers/utilities.
- Some controllers still reach into dialog widgets directly; consider tighter controller APIs to reduce dialog coupling.
- `CategoryManagerCategoryOpsController` still handles post-commit UI effects; consider extracting UI side effects to dedicated helpers if further isolation is desired.

## Recent Cleanups (Notes)

- Category commit side effects split into `_sync_category_map`, `_sync_category_combo`, and `_sync_view_model` for clarity.
- Category ops now use a minimal dialog adapter (`_DialogAdapter`) to reduce direct dialog coupling.
- Category ops split into services (wiring/add) and UI helpers (widget side effects).

## Related Files

- `domain/add_edit_sm.py`: State machine definitions
- `domain/meaning_sources.py`: Meaning facade
- `domain/candidate_provider.py`: Candidate provider interface
- `category_repo.py`: Category repository
- `category_commit.py`: Category commit service
