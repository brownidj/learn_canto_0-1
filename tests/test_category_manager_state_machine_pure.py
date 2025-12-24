"""
Pure (non-Qt) regression tests for the Add/Edit CategoryManager
state machine.

These tests assert *behavioural intent*, not UI wiring.
They must remain Qt-free and import-safe.
"""

from enum import Enum
import pytest


# ---------------------------------------------------------------------------
# Expected public contract
# ---------------------------------------------------------------------------

EXPECTED_STATES = [
    "EMPTY",
    "JYUTPING_VALID",
    "CANDIDATES_READY",
    "HANZI_SELECTED",
    "MEANINGS_VALID",
    "CATEGORY_SELECTED",
    "READY_TO_SAVE",
    "SAVING",
]


def _cands(*hz_src_pairs):
    """Helper to build the `candidates` shape expected by _derive_state.

    Accepts tuples like ("花", "rev") and returns a minimal list.
    The state machine only cares about non-empty vs empty.
    """
    out = []
    for item in hz_src_pairs:
        try:
            hz = str(item[0])
        except Exception:
            hz = ""
        out.append((hz, "src", 0.0))
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.pure
def test_state_enum_exists_and_is_stable():
    """
    CategoryManager must expose a stable enum-like state definition.

    We do not care *where* it lives yet, only that:
      - it is an Enum
      - it contains the expected states
      - names are stable (no accidental renames)
    """
    try:
        from category_manager import AddEditState
    except Exception as e:
        pytest.fail(f"AddEditState enum missing or not importable: {e}")

    assert issubclass(AddEditState, Enum)

    names = [s.name for s in AddEditState]
    assert names == EXPECTED_STATES


@pytest.mark.pure
def test_initial_state_is_empty():
    """
    On construction (before any input),
    the state must be EMPTY.
    """
    from category_manager import AddEditState
    from category_manager import _derive_state

    state = _derive_state(
        jyutping="",
        hanzi="",
        meanings=[],
        category="",
        candidates=[],
        saving=False,
    )

    assert state == AddEditState.EMPTY


@pytest.mark.pure
def test_jyutping_only_advances_to_jyutping_valid():
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="",
        meanings=[],
        category="",
        candidates=[],
        saving=False,
    )

    assert state == AddEditState.JYUTPING_VALID


@pytest.mark.pure
def test_candidates_ready_requires_valid_jyutping_and_candidates():
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="",
        meanings=[],
        category="",
        candidates=_cands(("花", "rev")),
        saving=False,
    )

    assert state == AddEditState.CANDIDATES_READY


@pytest.mark.pure
def test_hanzi_selected_requires_candidate_and_selection():
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=[],
        category="",
        candidates=_cands(("花", "rev")),
        saving=False,
    )

    assert state == AddEditState.HANZI_SELECTED


@pytest.mark.pure
def test_meanings_valid_requires_nonempty_meanings():
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=["flower"],
        category="",
        candidates=_cands(("花", "rev")),
        saving=False,
    )

    assert state == AddEditState.MEANINGS_VALID


@pytest.mark.pure
def test_category_selected_requires_meanings_and_category():
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=["flower"],
        category="nature_land",
        candidates=_cands(("花", "rev")),
        saving=False,
        category_committed=False,
    )

    assert state == AddEditState.CATEGORY_SELECTED


@pytest.mark.pure
def test_ready_to_save_requires_all_fields_and_not_saving():
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=["flower"],
        category="nature_land",
        candidates=_cands(("花", "rev")),
        saving=False,
        category_committed=True,
    )

    assert state == AddEditState.READY_TO_SAVE


@pytest.mark.pure
def test_saving_state_overrides_everything():
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=["flower"],
        category="nature_land",
        candidates=_cands(("花", "rev")),
        saving=True,
    )

    assert state == AddEditState.SAVING


@pytest.mark.pure
def test_invalid_regressions_do_not_skip_states():
    """
    Guard against future shortcuts like:
      EMPTY -> READY_TO_SAVE
    """
    from category_manager import AddEditState, _derive_state

    state = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=[],
        category="nature_land",
        candidates=_cands(("花", "rev")),
        saving=False,
    )

    assert state not in (
        AddEditState.READY_TO_SAVE,
        AddEditState.SAVING,
    )


@pytest.mark.pure
def test_derive_state_is_pure_and_deterministic():
    """Non-functional: _derive_state must be deterministic and must not mutate inputs."""
    from category_manager import _derive_state

    candidates = _cands(("花", "rev"), ("化", "rev"))
    before = list(candidates)

    s1 = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=["flower"],
        category="nature_land",
        candidates=candidates,
        saving=False,
        category_committed=False,
    )
    s2 = _derive_state(
        jyutping="faa1",
        hanzi="花",
        meanings=["flower"],
        category="nature_land",
        candidates=candidates,
        saving=False,
        category_committed=False,
    )

    assert s1 == s2
    assert candidates == before