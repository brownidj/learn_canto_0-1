"""
CategoryManager initialization extracted for maintainability.

Reduces category_manager.py size by extracting ~500 lines of setup logic
into a focused initializer class.
"""

import logging
import os
import time
from typing import TYPE_CHECKING

from domain.add_edit_sm import AddEditContext, AddEditState

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerInitializer:
    """Handles CategoryManagerDialog initialization in a structured way."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def initialize_all(
        self,
        vocab_items: dict,
        categories_map: dict,
    ) -> None:
        """Run all initialization steps for the dialog."""
        self._init_session_state()
        self._init_add_edit_state()
        self._init_style_and_curator()
        self._init_vocab_and_categories(vocab_items, categories_map)
        self._reload_categories_from_disk_if_needed()
        self._init_reverse_lookup_caches()
        self._init_meaning_resolver()
        self._init_cantonese_language_service()
        self._init_cantonese_meaning_controller()
        self._init_vocabulary_service()
        self._init_hanzi_pipeline()
        self._init_candidate_provider()
        self._init_optional_category_profiles()

    def _init_session_state(self) -> None:
        """Initialize flags/caches used across the dialog lifecycle."""
        self.dialog._save_pending = False
        self.dialog._saving_now = False
        self.dialog._row_was_unassigned = {}
        self.dialog._resort_in_progress = False
        self.dialog._resort_pending = False
        self.dialog._rev_manual = {}
        self.dialog._cedict = {}
        self.dialog._cand_combo = None
        self.dialog._cand_gloss_cache = {}
        self.dialog._manual_hanzi_mode = False
        self.dialog._cat_combo_ctrl = None
        self.dialog._add_edit_wired = False

    def _init_add_edit_state(self) -> None:
        """Initialize Add/Edit state machine baseline."""
        self.dialog._add_edit_state = AddEditState.EMPTY
        self.dialog._add_edit_ctx = AddEditContext(
            jy="",
            jy_ok=False,
            duplicate=None,
            hanzi="",
            hz_ok=False,
            manual_hanzi=False,
            meaning="",
            mn_ok=False,
            category="",
            cat_ok=False,
            saving=False,
        )
        try:
            state_svc = getattr(self.dialog, "_state_svc", None)
            self.dialog._add_edit_vm = state_svc.get_state() if state_svc is not None else None
        except Exception:
            self.dialog._add_edit_vm = None

    def _init_style_and_curator(self) -> None:
        """Initialize UI-free helpers for style and candidate curation."""
        from domain.category_rules import HanziStyleIndex, CandidateCurator
        from infra.paths import project_root

        try:
            project_dir = str(project_root())
        except (AttributeError, TypeError, ValueError, RuntimeError):
            project_dir = os.getcwd()

        self.dialog._style_index = HanziStyleIndex(project_dir)
        self.dialog._candidate_curator = CandidateCurator(
            self.dialog._style_index,
            self.dialog.MAX_HANZI_CANDIDATES
        )

    def _init_vocab_and_categories(
        self,
        vocab_items: dict,
        categories_map: dict,
    ) -> None:
        """Normalize in-memory vocab + categories and build stable category list."""
        from domain.category_repo import CategoryRepo
        from domain.category_commit import CategoryCommitService
        from persistence.categories_store import persist_categories_yaml

        # Legacy alias
        if isinstance(vocab_items, dict):
            self.dialog.vocab_items = vocab_items

        # In-memory vocab (shallow copy)
        self.dialog._vocab = {
            k: (
                list(v[0]) if isinstance(v, (list, tuple)) and v else [],
                v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else "",
            )
            for k, v in (vocab_items or {}).items()
        }

        # In-memory categories (authoritative)
        self.dialog._cats = {
            str(k).strip(): list(v or [])
            for k, v in (categories_map or {}).items()
            if str(k).strip()
        }

        # Legacy alias
        self.dialog._categories_map = self.dialog._cats

        # Initialize repo + commit service
        try:
            canon_fn = getattr(self.dialog, "_canon_cat_name", None)

            def persist_cb(_cats_map: dict) -> None:
                try:
                    persist_categories_yaml(_cats_map)
                except (TypeError, AttributeError, RuntimeError, ValueError, OSError):
                    return

            repo = CategoryRepo(
                self.dialog._cats,
                canon=canon_fn if callable(canon_fn) else None,
                persist=persist_cb,
            )
            self.dialog._cat_repo = repo
            self.dialog._cat_commit_svc = CategoryCommitService(repo)
        except (ImportError, ModuleNotFoundError, TypeError, AttributeError, RuntimeError, ValueError):
            self.dialog._cat_repo = None
            self.dialog._cat_commit_svc = None

        # Drop sentinel 'All' if only category
        if len(self.dialog._cats) <= 1:
            for k in list(self.dialog._cats):
                if k.lower() == "all":
                    self.dialog._cats.pop(k, None)

        # Stable categories list
        self.dialog._all_cats = sorted(
            (k for k in self.dialog._cats if k.lower() != "all"),
            key=lambda s: s.lower(),
        )

        # Ensure 'unassigned' exists
        if "unassigned" not in (c.lower() for c in self.dialog._all_cats):
            self.dialog._all_cats.append("unassigned")
            self.dialog._all_cats.sort(key=lambda s: s.lower())

        try:
            logger.debug(
                "AddItem: _cats keys (n=%d): %s",
                len(self.dialog._cats),
                sorted(self.dialog._cats.keys()),
            )
            logger.debug(
                "AddItem: _all_cats (n=%d): %s",
                len(self.dialog._all_cats),
                self.dialog._all_cats,
            )
        except (TypeError, ValueError):
            pass

    def _reload_categories_from_disk_if_needed(self) -> None:
        """If categories input is empty, attempt one-time reload from disk."""
        import yaml
        from domain.storage_paths import categories_yaml_path

        if len(self.dialog._all_cats) <= 1:
            try:
                cat_path = categories_yaml_path()
                if cat_path.exists():
                    with cat_path.open("r", encoding="utf-8") as fh:
                        raw = yaml.safe_load(fh) or {}
            except (OSError, yaml.YAMLError) as e:
                logger.warning("Failed to reload categories from disk: %s", e)
            else:
                if isinstance(raw, dict):
                    keys = [
                        str(k).strip()
                        for k in raw.keys()
                        if str(k).strip() and str(k).lower() != "all"
                    ]
                    if keys:
                        self.dialog._all_cats = sorted(
                            set(keys + ["unassigned"]),
                            key=lambda s: s.lower(),
                        )
                        logger.debug(
                            "AddItem: categories reloaded from %s -> %d keys",
                            cat_path,
                            len(self.dialog._all_cats),
                        )

        # Final safety
        if "unassigned" not in (c.lower() for c in self.dialog._all_cats):
            self.dialog._all_cats.append("unassigned")
            self.dialog._all_cats.sort(key=lambda s: s.lower())

    def _init_reverse_lookup_caches(self) -> None:
        """Initialize reverse lookup caches from parent or create empty."""
        parent = getattr(self.dialog, "_parent", None)

        # Tier 1: reverse index
        reverse_index = getattr(parent, "_reverse_index", None) if parent else None
        if not isinstance(reverse_index, dict) or not reverse_index:
            reverse_index = {}
            try:
                from domain.storage_paths import load_reverse_jyut_map, reverse_jyut_yaml_path
                from domain.jyutping_validation import normalize_jyutping

                reverse_index = load_reverse_jyut_map(
                    reverse_jyut_yaml_path(),
                    normalize_key=normalize_jyutping,
                )
            except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError):
                reverse_index = reverse_index or {}
        self.dialog._reverse_index = reverse_index

        src = "parent" if parent and isinstance(getattr(parent, "_reverse_index", None), dict) else "loaded"
        try:
            size = len(self.dialog._reverse_index)
            logger.debug("CacheAudit: reverse_index source=%s size=%d", src, int(size))
        except (TypeError, ValueError):
            pass

        # Tier 2: shared Unihan char map
        char_map = getattr(parent, "_char_map", None) if parent else None
        if not isinstance(char_map, dict) or not char_map:
            char_map = {}
            try:
                from infra.paths import project_root
                from infra.unihan import load_unihan_char_map

                char_map = load_unihan_char_map(project_root())
            except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError):
                char_map = char_map or {}
        self.dialog._char_map = char_map

        # Share back to parent
        if parent:
            try:
                setattr(parent, "_reverse_index", self.dialog._reverse_index)
                setattr(parent, "_char_map", self.dialog._char_map)
            except (AttributeError, TypeError):
                pass

    def _init_hanzi_pipeline(self) -> None:
        """Initialize Hanzi candidate pipeline."""
        from domain.hanzi_candidate_pipeline import (
            HanziCandidatePipeline,
            build_pipeline_from_category_manager,
        )

        try:
            self.dialog._hanzi_pipeline = build_pipeline_from_category_manager(self.dialog)
            return
        except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning(
                "HanziCandidatePipeline factory failed; falling back to minimal pipeline: %s",
                e,
            )

        try:
            from domain.jyutping_validation import normalize_jyutping
            self.dialog._hanzi_pipeline = HanziCandidatePipeline(
                normalize_jyutping=normalize_jyutping
            )
        except (AttributeError, TypeError, ValueError, RuntimeError):
            self.dialog._hanzi_pipeline = HanziCandidatePipeline(
                normalize_jyutping=lambda s: " ".join((s or "").strip().lower().split())
            )

    def _init_candidate_provider(self) -> None:
        """Initialize candidate provider adapter if not explicitly provided."""
        try:
            if getattr(self.dialog, "_candidate_provider", None) is not None:
                return
        except Exception:
            pass
        try:
            from ui.category_manager_candidate_pipeline import CandidatePipelineProvider
            self.dialog._candidate_provider = CandidatePipelineProvider(self.dialog)
        except Exception:
            self.dialog._candidate_provider = None

    def _init_meaning_resolver(self) -> None:
        """Initialize meaning resolver (optional)."""
        from domain.meaning_sources import default_facade

        self.dialog._meaning_facade = None
        try:
            self.dialog._meaning_facade = default_facade()
        except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning("Meaning facade init failed: %s", e)
            self.dialog._meaning_facade = None

        try:
            logger.debug(
                "MeaningFacade init: ok=%s type=%s",
                bool(self.dialog._meaning_facade is not None),
                type(self.dialog._meaning_facade).__name__ if self.dialog._meaning_facade else "None",
            )
        except (TypeError, ValueError):
            pass

    def _init_cantonese_language_service(self) -> None:
        """Initialize Cantonese language service (optional)."""
        try:
            from services.cantonese_language_service import CantoneseLanguageService
            from domain.storage_paths import cantonese_language_cache_path

            cache_path = cantonese_language_cache_path()
            self.dialog._canto_service = CantoneseLanguageService(cache_path=cache_path)
            logger.debug("Cantonese language service initialized (cache=%s)", str(cache_path))
        except (ImportError, OSError, AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.warning("Cantonese language service init failed: %s", e)
            self.dialog._canto_service = None

    def _init_cantonese_meaning_controller(self) -> None:
        """Initialize Cantonese meaning controller (optional)."""
        from ui.cantonese_meaning_controller import CantoneseMeaningController

        svc = getattr(self.dialog, "_canto_service", None)
        self.dialog._canto_ctrl = CantoneseMeaningController(self.dialog, svc)
        logger.debug("Cantonese meaning controller initialized")

    def _init_vocabulary_service(self) -> None:
        """Initialize VocabularyService (Week 2 refactoring)."""
        self.dialog._vocab_service = None
        self.dialog._entry_validator = None

        try:
            from domain.vocabulary_service import VocabularyService
            from domain.entry_validation import EntryValidator

            from domain.jyutping_validation import normalize_jyutping
            self.dialog._entry_validator = EntryValidator(
                normalize_jy=normalize_jyutping,
                valid_categories=set(self.dialog._all_cats) if hasattr(self.dialog, "_all_cats") else None,
            )

            self.dialog._vocab_service = VocabularyService(
                vocab=self.dialog._vocab,
                categories=self.dialog._cats,
                normalize_jy=normalize_jyutping,
            )

            logger.debug("VocabularyService initialized successfully")
        except (ImportError, TypeError, AttributeError, RuntimeError) as e:
            logger.warning("VocabularyService init failed: %s", e)
            self.dialog._vocab_service = None
            self.dialog._entry_validator = None

    def _init_optional_category_profiles(self) -> None:
        """Build optional category semantic profiles from existing vocab."""
        if not isinstance(getattr(self.dialog, "_cat_keywords", None), dict):
            self.dialog._cat_keywords = {}

        if isinstance(getattr(self.dialog, "_vocab", None), dict) and isinstance(
            getattr(self.dialog, "_cats", None), dict
        ):
            builder = getattr(self.dialog, "_build_category_profiles", None)
            if callable(builder):
                try:
                    builder()
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    self.dialog._cat_keywords = {}
