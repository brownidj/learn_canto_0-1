#!/usr/bin/env python3
"""
bulk_update_hanzi_style.py

Scan data/hanzi_style.yaml for entries with style: unknown (or clearly auto-default),
call ChatGPT in batches (via label_hanzi_style.call_chatgpt) to propose style labels,
and update hanzi_style.yaml in-place.

Usage examples (from project root):

  # Simple run, label up to 50 unknown entries
  .venv/bin/python3 utils/bulk_update_hanzi_style.py --max 50 --verbose

  # Dry-run: just print the YAML fragment that *would* be applied
  .venv/bin/python3 utils/bulk_update_hanzi_style.py --max 20 --dry-run

Requires:
  - OPENAI_API_KEY in the environment
  - openai Python package installed
  - utils/label_hanzi_style.py available in the same directory
"""

import argparse
import logging as log
import os
import sys
import time
from typing import Dict, Any, List

import yaml
from dotenv import load_dotenv

load_dotenv()

# Reuse the classifier helper from the first utility
from label_hanzi_style import call_chatgpt, STYLE_VOCAB  # type: ignore[import]


def _project_root() -> str:
    """Return project root (parent of utils/)."""
    here = os.path.abspath(__file__)
    utils_dir = os.path.dirname(here)
    return os.path.dirname(utils_dir)


PROJECT_ROOT = _project_root()
DEFAULT_STYLE_PATH = os.path.join(PROJECT_ROOT, "data", "hanzi_style.yaml")


def load_style_map(path: str) -> Dict[str, Dict[str, Any]]:
    """Load hanzi_style.yaml into a dict[hanzi] -> {style, source, ...}."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        log.error("Style file not found at %s", path)
        raise
    except Exception as e:
        log.error("Failed to load %s: %s", path, e)
        raise

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise TypeError(f"Style file has unexpected type {type(data)!r} (expected dict)")

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


def save_style_map(path: str, style_map: Dict[str, Dict[str, Any]]) -> None:
    """Write hanzi_style.yaml with sorted keys."""
    ordered = {k: style_map[k] for k in sorted(style_map.keys())}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            ordered,
            f,
            allow_unicode=True,
            sort_keys=True,
            default_flow_style=False,
        )
    log.info("Wrote %d entries to %s", len(ordered), path)


def choose_candidates(style_map: Dict[str, Dict[str, Any]], limit: int | None) -> List[str]:
    """
    Return a list of Hanzi keys that are eligible for ChatGPT style labelling.

    Rules:
      - style == 'unknown' OR (style is empty/whitespace)
      - AND source starts with 'auto-' (we do not touch manual-core, manual, etc.)
    """
    candidates: List[str] = []

    for hz, info in style_map.items():
        style_val = str(info.get("style", "") or "").strip()
        src_val = str(info.get("source", "") or "").strip()

        # Only consider unknown / empty style
        if style_val and style_val != "unknown":
            continue

        # Only touch auto-generated entries, not manual ones
        if not src_val.startswith("auto-"):
            continue

        candidates.append(hz)

    # Deterministic order: sort by Hanzi
    candidates.sort()

    # If limit is None or <= 0, treat as "no limit" and return all candidates
    if limit is not None and limit > 0:
        return candidates[:limit]
    return candidates


def batch(iterable: List[str], size: int) -> List[List[str]]:
    """Chunk a list into batches of at most size."""
    if size <= 0:
        return [iterable]
    return [iterable[i : i + size] for i in range(0, len(iterable), size)]


def apply_results(
        style_map: Dict[str, Dict[str, Any]],
        results: List[Dict[str, str]],
        dry_run: bool,
) -> int:
    """
    Apply ChatGPT results to style_map in-place.

    Returns the number of entries that were (or would be) updated.
    If dry_run=True, just log/print the corresponding YAML snippet.
    """
    if dry_run:
        # Print YAML fragment only
        for item in results:
            hz = item["hanzi"]
            style_val = item["style"]
            key = f"'{hz}'" if ("\n" in hz or ":" in hz) else hz
            print(f"{key}:")
            print("  source: chatgpt-style")
            print(f"  style: {style_val}")
            print()
        log.info("Dry-run: would update %d entries.", len(results))
        return len(results)

    updated = 0
    for item in results:
        hz = item["hanzi"]
        style_val = item["style"]

        info = style_map.get(hz)
        if info is None:
            # This shouldn't normally happen, but be defensive
            style_map[hz] = {
                "style": style_val,
                "source": "chatgpt-style",
            }
            updated += 1
            continue

        # Respect manual entries: only overwrite auto-* ones
        src_val = str(info.get("source", "") or "").strip()
        if not src_val.startswith("auto-") and src_val != "chatgpt-style":
            log.debug("Skipping %s (source=%s): manual entry not overwritten.", hz, src_val)
            continue

        info["style"] = style_val
        info["source"] = "chatgpt-style"
        updated += 1

    log.info("Applied ChatGPT styles to %d entries.", updated)
    return updated


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-update style: unknown entries in hanzi_style.yaml using ChatGPT."
    )
    parser.add_argument(
        "--style-file",
        default=DEFAULT_STYLE_PATH,
        help=f"Path to hanzi_style.yaml (default: {DEFAULT_STYLE_PATH})",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=50,
        help="Maximum number of unknown entries to label in this run (<= 0 means no limit; default: 50).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of Hanzi items per ChatGPT request (default: 20).",
    )
    parser.add_argument(
        "--sleep-sec",
        type=float,
        default=1.0,
        help="Seconds to sleep between ChatGPT batches to respect rate limits (default: 1.0).",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="gpt-4.1-mini",
        help="OpenAI model to use (default: gpt-4.1-mini).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify hanzi_style.yaml; print YAML fragment instead.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    log.basicConfig(
        level=log.DEBUG if args.verbose else log.INFO,
        format="%(levelname)s:bulk_update_hanzi_style:%(message)s",
    )

    style_map = load_style_map(args.style_file)

    # Count how many entries are currently eligible for auto labelling
    total_eligible_before = len(choose_candidates(style_map, limit=None))
    if total_eligible_before == 0:
        log.info("No eligible unknown/auto-* entries found; nothing to do.")
        return

    # Derive an effective maximum for this run.
    # If --max is non-positive, treat it as "process all eligible entries in one run".
    if args.max is None or args.max <= 0:
        effective_max = total_eligible_before
        log.info(
            "Non-positive --max (%s) supplied; processing all %d eligible entries in this run.",
            args.max,
            effective_max,
        )
    else:
        effective_max = min(args.max, total_eligible_before)

    # Now select the subset we will process in this run (respecting effective_max)
    candidates = choose_candidates(style_map, limit=effective_max)
    if not candidates:
        log.info(
            "No candidates selected for this run (effective max=%d); nothing to do.",
            effective_max,
        )
        return

    log.info(
        "Selected %d candidate Hanzi entries for style labelling (of %d total eligible).",
        len(candidates),
        total_eligible_before,
    )

    all_results: List[Dict[str, str]] = []

    groups = batch(candidates, args.batch_size)
    total_batches = len(groups)

    for idx, group in enumerate(groups, start=1):
        log.info("Calling ChatGPT for batch %d/%d (%d items)…", idx, total_batches, len(group))
        results = call_chatgpt(group, model=args.model)
        log.info("ChatGPT returned %d labelled items for batch %d.", len(results), idx)
        all_results.extend(results)

        # Be gentle with the API: sleep a little between batches.
        if args.sleep_sec > 0 and idx < total_batches:
            log.debug("Sleeping %.2f seconds between batches to respect rate limits.", args.sleep_sec)
            time.sleep(args.sleep_sec)

    updated = apply_results(style_map, all_results, dry_run=args.dry_run)

    processed = len(all_results)
    total_entries = len(style_map)
    processed_not_updated = max(processed - updated, 0)

    if args.dry_run:
        remaining = total_eligible_before  # no changes applied in dry-run
        log.info(
            "Dry-run complete. Total entries: %d. Eligible before run: %d. "
            "Would process %d entries in this run; would update %d, leave %d unchanged. "
            "Unknown/auto-* entries remaining after run (hypothetical): %d.",
            total_entries,
            total_eligible_before,
            processed,
            updated,
            processed_not_updated,
            remaining,
        )
        return

    # For a real run, persist the updated map and report how many unknowns remain.
    remaining = len(choose_candidates(style_map, limit=None))
    save_style_map(args.style_file, style_map)
    log.info(
        "Bulk style update complete. Total entries: %d. Eligible before run: %d. "
        "Processed this run: %d. Updated: %d. Unchanged but processed: %d. "
        "Remaining unknown/auto-* entries: %d.",
        total_entries,
        total_eligible_before,
        processed,
        updated,
        processed_not_updated,
        remaining,
    )


if __name__ == "__main__":
    main()