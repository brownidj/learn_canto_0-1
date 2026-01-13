#!/usr/bin/env python3
"""
analyze_wrapper_methods.py

Finds thin wrapper methods in CategoryManagerDialog that just delegate
to controllers, and identifies which can be removed.

A wrapper method is one that:
1. Has a single line that calls another method
2. Just passes through arguments
3. Adds no logic/transformation
"""

import re
from pathlib import Path
from collections import defaultdict


def find_wrapper_methods(file_path: str) -> dict:
    """Find all thin wrapper methods."""

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all method definitions and their bodies
    method_pattern = r'def (_\w+)\(self[^)]*\)[^:]*:\s*"""[^"]*"""\s*(\w+\.\w+\([^)]*\))'

    wrappers = {}

    for match in re.finditer(method_pattern, content):
        method_name = match.group(1)
        delegate_call = match.group(2)
        wrappers[method_name] = delegate_call

    return wrappers


def find_method_usages(file_path: str, method_name: str) -> list[str]:
    """Find where a method is called."""

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    usages = []
    pattern = rf'self\.{method_name}\('

    for i, line in enumerate(lines, 1):
        if re.search(pattern, line) and 'def ' not in line:
            usages.append(f"Line {i}: {line.strip()}")

    return usages


def main():
    file_path = 'category_manager.py'

    print("=" * 70)
    print("Analyzing thin wrapper methods in CategoryManagerDialog")
    print("=" * 70)
    print()

    wrappers = find_wrapper_methods(file_path)

    print(f"Found {len(wrappers)} potential wrapper methods:")
    print()

    unused = []
    used = []

    for method_name, delegate in wrappers.items():
        usages = find_method_usages(file_path, method_name)

        if not usages:
            unused.append((method_name, delegate))
            print(f"❌ UNUSED: {method_name}")
            print(f"   Delegates to: {delegate}")
            print()
        else:
            used.append((method_name, delegate, usages))
            print(f"✓ USED: {method_name} ({len(usages)} call(s))")
            print(f"   Delegates to: {delegate}")
            for usage in usages[:3]:  # Show first 3
                print(f"   {usage}")
            if len(usages) > 3:
                print(f"   ... and {len(usages) - 3} more")
            print()

    print("=" * 70)
    print(f"Summary:")
    print(f"  Total wrappers: {len(wrappers)}")
    print(f"  Used: {len(used)}")
    print(f"  Unused (can delete): {len(unused)}")
    print("=" * 70)
    print()

    if unused:
        print("RECOMMENDATION: Delete these unused wrapper methods:")
        for method_name, delegate in unused:
            print(f"  - {method_name}")

    if used:
        print()
        print("RECOMMENDATION: Replace direct calls in callers:")
        print("  Instead of: self._method(...)")
        print("  Use: self._controller.method(...)")
        print("  Then delete the wrapper.")


if __name__ == '__main__':
    main()
