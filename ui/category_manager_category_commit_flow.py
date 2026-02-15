"""
Pure category-commit decision flow for CategoryManager.

Separates domain decision-making from UI side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class CategoryRepoLike(Protocol):
    def canon(self, text: str) -> str: ...
    def exists(self, cat: str) -> bool: ...


class CategoryCommitServiceLike(Protocol):
    def commit(self, *, requested: str, has_jyutping: bool, user_confirmed_add: bool): ...


ConfirmFn = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class CategoryCommitDecision:
    ok: bool
    category: str
    should_fill_candidates: bool
    reason: str
    canon: str
    exists_now: bool
    user_confirmed_add: bool


def decide_category_commit(
    *,
    cat_raw: str,
    has_jy: bool,
    repo: CategoryRepoLike,
    svc: CategoryCommitServiceLike,
    confirm_add_fn: ConfirmFn | None = None,
) -> CategoryCommitDecision:
    """Compute category commit decision without UI side effects."""
    canon = _canon_category(repo, cat_raw)
    if not canon:
        return CategoryCommitDecision(
            ok=False,
            category="",
            should_fill_candidates=False,
            reason="empty",
            canon="",
            exists_now=False,
            user_confirmed_add=False,
        )

    exists_now = _category_exists(repo, canon)
    user_confirmed_add = False

    if not exists_now:
        user_confirmed_add = bool(confirm_add_fn(canon)) if callable(confirm_add_fn) else False
        if not user_confirmed_add:
            return CategoryCommitDecision(
                ok=False,
                category=canon,
                should_fill_candidates=False,
                reason="user_declined_add",
                canon=canon,
                exists_now=False,
                user_confirmed_add=False,
            )

    try:
        res = svc.commit(
            requested=canon,
            has_jyutping=bool(has_jy),
            user_confirmed_add=bool(user_confirmed_add),
        )
    except Exception:
        res = None

    if res is None or not bool(getattr(res, "ok", False)):
        return CategoryCommitDecision(
            ok=False,
            category=str(getattr(res, "category", "") or "").strip(),
            should_fill_candidates=bool(getattr(res, "should_fill_candidates", False)) if res is not None else False,
            reason=str(getattr(res, "reason", "commit_failed") or "commit_failed"),
            canon=canon,
            exists_now=exists_now,
            user_confirmed_add=user_confirmed_add,
        )

    return CategoryCommitDecision(
        ok=True,
        category=str(getattr(res, "category", "") or "").strip(),
        should_fill_candidates=bool(getattr(res, "should_fill_candidates", False)),
        reason=str(getattr(res, "reason", "ok") or "ok"),
        canon=canon,
        exists_now=exists_now,
        user_confirmed_add=user_confirmed_add,
    )


def _canon_category(repo: CategoryRepoLike, cat_raw: str) -> str:
    try:
        return str(repo.canon(cat_raw) or "").strip()
    except Exception:
        return str(cat_raw or "").strip()


def _category_exists(repo: CategoryRepoLike, canon: str) -> bool:
    try:
        return bool(canon) and bool(repo.exists(canon))
    except Exception:
        return False

