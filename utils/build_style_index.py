#!/usr/bin/env python3
"""
build_style_index.py

Build or update data/hanzi_style.yaml from data/reverse_jyut.yaml.

Design:
- reverse_jyut.yaml is the fast Jyutping → [Hanzi, …] index (no glosses).
- hanzi_style.yaml is the style metadata per Hanzi, of the form:

    紅:
      style: both
      source: manual

    啡:
      style: unknown
      source: auto-default

This script:
- Loads reverse_jyut.yaml (Jyutping → [Hanzi] lists).
- Optionally loads an existing hanzi_style.yaml to preserve manual edits.
- Adds any missing Hanzi with a default style (usually "unknown").
- Writes a merged hanzi_style.yaml back to disk.

We are *not* trying to infer accurate style here yet; this is infrastructure
to centralise style metadata in one place and keep it in sync with the
lexical space defined by CC-Canto → reverse_jyut.yaml.
"""

import argparse
import logging as log
import os
from typing import Dict, List, Any

import yaml


def _project_root() -> str:
    """Return project root (parent of utils/)."""
    here = os.path.abspath(__file__)
    utils_dir = os.path.dirname(here)
    return os.path.dirname(utils_dir)


PROJECT_ROOT = _project_root()
DEFAULT_REVERSE = os.path.join(PROJECT_ROOT, "data", "reverse_jyut.yaml")
DEFAULT_STYLE = os.path.join(PROJECT_ROOT, "data", "hanzi_style.yaml")


def load_reverse(path: str) -> Dict[str, List[str]]:
    """Load reverse_jyut.yaml (Jyutping → [Hanzi, …]) into a dict."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        log.error("reverse_jyut.yaml not found at %s", path)
        raise
    except Exception as e:
        log.error("Failed to load reverse_jyut.yaml from %s: %s", path, e)
        raise

    if not isinstance(data, dict):
        raise TypeError(f"reverse_jyut.yaml has unexpected type {type(data)!r} (expected dict)")

    # Normalise: ensure all values are lists of strings
    norm: Dict[str, List[str]] = {}
    for jy, val in data.items():
        if not isinstance(jy, str):
            continue
        if val is None:
            continue
        if isinstance(val, str):
            items = [val]
        else:
            try:
                items = list(val)
            except TypeError:
                items = [str(val)]
        hz_list: List[str] = []
        for item in items:
            if isinstance(item, str):
                hz = item.strip()
                if hz:
                    hz_list.append(hz)
        if hz_list:
            norm[jy] = hz_list
    return norm


def load_existing_style(path: str) -> Dict[str, Dict[str, Any]]:
    """Load existing hanzi_style.yaml (if any). Return a dict[hanzi]→{style, source,…}."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        log.info("No existing hanzi_style.yaml found at %s; starting fresh.", path)
        return {}
    except Exception as e:
        log.error("Failed to load hanzi_style.yaml from %s: %s", path, e)
        raise

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise TypeError(f"hanzi_style.yaml has unexpected type {type(data)!r} (expected dict)")

    # Ensure each entry is a dict with at least 'style' and 'source' keys
    norm: Dict[str, Dict[str, Any]] = {}
    for hz, info in data.items():
        if not isinstance(hz, str):
            continue
        if not isinstance(info, dict):
            info = {"style": str(info), "source": "legacy"}
        if "style" not in info:
            info["style"] = "unknown"
        if "source" not in info:
            info["source"] = "legacy"
        norm[hz] = info
    return norm


def build_style_index(
        reverse_map: Dict[str, List[str]],
        existing: Dict[str, Dict[str, Any]],
        default_style: str = "unknown",
        source_tag: str = "auto-default",
) -> Dict[str, Dict[str, Any]]:
    """
    Merge reverse_jyut space (all Hanzi seen) with existing hanzi_style.yaml.

    - All existing entries are preserved.
    - Any new Hanzi in reverse_jyut.yaml gets a default style entry.
    """
    style_map: Dict[str, Dict[str, Any]] = dict(existing)  # shallow copy

    all_hanzi = set(style_map.keys())
    new_count = 0

    for jy, hz_list in reverse_map.items():
        if not isinstance(hz_list, list):
            continue
        for hz in hz_list:
            if not isinstance(hz, str):
                continue
            hzs = hz.strip()
            if not hzs:
                continue
            if hzs in all_hanzi:
                continue
            style_map[hzs] = {
                "style": default_style,
                "source": source_tag,
            }
            all_hanzi.add(hzs)
            new_count += 1

    log.info("Style index merge complete: %d existing, %d new → %d total Hanzi.",
             len(existing), new_count, len(style_map))
    return style_map


def save_style(path: str, style_map: Dict[str, Dict[str, Any]]) -> None:
    """Write hanzi_style.yaml with keys sorted."""
    # Sort keys for stable diffs
    ordered = {k: style_map[k] for k in sorted(style_map.keys())}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            ordered,
            f,
            allow_unicode=True,
            sort_keys=True,
            default_flow_style=False,
        )
    log.info("Wrote %d Hanzi style entries to %s", len(ordered), path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or update data/hanzi_style.yaml from data/reverse_jyut.yaml."
    )
    parser.add_argument(
        "--reverse",
        default=DEFAULT_REVERSE,
        help=f"Path to reverse_jyut.yaml (default: {DEFAULT_REVERSE})",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_STYLE,
        help=f"Output path for hanzi_style.yaml (default: {DEFAULT_STYLE})",
    )
    parser.add_argument(
        "--default-style",
        default="unknown",
        choices=["unknown", "colloquial", "written", "both"],
        help="Default style assigned to new Hanzi entries (default: unknown).",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Do not merge existing hanzi_style.yaml; start from scratch.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args()

    log.basicConfig(
        level=log.DEBUG if args.verbose else log.INFO,
        format="%(levelname)s:build_style_index:%(message)s",
    )

    log.info("Using reverse map: %s", args.reverse)
    log.info("Output style file: %s", args.out)

    reverse_map = load_reverse(args.reverse)

    if args.no_merge:
        existing: Dict[str, Dict[str, Any]] = {}
        log.info("Starting from scratch (no merge of existing style file).")
    else:
        existing = load_existing_style(args.out)

    style_map = build_style_index(
        reverse_map,
        existing,
        default_style=args.default_style,
        source_tag="auto-default",
    )
    save_style(args.out, style_map)
    log.info("Done.")


if __name__ == "__main__":
    main()