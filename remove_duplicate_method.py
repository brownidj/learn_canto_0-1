#!/usr/bin/env python3
"""
remove_duplicate_method.py

Surgically removes the first (massive) _build_add_entry_preview method
from category_manager.py, keeping only the proper delegation version.

This script:
1. Reads the file
2. Finds the duplicate method definitions
3. Removes the first (400+ line) version
4. Keeps the second (delegation) version
5. Writes the cleaned file back
"""

import re
import sys
from pathlib import Path


def remove_duplicate_method(file_path: str) -> tuple[bool, str, int]:
    """
    Remove the first _build_add_entry_preview method (the massive inline one).

    Returns:
        (success, message, lines_removed)
    """
    path = Path(file_path)

    if not path.exists():
        return False, f"File not found: {file_path}", 0

    # Read the file
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    original_count = len(lines)
    print(f"Original file: {original_count} lines")

    # Find the first _build_add_entry_preview method
    first_method_start = None
    first_method_end = None
    second_method_start = None

    for i, line in enumerate(lines):
        # Look for method definitions
        if 'def _build_add_entry_preview(self) -> dict:' in line:
            if first_method_start is None:
                first_method_start = i
                print(f"Found first _build_add_entry_preview at line {i + 1}")
            else:
                second_method_start = i
                print(f"Found second _build_add_entry_preview at line {i + 1}")
                break

    if first_method_start is None:
        return False, "Could not find _build_add_entry_preview method", 0

    if second_method_start is None:
        return False, "Could not find second _build_add_entry_preview method", 0

    # Find the end of the first method (the line with just "return" before the second method)
    # We need to find the last "return" statement in the first method
    for i in range(second_method_start - 1, first_method_start, -1):
        line = lines[i].strip()
        if line == "return":
            first_method_end = i
            print(f"Found end of first method at line {i + 1}")
            break

    if first_method_end is None:
        return False, "Could not find end of first method", 0

    # Also look for _do_category_commit_internal stub to remove
    stub_start = None
    stub_end = None

    for i in range(first_method_end + 1, second_method_start):
        if 'def _do_category_commit_internal(self)' in lines[i]:
            stub_start = i
            print(f"Found _do_category_commit_internal stub at line {i + 1}")
            # Find the end of this short method (next method def or end of indentation)
            for j in range(i + 1, second_method_start):
                if lines[j].strip() and not lines[j].startswith(' '):
                    stub_end = j - 1
                    break
                if 'def ' in lines[j] and lines[j].startswith('    def '):
                    stub_end = j - 1
                    break
            if stub_end is None:
                stub_end = second_method_start - 1
            print(f"Found end of stub at line {stub_end + 1}")
            break

    # Calculate what to remove
    lines_to_remove = []

    # Remove first method (including its definition line through return)
    lines_to_remove.extend(range(first_method_start, first_method_end + 1))

    # Remove stub if found
    if stub_start is not None and stub_end is not None:
        lines_to_remove.extend(range(stub_start, stub_end + 1))

    lines_to_remove = sorted(set(lines_to_remove))
    lines_removed_count = len(lines_to_remove)

    print(f"\nWill remove {lines_removed_count} lines:")
    print(f"  - First method: lines {first_method_start + 1} to {first_method_end + 1}")
    if stub_start is not None:
        print(f"  - Stub method: lines {stub_start + 1} to {stub_end + 1}")

    # Create new file content (keep lines not in removal list)
    new_lines = [lines[i] for i in range(len(lines)) if i not in lines_to_remove]

    new_count = len(new_lines)
    print(f"\nNew file: {new_count} lines ({original_count - new_count} lines removed)")
    print(f"Reduction: {(original_count - new_count) / original_count * 100:.1f}%")

    # Write back
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    return True, f"Successfully removed {lines_removed_count} lines", lines_removed_count


def main():
    """Main entry point."""
    file_path = 'category_manager.py'

    print(f"=" * 70)
    print(f"Removing duplicate _build_add_entry_preview method")
    print(f"=" * 70)
    print()

    success, message, lines_removed = remove_duplicate_method(file_path)

    print()
    print("=" * 70)
    if success:
        print(f"✅ SUCCESS: {message}")
        print(f"   File: {file_path}")
        print(f"   Lines removed: {lines_removed}")
    else:
        print(f"❌ FAILED: {message}")
        sys.exit(1)
    print("=" * 70)


if __name__ == '__main__':
    main()
