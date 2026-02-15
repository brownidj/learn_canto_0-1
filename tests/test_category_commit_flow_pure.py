from __future__ import annotations

from domain.category_commit import CategoryCommitService
from ui.category_manager_category_commit_flow import decide_category_commit


class _Repo:
    def __init__(self, cats: set[str] | None = None):
        self._cats = set(cats or set())

    def canon(self, text: str) -> str:
        return str(text or "").strip()

    def exists(self, cat: str) -> bool:
        return cat in self._cats

    def add(self, cat: str) -> bool:
        if not cat:
            return False
        if cat in self._cats:
            return False
        self._cats.add(cat)
        return True


def test_decide_category_commit_empty_raw():
    repo = _Repo({"work"})
    svc = CategoryCommitService(repo)
    decision = decide_category_commit(
        cat_raw="",
        has_jy=False,
        repo=repo,
        svc=svc,
        confirm_add_fn=lambda _c: True,
    )
    assert decision.ok is False
    assert decision.reason == "empty"


def test_decide_category_commit_existing_no_confirm():
    repo = _Repo({"work"})
    svc = CategoryCommitService(repo)
    decision = decide_category_commit(
        cat_raw="work",
        has_jy=True,
        repo=repo,
        svc=svc,
        confirm_add_fn=lambda _c: (_ for _ in ()).throw(AssertionError("confirm should not be called")),
    )
    assert decision.ok is True
    assert decision.category == "work"
    assert decision.should_fill_candidates is True


def test_decide_category_commit_unknown_declined():
    repo = _Repo({"work"})
    svc = CategoryCommitService(repo)
    decision = decide_category_commit(
        cat_raw="newcat",
        has_jy=True,
        repo=repo,
        svc=svc,
        confirm_add_fn=lambda _c: False,
    )
    assert decision.ok is False
    assert decision.reason == "user_declined_add"
    assert decision.category == "newcat"


def test_decide_category_commit_unknown_confirmed():
    repo = _Repo({"work"})
    svc = CategoryCommitService(repo)
    decision = decide_category_commit(
        cat_raw="newcat",
        has_jy=False,
        repo=repo,
        svc=svc,
        confirm_add_fn=lambda _c: True,
    )
    assert decision.ok is True
    assert decision.category == "newcat"
    assert decision.should_fill_candidates is False
    assert repo.exists("newcat") is True
