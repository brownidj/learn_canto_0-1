# CategoryManagerDialog Architecture

## Overview

The CategoryManagerDialog has been refactored from a monolithic 4488-line file into a modular architecture with 12+ specialized controllers, achieving a **73% reduction** to ~1200 lines.

## Design Principles

1. **Single Responsibility**: Each controller handles one cohesive concern
2. **Thin Coordinator**: The main dialog delegates all logic to controllers
3. **Best-Effort UI**: All UI operations are defensive and never raise exceptions
4. **State Management**: Centralized via `AddEditContext` and controller coordination
5. **Testability**: Controllers are independently testable with minimal Qt dependencies

## Controller Responsibilities

### Data & Initialization
- **CategoryManagerInitializer**: Loads and caches vocab, categories, and pipeline data

### UI Controllers
- **CategoryManagerUIBuilder**: Constructs all widgets and layouts
- **CategoryManagerSignalWiring**: Connects Qt signals to handler methods
- **CategoryManagerTypographyController**: Manages fonts and typography
- **CategoryManagerVocabDisplay**: Table display, search filtering, category dropdown refresh

### Workflow Controllers
- **CategoryManagerAddEditFlowController**: Orchestrates the Add/Edit workflow (Jyutping → Category → Hanzi → Meanings → Save)
- **CategoryManagerFocusController**: Focus management and focus policy enforcement
- **CategoryManagerManualHanziController**: Manual Hanzi entry mode
- **CategoryManagerFieldResetController**: Field clearing and reset operations

### Domain Adapters
- **CategoryManagerMeaningResolver**: Adapts MeaningFacade for UI needs
- **CategoryManagerCategoryOpsController**: Category CRUD operations
- **CategoryManagerCandidatePipeline**: Hanzi candidate ranking and curation

### Save/Commit
- **CategoryManagerSaveCommitController**: Save orchestration and persistence
- **CategoryManagerPreviewConfirmController**: Entry preview and confirmation dialogs

### Utilities
- **CategoryManagerHelpers**: Standalone utility functions (perf timing, validation, field readers)

## Key Workflows

### Add Workflow
1. User types Jyutping → `AddEditFlowController.on_jyut_enter()`
2. Jyutping validated → Focus moves to Category
3. User selects Category → `CategoryOpsController.on_add_category_committed()`
4. Category committed → `CandidatePipeline.fill_hanzi_candidates()`
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
| After 12 controllers | 1760 | 60.8% |
| After helper extraction | 1460 | 67.5% |
| After vocab display extraction | 1260 | 72.0% |
| After final cleanup | ~1200 | **73.0%** |

## Future Enhancements

- Extract `_resolve_meanings_for_candidate` to MeaningResolver controller
- Extract `_update_save_enabled` to SaveGatingController
- Move `_build_add_entry_preview` delegation to CategoryOpsController
- Consolidate all focus methods into FocusController

## Related Files

- `domain/add_edit_sm.py`: State machine definitions
- `domain/meaning_sources.py`: Meaning facade
- `category_repo.py`: Category repository
- `category_commit.py`: Category commit service
