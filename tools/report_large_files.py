#!/usr/bin/env python3
"""Report files over a line-count threshold, excluding data/."""

from __future__ import annotations

import argparse
from pathlib import Path


def _count_lines(path: Path) -> int:
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except ():
        return 0


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts = {p for p in rel.parts}
    if "data" in parts:
        return True
    if "assets" in parts:
        return True
    if "docs" in parts:
        return True
    if "tests" in parts:
        return True
    if "tools" in parts:
        return True
    if "utils" in parts:
        return True
    if ".git" in parts:
        return True
    if path.suffix == ".ui":
        return True
    if ".venv" in parts or "venv" in parts or "env" in parts:
        return True
    if "site-packages" in parts:
        return True
    if "node_modules" in parts:
        return True
    if "dist" in parts or "build" in parts:
        return True
    if "__pycache__" in parts:
        return True
    if ".idea" in parts:
        return True
    if ".pytest_cache" in parts:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="List files over N lines (excluding data/).")
    parser.add_argument("--threshold", type=int, default=350, help="Line-count threshold.")
    parser.add_argument("--root", type=str, default=".", help="Root directory to scan.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    threshold = int(args.threshold)

    results: list[tuple[int, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip(path, root):
            continue
        n = _count_lines(path)
        if n > threshold:
            results.append((n, path))

    results.sort(key=lambda x: (-x[0], str(x[1]).lower()))

    for n, p in results:
        rel = p.relative_to(root)
        print(f"{n}\t{rel}")

    print(f"\nTotal files over {threshold}: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
