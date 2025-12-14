#!/usr/bin/env python3
"""
Utility: build_reverse_jyut.py

Generate a comprehensive reverse Jyutping → Hanzi index
by reading CC‑Canto raw data through utils.get_cccanto_reverse_map().

Output is written to data/reverse_jyut.yaml.
"""

import os
import sys
import argparse
import logging
import yaml

# Import utils from project root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from utils.utils import get_cccanto_reverse_map
except Exception:
    print("ERROR: Could not import utils.get_cccanto_reverse_map")
    sys.exit(1)


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger("build_reverse_jyut")


def _coerce_entry(jy_key, hanzi, gloss_list, out_map, max_glosses):
    """
    Normalise and append a single reverse entry.

    After simplification, the output schema for reverse_jyut.yaml is:

        {
            "jyutping-key": ["漢字1", "漢字2", ...],
            ...
        }

    We no longer store glosses or source metadata here; this file is a
    pure, fast Jyutping → Hanzi index.
    """
    if not isinstance(jy_key, str) or not isinstance(hanzi, str):
        return

    # Normalise Hanzi string
    hanzi = hanzi.strip()
    if not hanzi:
        return

    bucket = out_map.setdefault(jy_key, [])
    # Avoid duplicates for the same Jyutping key
    if hanzi not in bucket:
        bucket.append(hanzi)


def build_reverse(cc_map, max_glosses=6, verbose=False):
    """
    Convert the mapping returned by get_cccanto_reverse_map()
    into a uniform structure suitable for saving.
    """
    out = {}
    n_keys = len(cc_map)
    if verbose:
        log.info("Normalising CC‑Canto map: %d keys", n_keys)

    for idx, (jy, entry) in enumerate(cc_map.items()):
        # Log a few sample entries so we can see the real structure
        if verbose and idx < 5:
            log.debug("Sample entry[%d]: key=%r type=%s value=%r",
                      idx, jy, type(entry).__name__, entry)

        # Possibility 1: { jy: {hanzi: [gloss,...], ...} }
        if isinstance(entry, dict):
            for hz, glosses in entry.items():
                _coerce_entry(jy, hz, glosses, out, max_glosses)

        # Possibility 2: { jy: [ ... ] } with various shapes
        elif isinstance(entry, (list, tuple)):
            for item in entry:
                # 2a) list/tuple of dict-like items
                if isinstance(item, dict):
                    hz = (item.get("hanzi") or
                          item.get("hz") or
                          item.get("char") or
                          item.get("ch"))
                    glosses = (item.get("glosses") or
                               item.get("senses") or
                               item.get("meanings") or
                               item.get("defs"))
                    if hz:
                        _coerce_entry(jy, hz, glosses, out, max_glosses)
                    continue

                # 2b) tuple/list like (hanzi, glosses?)
                if isinstance(item, (list, tuple)) and item:
                    hz = str(item[0])
                    glosses = item[1] if len(item) > 1 else []
                    _coerce_entry(jy, hz, glosses, out, max_glosses)
                    continue

                # 2c) bare string items, treat as Hanzi with no glosses
                if isinstance(item, str):
                    _coerce_entry(jy, item, [], out, max_glosses)
                    continue

                if verbose:
                    log.debug("Skipping unexpected list item for %r: %r (type=%s)",
                              jy, item, type(item).__name__)

        # Possibility 3: bare string entry, treat as Hanzi with no glosses
        elif isinstance(entry, str):
            _coerce_entry(jy, entry, [], out, max_glosses)

        else:
            # Unexpected structure; skip quietly but log in verbose mode
            if verbose:
                log.warning("Skipping unexpected entry for %r: %r (type=%s)",
                            jy, entry, type(entry).__name__)

    if verbose:
        log.info("Normalised %d Jyutping keys.", len(out))
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Build reverse Jyutping → Hanzi index from CC‑Canto."
    )
    parser.add_argument("--out", default="data/reverse_jyut.yaml",
                        help="Output YAML file path.")
    parser.add_argument("--cccanto", default=None,
                        help="Path to CC-Canto source file (optional; default is handled by utils.get_cccanto_reverse_map).")
    parser.add_argument("--max-glosses", type=int, default=6,
                        help="Limit number of glosses per entry.")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose logging output.")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    if args.cccanto:
        # Resolve relative path against project root
        ccc_path = args.cccanto
        if not os.path.isabs(ccc_path):
            ccc_path = os.path.join(PROJECT_ROOT, ccc_path)
        log.info("Loading CC-Canto reverse map from %s", ccc_path)
        try:
            # Prefer a path-aware signature if available
            try:
                ccc_map = get_cccanto_reverse_map(ccc_path)
            except TypeError:
                log.warning("get_cccanto_reverse_map() does not accept a path; falling back to no-arg call.")
                ccc_map = get_cccanto_reverse_map()
        except Exception as e:
            log.error("Failed to load CC-Canto (path aware): %s", e)
            sys.exit(1)
    else:
        log.info("Loading CC-Canto reverse map using utils.get_cccanto_reverse_map() defaults.")
        try:
            ccc_map = get_cccanto_reverse_map()
        except Exception as e:
            log.error("Failed to load CC-Canto: %s", e)
            sys.exit(1)

    # Basic format validation
    if not isinstance(ccc_map, dict):
        log.error("CC-Canto reverse map has unexpected type %r (expected dict-like).", type(ccc_map))
        sys.exit(1)
    if not ccc_map:
        log.error("CC-Canto reverse map is empty; aborting.")
        sys.exit(1)
    log.info("Loaded CC-Canto reverse map with %d Jyutping keys.", len(ccc_map))

    log.info("Building reverse index…")
    reverse_map = build_reverse(ccc_map,
                                max_glosses=args.max_glosses,
                                verbose=args.verbose)

    out_path = os.path.join(PROJECT_ROOT, args.out)
    out_dir = os.path.dirname(out_path)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    log.info("Writing %d keys to %s", len(reverse_map), out_path)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(reverse_map, f, allow_unicode=True, sort_keys=True)
        log.info("Done.")
    except Exception as e:
        log.error("Failed writing output: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()