"""
Vocabulary and category loading/persistence service.

Extracted from main.py to improve testability and maintainability.
"""
import os
import logging
from typing import Dict, List, Tuple, Optional, Any, Iterable

import yaml

from infra.paths import data_path

logger = logging.getLogger(__name__)


def load_vocab_from_unified_yaml() -> Tuple[Dict[str, List], Dict[str, List[str]]]:
    """Load vocab.yaml (unified categories + entries) and return (vocab, categories_map).

    vocab: {hanzi: [meanings_list, jyutping_str]}
    categories_map: {category: [hanzi, ...]}
    """
    path = data_path("vocab.yaml")
    if not os.path.exists(path):
        logger.warning("vocab.yaml not found at: %s", path)
        return {}, {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as e:
        logger.warning("Failed to load vocab.yaml: %s", e)
        return {}, {}

    if not isinstance(data, dict):
        logger.warning("vocab.yaml top-level is not a mapping; got %r", type(data))
        return {}, {}

    categories_block = data.get("categories") or {}
    entries_block = data.get("entries") or {}

    if not isinstance(categories_block, dict):
        categories_block = {}
    if not isinstance(entries_block, dict):
        entries_block = {}

    vocab = {}
    categories_map = {}

    # Start with empty lists for all defined categories
    for cat_key in categories_block.keys():
        categories_map[str(cat_key)] = []

    # Populate vocab and categories from entries
    for jy_key, entry in entries_block.items():
        if not isinstance(entry, dict):
            continue
        jyut = entry.get("jyutping") or jy_key
        senses = entry.get("senses") or []
        if not isinstance(senses, list):
            continue
        for sense in senses:
            if not isinstance(sense, dict):
                continue
            hanzi = sense.get("hanzi")
            gloss = sense.get("gloss")
            cats = sense.get("categories") or []
            if not hanzi or not gloss:
                continue

            # Build meanings list as a list of gloss strings; merge if Hanzi already present
            if hanzi in vocab:
                existing_meanings = vocab[hanzi][0]
                existing_jy = vocab[hanzi][1]
                if gloss not in existing_meanings:
                    existing_meanings.append(gloss)
                if not existing_jy and jyut:
                    vocab[hanzi][1] = jyut
            else:
                vocab[hanzi] = [[gloss], jyut]

            # Populate categories map
            for cat in cats:
                if not cat:
                    continue
                cat_str = str(cat)
                if cat_str not in categories_map:
                    categories_map[cat_str] = []
                if hanzi not in categories_map[cat_str]:
                    categories_map[cat_str].append(hanzi)

    # Ensure an 'unassigned' bucket exists even if empty
    if "unassigned" not in categories_map:
        categories_map["unassigned"] = []

    return vocab, categories_map


def load_categories_from_disk() -> dict:
    """Load categories from vocab.yaml (single source of truth)."""
    try:
        _v, cats = load_vocab_from_unified_yaml()
    except Exception:
        cats = {}
    return cats or {}


def load_categories_map() -> dict:
    """Return the best-available categories map.

    Source order:
      1) vocab.yaml-derived categories (single source of truth)
    """
    try:
        cats_disk = load_categories_from_disk()
        if isinstance(cats_disk, dict):
            return cats_disk
    except Exception:
        return {}
    return {}


def persist_categories_block(categories: dict | Iterable[str]) -> None:
    """Persist category keys into vocab.yaml's categories block (best-effort)."""
    try:
        if isinstance(categories, dict):
            cats = [str(k).strip() for k in categories.keys()]
        else:
            cats = [str(k).strip() for k in categories]
    except Exception:
        cats = []

    cats = [c for c in cats if c]
    if not cats:
        return

    try:
        vocab_path = data_path("vocab.yaml")
        if not os.path.exists(vocab_path):
            return
        with open(vocab_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            data = {}
        categories_block = data.get("categories")
        if not isinstance(categories_block, dict):
            categories_block = {}

        changed = False
        for cat in cats:
            if cat not in categories_block:
                categories_block[cat] = {}
                changed = True

        if not changed:
            return

        data["categories"] = categories_block
        with open(vocab_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=True)
    except Exception:
        return


def update_entry_categories(
    *,
    hanzi: str,
    categories: list[str],
) -> bool:
    """Update categories for a Hanzi entry inside vocab.yaml (best-effort)."""
    hz = str(hanzi or "").strip()
    cats = [str(c).strip() for c in (categories or []) if str(c).strip()]
    if not hz:
        return False

    try:
        vocab_path = data_path("vocab.yaml")
        if not os.path.exists(vocab_path):
            return False
        with open(vocab_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            data = {}

        entries_block = data.get("entries")
        if not isinstance(entries_block, dict):
            entries_block = {}

        updated = False
        for _jy, entry in entries_block.items():
            if not isinstance(entry, dict):
                continue
            senses = entry.get("senses")
            if not isinstance(senses, list):
                continue
            for s in senses:
                if not isinstance(s, dict):
                    continue
                if s.get("hanzi") == hz:
                    s["categories"] = cats
                    updated = True

        if not updated:
            return False

        categories_block = data.get("categories")
        if not isinstance(categories_block, dict):
            categories_block = {}
        for cat in cats:
            categories_block.setdefault(cat, {})
        data["categories"] = categories_block
        data["entries"] = entries_block

        with open(vocab_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=True)
        return True
    except Exception:
        return False


def commit_vocab_entry(
    entry: dict,
    vocab: dict,
    categories_map: dict,
    window: Optional[Any] = None,
    dialog: Optional[Any] = None
) -> None:
    """
    Commit a new vocab entry from the CategoryManagerDialog.

    The `entry` dict is expected to have:
        - jyutping: str
        - hanzi: str
        - gloss: str
        - categories: list[str]

    Updates in-memory vocab and categories_map, mirrors changes to window/dialog,
    and persists to vocab.yaml.
    """
    try:
        jy = " ".join((entry.get("jyutping") or "").strip().lower().split())
        hz = (entry.get("hanzi") or "").strip()
        gloss = (entry.get("gloss") or "").strip()
        cats_in = entry.get("categories") or []
        cats = [str(c).strip() for c in cats_in if str(c).strip()]
    except Exception as e:
        logger.warning("Commit aborted: malformed entry payload %r (%s)", entry, e)
        return

    if not jy or not hz or not gloss or not cats:
        logger.debug(
            "Commit aborted: missing fields jy=%r hz=%r gloss=%r cats=%r",
            jy, hz, gloss, cats,
        )
        return

    # ---- Update in-memory vocab ----
    try:
        if hz in vocab:
            meanings, jy_existing = vocab.get(hz, ([], ""))
            if not isinstance(meanings, list):
                meanings = []
            if gloss not in meanings:
                meanings.append(gloss)
            if not jy_existing:
                jy_existing = jy
            vocab[hz] = [meanings, jy_existing]
        else:
            vocab[hz] = [[gloss], jy]
    except Exception as e:
        logger.warning("Failed to update in-memory vocab for '%s' (%s)", hz, e)

    # ---- Mirror update back into the dialog (same-session duplicate detection) ----
    try:
        dlg_vocab = getattr(dialog, "_vocab", None)
    except (TypeError, AttributeError, RuntimeError):
        dlg_vocab = None

    if isinstance(dlg_vocab, dict):
        try:
            dlg_vocab[hz] = [[gloss], jy]
        except (TypeError, AttributeError, RuntimeError):
            pass

    # Optional: if the dialog exposes a test/legacy mirror dict, keep it in sync too.
    try:
        dlg_vocab_items = getattr(dialog, "vocab_items", None)
    except (TypeError, AttributeError, RuntimeError):
        dlg_vocab_items = None

    if isinstance(dlg_vocab_items, dict):
        try:
            dlg_vocab_items[hz] = [[gloss], jy]
        except (TypeError, AttributeError, RuntimeError):
            pass

    # ---- Update in-memory categories_map ----
    try:
        for cat in cats:
            lst = categories_map.setdefault(cat, [])
            if hz not in lst:
                lst.append(hz)
    except Exception as e:
        logger.warning("Failed to update in-memory categories_map for '%s' (%s)", hz, e)

    # Reflect changes on the window's categories map
    if window is not None:
        try:
            wmap = getattr(window, "_categories_map", None)
            if isinstance(wmap, dict):
                for cat in cats:
                    lst = wmap.setdefault(cat, [])
                    if hz not in lst:
                        lst.append(hz)
                setattr(window, "_categories_map", wmap)
        except Exception as e:
            logger.debug("Could not mirror categories onto window._categories_map: %s", e)

    # ---- Persist changes back to vocab.yaml ----
    try:
        vocab_path = data_path("vocab.yaml")
        if not os.path.exists(vocab_path):
            logger.warning("Cannot persist new entry: vocab.yaml not found at %s", vocab_path)
            return

        with open(vocab_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            data = {}

        categories_block = data.get("categories")
        if not isinstance(categories_block, dict):
            categories_block = {}

        entries_block = data.get("entries")
        if not isinstance(entries_block, dict):
            entries_block = {}

        # Ensure categories exist in the categories block
        for cat in cats:
            categories_block.setdefault(cat, {})

        # Upsert the entry under its Jyutping key
        entry_obj = entries_block.get(jy)
        if not isinstance(entry_obj, dict):
            entry_obj = {"senses": []}
        else:
            if not isinstance(entry_obj.get("senses"), list):
                entry_obj["senses"] = []

        senses = entry_obj["senses"]

        # Try to merge with an existing sense that matches hanzi+gloss
        merged = False
        for s in senses:
            if not isinstance(s, dict):
                continue
            if s.get("hanzi") == hz and s.get("gloss") == gloss:
                existing_cats = s.get("categories") or []
                merged_cats = sorted({*(str(c) for c in existing_cats), *cats})
                s["categories"] = merged_cats
                merged = True
                break

        if not merged:
            senses.append({"hanzi": hz, "gloss": gloss, "categories": cats})

        entry_obj["senses"] = senses
        entries_block[jy] = entry_obj

        data["categories"] = categories_block
        data["entries"] = entries_block

        with open(vocab_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=True)

        logger.debug(
            "Committed new vocab entry to %s: jy=%r hanzi=%r cats=%r",
            vocab_path, jy, hz, cats,
        )
    except Exception as e:
        logger.warning(
            "Failed to persist vocab entry for jy=%r hanzi=%r: %s",
            jy, hz, e,
        )
