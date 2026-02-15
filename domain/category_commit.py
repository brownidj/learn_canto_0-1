# category_commit.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CategoryRepoLike(Protocol):
    def canon(self, text: str) -> str: ...
    def exists(self, cat: str) -> bool: ...
    def add(self, cat: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class CategoryCommitResult:
    ok: bool
    category: str
    should_fill_candidates: bool
    reason: str


class CategoryCommitService:
    def __init__(self, repo: CategoryRepoLike):
        self._repo = repo

    def commit(
            self,
            *,
            requested: str,
            has_jyutping: bool,
            user_confirmed_add: bool,
    ) -> CategoryCommitResult:
        """
        Attempt to commit a category.

        Inputs:
          requested:
              Raw category text from UI.
          has_jyutping:
              Whether a valid Jyutping is already present.
          user_confirmed_add:
              Whether the user explicitly confirmed adding a new category.

        Returns:
          CategoryCommitResult
        """

        # Canonicalise early
        cat = self._repo.canon(requested)
        if not cat:
            return CategoryCommitResult(
                ok=False,
                category="",
                should_fill_candidates=False,
                reason="empty",
            )

        # Existing category: accept immediately
        if self._repo.exists(cat):
            return CategoryCommitResult(
                ok=True,
                category=cat,
                should_fill_candidates=bool(has_jyutping),
                reason="exists",
            )

        # New category path
        if not user_confirmed_add:
            return CategoryCommitResult(
                ok=False,
                category=cat,
                should_fill_candidates=False,
                reason="user_declined_add",
            )

        # Add to authoritative repo (SINGLE SOURCE OF TRUTH)
        added = self._repo.add(cat)
        if not added or not self._repo.exists(cat):
            # Defensive: invariant violation
            return CategoryCommitResult(
                ok=False,
                category=cat,
                should_fill_candidates=False,
                reason="add_failed",
            )

        # Success: invariant guaranteed
        return CategoryCommitResult(
            ok=True,
            category=cat,
            should_fill_candidates=bool(has_jyutping),
            reason="added",
        )