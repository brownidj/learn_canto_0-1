# tests/test_category_commit_service_pure.py

from __future__ import annotations

from category_commit import CategoryCommitService


class _FakeCategoryRepo:
    """Minimal repo double for CategoryCommitService tests.

    Implements the exact interface the service relies on:
      - canon(text) -> str
      - exists(cat) -> bool
      - add(cat) -> bool

    Keeps tests independent of CategoryRepo persistence / UI wiring.
    """

    def __init__(self, initial: set[str] | None = None, *, add_success: bool = True):
        self._cats: set[str] = set(initial or set())
        self._add_success = bool(add_success)

        # Simple call counters to help debug regressions quickly.
        self.calls_canon = 0
        self.calls_exists = 0
        self.calls_add = 0

    def canon(self, text: str) -> str:
        self.calls_canon += 1
        # Match the common behavior: strip and collapse whitespace
        t = str(text or "").strip()
        if not t:
            return ""
        return "_".join(t.split())

    def exists(self, cat: str) -> bool:
        self.calls_exists += 1
        c = str(cat or "").strip()
        return bool(c) and c in self._cats

    def add(self, cat: str) -> bool:
        self.calls_add += 1
        c = str(cat or "").strip()
        if not c:
            return False
        if not self._add_success:
            return False
        self._cats.add(c)
        return True


def test_empty_requested_returns_not_ok_and_no_fill() -> None:
    repo = _FakeCategoryRepo({"direction", "unassigned"})
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="   ", has_jyutping=True, user_confirmed_add=True)

    assert res.ok is False
    assert res.category == ""
    assert res.should_fill_candidates is False
    assert res.reason == "empty"
    assert repo.calls_add == 0


def test_existing_category_commits_and_may_fill_candidates() -> None:
    repo = _FakeCategoryRepo({"direction", "unassigned"})
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="direction", has_jyutping=True, user_confirmed_add=False)

    assert res.ok is True
    assert res.category == "direction"
    assert res.should_fill_candidates is True
    assert res.reason == "exists"
    assert repo.exists("direction") is True
    assert repo.calls_add == 0


def test_existing_category_commits_but_does_not_fill_when_no_jyutping() -> None:
    repo = _FakeCategoryRepo({"direction", "unassigned"})
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="direction", has_jyutping=False, user_confirmed_add=False)

    assert res.ok is True
    assert res.category == "direction"
    assert res.should_fill_candidates is False
    assert res.reason == "exists"
    assert repo.calls_add == 0


def test_unknown_category_declined_add_returns_not_ok() -> None:
    repo = _FakeCategoryRepo({"direction", "unassigned"})
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="verbs_actions", has_jyutping=True, user_confirmed_add=False)

    assert res.ok is False
    assert res.category == "verbs_actions"
    assert res.should_fill_candidates is False
    assert res.reason == "user_declined_add"
    assert repo.exists("verbs_actions") is False
    assert repo.calls_add == 0


def test_unknown_category_confirmed_add_adds_and_returns_ok() -> None:
    repo = _FakeCategoryRepo({"direction", "unassigned"}, add_success=True)
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="verbs_actions", has_jyutping=True, user_confirmed_add=True)

    assert res.ok is True
    assert res.category == "verbs_actions"
    assert res.should_fill_candidates is True
    assert res.reason == "added"
    # Hard invariant: ok => exists
    assert repo.exists("verbs_actions") is True
    assert repo.calls_add == 1


def test_unknown_category_confirmed_add_but_repo_add_fails_returns_not_ok() -> None:
    repo = _FakeCategoryRepo({"direction", "unassigned"}, add_success=False)
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="verbs_actions", has_jyutping=True, user_confirmed_add=True)

    assert res.ok is False
    assert res.category == "verbs_actions"
    assert res.should_fill_candidates is False
    assert res.reason == "add_failed"
    assert repo.exists("verbs_actions") is False
    assert repo.calls_add == 1


def test_canonicalisation_is_applied_before_existence_check() -> None:
    repo = _FakeCategoryRepo({"verbs_actions", "direction"})
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="  verbs   actions  ", has_jyutping=True, user_confirmed_add=False)

    # canon collapses whitespace into underscores in the fake repo
    assert res.ok is True
    assert res.category == "verbs_actions"
    assert res.reason == "exists"
    assert repo.calls_canon >= 1
    assert repo.calls_exists >= 1


def test_unknown_category_confirmed_add_does_not_fill_without_jyutping() -> None:
    repo = _FakeCategoryRepo({"direction", "unassigned"}, add_success=True)
    svc = CategoryCommitService(repo)

    res = svc.commit(requested="verbs_actions", has_jyutping=False, user_confirmed_add=True)

    assert res.ok is True
    assert res.category == "verbs_actions"
    assert res.should_fill_candidates is False
    assert res.reason == "added"
    assert repo.exists("verbs_actions") is True