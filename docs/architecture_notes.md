# Architecture Notes: Add/Edit & Cantonese Meaning

This note captures the current architecture and the refactors completed to improve maintainability and separation of concerns around the Add/Edit flow and the Cantonese meaning service.

## Current Snapshot (What’s Working)
- Dialog orchestration is split across UI builder, wiring, flow, focus, and category controllers in `ui/category_manager_*`.
- Domain logic (meaning sources, validation, candidate pipeline) is outside the UI layer in `domain/` and `services/`.
- Defensive UI ops (`WidgetAccessor`, best‑effort wiring) reduce crash risk in PySide.

## Key Friction Points (Remaining)
1) **Focus orchestration can drift**
   - Focus moves are now centralized in the focus controller, but new handlers must keep using it.

2) **Async meaning application is still UI‑coupled**
   - The new `CantoneseMeaningController` isolates lookup/apply, but UI code must call it instead of ad‑hoc updates.

3) **State still exists in multiple places**
   - ViewModel is the single mutable source; SM context is derived. New code must avoid mutating `_add_edit_ctx` directly.

## Refactor Plan (Completed)
### Phase 1 — Make dependencies explicit (Done)
**Goal:** Remove dynamic hidden coupling.
- Added a small `CandidateProvider` interface and adapters.
- Dialog now receives a provider explicitly.
- Tests pass stub providers.

### Phase 2 — Single focus authority (Done)
**Goal:** Predictable focus behavior.
- All focus transitions go through `CategoryManagerFocusController`.
- Focus contract documented in the controller.

### Phase 3 — CantoneseMeaningController (Done)
**Goal:** Isolate network/cache/apply behavior.
- `ui/cantonese_meaning_controller.py` owns cache‑first lookup, async fetch, UI apply, and notes messaging.
- Dialog delegates to controller; tests can stub it.

### Phase 4 — ViewModel‑like state consolidation (Done)
**Goal:** Reduce the number of truth sources.
- Added `ui/add_edit_view_model.py`.
- Controllers read/write through the ViewModel.
- SM context (`AddEditContext`) is derived from ViewModel via `_sync_add_edit_ctx()`.

## Focus Contract (Authoritative)
- After category commit → Hanzi (no select‑all).
- After candidate selection → Meaning (select‑all).
- After meaning save/commit → Jyutping (select‑all).
- After manual Hanzi mode → Hanzi (select‑all).

## Where to Extend Safely
- **New focus behavior:** add to `CategoryManagerFocusController` only.
- **New meaning sources:** add to `MeaningFacade` or `CantoneseMeaningController`.
- **New candidate sources:** add to a `CandidateProvider` adapter.
- **New Add/Edit state fields:** extend `AddEditViewModel` and keep `AddEditContext` in sync.

## Risks & Guardrails
- Do not mutate `_add_edit_ctx` directly; always go through `_update_add_edit_state`.
- Do not call `WidgetAccessor.focus` outside the focus controller.
- Keep meaning lookups cache‑first and async to avoid UI stalls.

## Suggested Regression Tests (Optional)
- ViewModel → SM context sync (update VM, ensure ctx matches).
- Meaning fill after candidate selection still applies via controller.
- Focus contract checks remain stable (existing tests already cover core paths).
