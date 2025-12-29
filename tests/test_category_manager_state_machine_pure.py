"""
Pure (non-Qt) regression tests for the Add/Edit CategoryManager
state machine.

These tests assert *behavioural intent*, not UI wiring.
They must remain Qt-free and import-safe.
"""

from enum import Enum
import pytest
import inspect

def _import_state_api():
    """Return (AddEditState, AddEditContext, reduce_fn) from the current module."""
    try:
        from domain.add_edit_sm import AddEditState, AddEditContext, reduce  # type: ignore
        return AddEditState, AddEditContext, reduce
    except Exception as e:
        raise ImportError("Unable to import AddEditState/AddEditContext/reduce from domain.add_edit_sm") from e


def _import_state_enum_only():
    try:
        from domain.add_edit_sm import AddEditState  # type: ignore
        return AddEditState
    except Exception as e:
        raise ImportError("Unable to import AddEditState from domain.add_edit_sm") from e


# ---------------------------------------------------------------------------
# Expected public contract
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Expected public contract
# ---------------------------------------------------------------------------

# We lock the *critical* state names used by the reducer-era UI wiring.
# The reducer may add intermediate states over time, but these must remain present.
# NOTE: these names reflect the current reducer API (post "derive_state" removal).
REQUIRED_STATES = {
    "EMPTY",
    "JY_EDITING",
    "JY_ACCEPTED",
    "CANDIDATES_AVAILABLE",
    "CATEGORY_COMMITTED",
}


def _cands(*hz_src_pairs):
    """Helper to build the `candidates` shape expected by the state machine.

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
        AddEditState = _import_state_enum_only()
    except Exception as e:
        pytest.fail(f"AddEditState enum missing or not importable: {e}")

    assert issubclass(AddEditState, Enum)

    names = [s.name for s in AddEditState]
    name_set = set(names)

    # Must contain critical states (and must start with EMPTY).
    assert names[0] == "EMPTY"
    assert REQUIRED_STATES.issubset(name_set)




# New reducer-based tests

@pytest.mark.pure
def test_initial_state_is_empty():
    """Default context should represent an empty add/edit form."""
    AddEditState, AddEditContext, _reduce = _import_state_api()

    ctx = AddEditContext()

    # Default state used by the reducer is expected to be EMPTY.
    assert AddEditState.EMPTY.name == "EMPTY"
    assert ctx.jy == ""
    assert ctx.hanzi == ""
    assert ctx.meaning == ""
    assert ctx.category == ""


@pytest.mark.pure
def test_reducer_api_exists_and_has_stable_signature():
    """The state machine is reducer-based; ensure the function exists and accepts (state, ctx, evt)."""
    AddEditState, AddEditContext, reduce_fn = _import_state_api()

    assert callable(reduce_fn)
    sig = inspect.signature(reduce_fn)
    params = list(sig.parameters.keys())
    assert params[:3] == ["state", "ctx", "evt"]


@pytest.mark.pure
def test_context_is_frozen_and_not_mutated_by_copy_semantics():
    """AddEditContext is frozen; downstream code must replace it rather than mutate it."""
    _, AddEditContext, _reduce = _import_state_api()

    ctx = AddEditContext()
    with pytest.raises(Exception):
        # frozen dataclass should reject mutation via normal assignment
        ctx.jy = "faa1"  # type: ignore[misc]


@pytest.mark.pure
def test_state_enum_contains_expected_progression_markers():
    """We require key progression markers to exist so UI logic can remain stable."""
    AddEditState = _import_state_enum_only()
    names = [s.name for s in AddEditState]
    s = set(names)

    # Minimal must-haves (reducer-era naming)
    assert "EMPTY" in s
    assert "JY_EDITING" in s
    assert "JY_ACCEPTED" in s
    assert "CANDIDATES_AVAILABLE" in s
    assert "CATEGORY_COMMITTED" in s


@pytest.mark.pure
def test_reduce_returns_expected_tuple_shape():
    """reduce(...) must return (state, ctx, effects) and preserve types."""
    AddEditState, AddEditContext, reduce_fn = _import_state_api()

    state0 = AddEditState.EMPTY
    ctx0 = AddEditContext()

    # We cannot assume a particular event taxonomy here; use a benign placeholder.
    # If the reducer rejects unknown events, it should do so by raising, which is acceptable.
    evt = {"type": "__TEST_NOOP__"}

    try:
        out = reduce_fn(state0, ctx0, evt)
    except Exception:
        pytest.skip("Reducer event taxonomy is not exposed; behaviour tests live elsewhere.")
        return

    assert isinstance(out, tuple)
    assert len(out) == 3
    st1, ctx1, effects = out
    assert isinstance(st1, AddEditState)
    assert isinstance(ctx1, AddEditContext)
    assert isinstance(effects, list)