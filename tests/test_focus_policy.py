

import pytest


def _import_focus_policy_api():
    """Resolve the focus policy API across refactors.

    We keep this test robust to naming changes while still enforcing behaviour.
    """
    candidates = []
    try:
        # Preferred location after extraction
        from ui import focus_policy as fp  # type: ignore
        candidates.append(fp)
    except Exception:
        fp = None

    if fp is None:
        pytest.fail(
            "Could not import ui.focus_policy. "
            "Create ui/focus_policy.py with pure decision functions so this test can run."
        )

    # Function name variants we accept.
    steal_names = (
        "should_steal_focus",
        "allow_focus_steal",
        "can_steal_focus",
        "focus_should_steal",
    )
    regen_names = (
        "should_regenerate_candidates",
        "allow_regenerate_candidates",
        "can_regenerate_candidates",
        "regenerate_should_run",
    )

    steal_fn = None
    for n in steal_names:
        if hasattr(fp, n):
            steal_fn = getattr(fp, n)
            break

    regen_fn = None
    for n in regen_names:
        if hasattr(fp, n):
            regen_fn = getattr(fp, n)
            break

    if steal_fn is None:
        pytest.fail(
            "ui.focus_policy is missing a focus-steal decision function. "
            "Expected one of: %r" % (steal_names,)
        )

    if regen_fn is None:
        pytest.fail(
            "ui.focus_policy is missing a candidate-regeneration decision function. "
            "Expected one of: %r" % (regen_names,)
        )

    return steal_fn, regen_fn


@pytest.mark.pure
@pytest.mark.parametrize(
    "manual_mode,hanzi_committed,expected",
    [
        (False, False, True),
        (True, False, False),
        (False, True, False),
        (True, True, False),
    ],
)
def test_should_regenerate_candidates_blocks_manual_or_committed(manual_mode, hanzi_committed, expected):
    """Central rule: do not regenerate/overwrite candidates after explicit user choice."""
    _steal, regen = _import_focus_policy_api()

    # Accept both keyword and positional styles.
    try:
        out = regen(manual_mode=manual_mode, hanzi_committed=hanzi_committed, reason="test")
    except TypeError:
        try:
            out = regen(manual_mode, hanzi_committed)
        except TypeError:
            out = regen(manual_mode=manual_mode, hanzi_committed=hanzi_committed)

    assert bool(out) is bool(expected)


@pytest.mark.pure
def test_should_steal_focus_true_when_user_action():
    """If the user action clearly indicates intent, focus stealing is allowed."""
    steal, _regen = _import_focus_policy_api()

    # When user_action=True, we allow focus moves regardless of other guards.
    # (This matches the desired 'intent gating' behaviour.)
    kwargs = dict(
        reason="test",
        user_action=True,
        manual_mode=True,
        hanzi_committed=True,
        combo_has_focus=True,
        view_has_focus=True,
    )

    try:
        out = steal(**kwargs)
    except TypeError:
        # Minimal positional fallback: (user_action, combo_has_focus, view_has_focus, manual_mode, hanzi_committed)
        out = steal(True, True, True, True, True)

    assert bool(out) is True


@pytest.mark.pure
def test_should_steal_focus_false_by_default_no_intent():
    """Default: do not steal focus unless intent is clear."""
    steal, _regen = _import_focus_policy_api()

    kwargs = dict(
        reason="test",
        user_action=False,
        manual_mode=False,
        hanzi_committed=False,
        combo_has_focus=False,
        view_has_focus=False,
    )

    try:
        out = steal(**kwargs)
    except TypeError:
        out = steal(False, False, False, False, False)

    assert bool(out) is False


@pytest.mark.pure
@pytest.mark.parametrize(
    "combo_has_focus,view_has_focus",
    [
        (True, False),
        (False, True),
        (True, True),
    ],
)
def test_should_steal_focus_never_steals_when_candidate_ui_has_focus(combo_has_focus, view_has_focus):
    """If the candidate combobox or its popup view has focus, never steal focus."""
    steal, _regen = _import_focus_policy_api()

    kwargs = dict(
        reason="test",
        user_action=False,
        manual_mode=False,
        hanzi_committed=False,
        combo_has_focus=combo_has_focus,
        view_has_focus=view_has_focus,
    )

    try:
        out = steal(**kwargs)
    except TypeError:
        out = steal(False, combo_has_focus, view_has_focus, False, False)

    assert bool(out) is False


@pytest.mark.pure
@pytest.mark.parametrize(
    "manual_mode,hanzi_committed",
    [
        (True, False),
        (False, True),
        (True, True),
    ],
)
def test_should_steal_focus_never_steals_when_manual_or_committed(manual_mode, hanzi_committed):
    """If manual mode is active or Hanzi has been committed, never steal focus."""
    steal, _regen = _import_focus_policy_api()

    kwargs = dict(
        reason="test",
        user_action=False,
        manual_mode=manual_mode,
        hanzi_committed=hanzi_committed,
        combo_has_focus=False,
        view_has_focus=False,
    )

    try:
        out = steal(**kwargs)
    except TypeError:
        out = steal(False, False, False, manual_mode, hanzi_committed)

    assert bool(out) is False