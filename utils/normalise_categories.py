#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utility to rename or merge category names in data/vocab.yaml.

Usage:
  python utils/normalise_categories.py --list
  python utils/normalise_categories.py --rename old_name new_name
  python utils/normalise_categories.py --merge target name1 name2 ...
  python utils/normalise_categories.py --interactive
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import yaml


def _data_path() -> Path:
    try:
        from infra.paths import data_path
        return Path(data_path("vocab.yaml"))
    except Exception:
        return Path("data") / "vocab.yaml"


def _load_vocab(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"vocab.yaml not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError("vocab.yaml must be a mapping")
    return data


def _save_vocab(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=True)


def _iter_entry_categories(data: dict) -> Iterable[str]:
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return []
    out = []
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        senses = entry.get("senses")
        if not isinstance(senses, list):
            continue
        for sense in senses:
            if not isinstance(sense, dict):
                continue
            cats = sense.get("categories")
            if isinstance(cats, list):
                for c in cats:
                    s = str(c or "").strip()
                    if s:
                        out.append(s)
    return out


def _all_categories(data: dict) -> list[str]:
    cats = []
    block = data.get("categories")
    if isinstance(block, dict):
        cats.extend(str(k).strip() for k in block.keys() if str(k).strip())
    cats.extend(_iter_entry_categories(data))
    uniq = sorted({c for c in cats if c}, key=lambda s: s.lower())
    return uniq


def _ensure_category_block(data: dict) -> dict:
    block = data.get("categories")
    if not isinstance(block, dict):
        block = {}
        data["categories"] = block
    return block


def _replace_categories_in_entries(data: dict, mapping: dict[str, str]) -> None:
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        senses = entry.get("senses")
        if not isinstance(senses, list):
            continue
        for sense in senses:
            if not isinstance(sense, dict):
                continue
            cats = sense.get("categories")
            if not isinstance(cats, list):
                continue
            new_list = []
            for c in cats:
                key = str(c or "").strip()
                if not key:
                    continue
                key = mapping.get(key, key)
                if key and key not in new_list:
                    new_list.append(key)
            sense["categories"] = new_list


def _merge_category_block(block: dict, target: str, sources: Iterable[str]) -> None:
    target = str(target or "").strip()
    if not target:
        return
    target_node = block.get(target)
    if target_node is None:
        block[target] = {}
        target_node = block[target]
    for src in sources:
        src_s = str(src or "").strip()
        if not src_s or src_s == target:
            continue
        node = block.get(src_s)
        if isinstance(target_node, dict) and isinstance(node, dict):
            for k, v in node.items():
                if k not in target_node:
                    target_node[k] = v
        if src_s in block:
            del block[src_s]


def rename_category(data: dict, old: str, new: str) -> None:
    old_s = str(old or "").strip()
    new_s = str(new or "").strip()
    if not old_s or not new_s:
        raise ValueError("Both old and new category names are required")

    mapping = {old_s: new_s}
    _replace_categories_in_entries(data, mapping)

    block = _ensure_category_block(data)
    if old_s != new_s:
        _merge_category_block(block, new_s, [old_s])
    else:
        block.setdefault(new_s, {})


def merge_categories(data: dict, target: str, sources: Iterable[str]) -> None:
    target_s = str(target or "").strip()
    sources_s = [str(s or "").strip() for s in sources]
    sources_s = [s for s in sources_s if s and s != target_s]
    if not target_s or not sources_s:
        raise ValueError("Target and at least one source category are required")

    mapping = {s: target_s for s in sources_s}
    _replace_categories_in_entries(data, mapping)
    block = _ensure_category_block(data)
    _merge_category_block(block, target_s, sources_s)


def _select_indices(names: list[str], prompt: str, multi: bool) -> list[str]:
    print(prompt)
    raw = input("> ").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(",", " ").split()]
    if not parts:
        return []
    selected = []
    for p in parts:
        if p.isdigit():
            idx = int(p)
            if 1 <= idx <= len(names):
                selected.append(names[idx - 1])
        else:
            if p in names:
                selected.append(p)
    if not multi and selected:
        return [selected[0]]
    return list(dict.fromkeys(selected))


def interactive(path: Path) -> None:
    data = _load_vocab(path)
    while True:
        names = _all_categories(data)
        print("\nCategories:")
        for i, name in enumerate(names, start=1):
            print(f"{i:>3}. {name}")
        print("\nChoose action: rename, merge, list, save, quit")
        action = input("> ").strip().lower()
        if action in {"quit", "q"}:
            return
        if action in {"list", "l"}:
            continue
        if action in {"rename", "r"}:
            sel = _select_indices(names, "Select one category (index or name):", multi=False)
            if not sel:
                continue
            new_name = input("New name: ").strip()
            if not new_name:
                continue
            rename_category(data, sel[0], new_name)
            print(f"Renamed '{sel[0]}' -> '{new_name}'")
            continue
        if action in {"merge", "m"}:
            sources = _select_indices(names, "Select categories to merge (indices or names):", multi=True)
            if not sources:
                continue
            target = input("Target category name: ").strip()
            if not target:
                continue
            merge_categories(data, target, sources)
            print(f"Merged {sources} -> '{target}'")
            continue
        if action in {"save", "s"}:
            _save_vocab(path, data)
            print(f"Saved {path}")
            continue
        print("Unknown action")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize category names in vocab.yaml")
    parser.add_argument("--path", default=str(_data_path()), help="Path to vocab.yaml")
    parser.add_argument("--list", action="store_true", help="List categories and exit")
    parser.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"), help="Rename a category")
    parser.add_argument("--merge", nargs="+", metavar=("TARGET", "SRC"), help="Merge categories into target")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    args = parser.parse_args()

    path = Path(args.path)
    data = _load_vocab(path)

    if args.list:
        for name in _all_categories(data):
            print(name)
        return 0

    if args.rename:
        old, new = args.rename
        rename_category(data, old, new)
        _save_vocab(path, data)
        return 0

    if args.merge:
        if len(args.merge) < 2:
            raise SystemExit("--merge requires TARGET and at least one SRC")
        target = args.merge[0]
        sources = args.merge[1:]
        merge_categories(data, target, sources)
        _save_vocab(path, data)
        return 0

    interactive(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
