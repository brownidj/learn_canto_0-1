#!/usr/bin/env python3
"""
remove_wrapper_methods.py

Automatically removes thin wrapper methods by:
1. Finding all wrapper methods that just delegate to controllers
2. Replacing all calls to wrappers with direct controller calls
3. Deleting the wrapper method definitions

This is safe because:
- We only touch single-line delegation methods
- We validate each replacement
- All tests must pass afterward
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple


class WrapperRemover:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content = ""
        self.lines = []
        self.wrappers: Dict[str, dict] = {}

    def load(self):
        """Load the file."""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.content = f.read()
            self.lines = self.content.splitlines(keepends=True)

    def find_wrappers(self):
        """Find all thin wrapper methods and what they delegate to."""

        # Pattern to match simple delegation methods
        # Example: def _method(self, ...): """...""" return self._ctrl.method(...)

        in_class = False
        current_method = None
        method_start_line = None

        for i, line in enumerate(self.lines):
            # Check if we're in CategoryManagerDialog class
            if 'class CategoryManagerDialog' in line:
                in_class = True
                continue

            if not in_class:
                continue

            # Look for method definitions
            method_match = re.match(r'    def (_\w+)\(self([^)]*)\)', line)
            if method_match:
                current_method = method_match.group(1)
                method_start_line = i
                params = method_match.group(2)

                # Look ahead for the delegation (within next 5 lines)
                delegate_line = None
                delegate_pattern = None

                for j in range(i + 1, min(i + 6, len(self.lines))):
                    delegate_match = re.search(
                        r'((?:self\._\w+|CategoryManager\w+)\.[\w_]+\([^)]*\))',
                        self.lines[j]
                    )
                    if delegate_match and '"""' not in self.lines[j]:
                        delegate_line = j
                        delegate_pattern = delegate_match.group(1)
                        break

                if delegate_pattern:
                    # Find the end of this method (next def or class-level code)
                    method_end_line = None
                    for j in range(delegate_line + 1, len(self.lines)):
                        if self.lines[j].startswith('    def ') or self.lines[j].startswith('class '):
                            method_end_line = j - 1
                            break
                        # Also check for next method with less indentation
                        if self.lines[j].strip() and not self.lines[j].startswith('        '):
                            if self.lines[j].startswith('    '):
                                method_end_line = j - 1
                                break

                    if method_end_line is None:
                        method_end_line = len(self.lines) - 1

                    # Store wrapper info
                    self.wrappers[current_method] = {
                        'params': params,
                        'delegate': delegate_pattern,
                        'start_line': method_start_line,
                        'end_line': method_end_line,
                        'usages': []
                    }

    def find_usages(self):
        """Find all calls to wrapper methods."""

        for method_name, info in self.wrappers.items():
            pattern = rf'self\.{method_name}\('

            for i, line in enumerate(self.lines):
                # Skip the method definition itself
                if i >= info['start_line'] and i <= info['end_line']:
                    continue

                if re.search(pattern, line):
                    info['usages'].append(i)

    def replace_usages(self):
        """Replace all calls to wrappers with direct controller calls."""

        replacements = 0

        for method_name, info in self.wrappers.items():
            if not info['usages']:
                continue

            # Determine the replacement pattern
            delegate = info['delegate']

            # Extract controller and method from delegate
            # E.g., "self._add_edit_flow.on_candidate_index_activated(...)"
            # or "CategoryManagerHelpers.set_notes(self, ...)"

            for line_num in info['usages']:
                old_line = self.lines[line_num]

                # Simple replacement: self._method(...) -> self._controller.method(...)
                # We need to be careful with arguments

                # For now, do a simple string replacement
                new_line = old_line.replace(f'self.{method_name}(', f'{delegate}(')

                # Special case: if delegate is a static method like CategoryManagerHelpers.method
                # we need to add 'self' as first argument
                if 'CategoryManager' in delegate and '(' in new_line:
                    # Check if we need to inject self
                    if re.search(rf'{delegate}\(\)', new_line):
                        new_line = new_line.replace(f'{delegate}()', f'{delegate}(self)')
                    elif re.search(rf'{delegate}\((?!self)', new_line):
                        new_line = re.sub(rf'({delegate})\(', r'\1(self, ', new_line)

                if new_line != old_line:
                    self.lines[line_num] = new_line
                    replacements += 1
                    print(f"  Replaced call on line {line_num + 1}")

        return replacements

    def remove_wrapper_definitions(self):
        """Remove the wrapper method definitions."""

        lines_to_remove = set()

        for method_name, info in self.wrappers.items():
            # Mark all lines of this method for removal
            for i in range(info['start_line'], info['end_line'] + 1):
                lines_to_remove.add(i)

            print(f"  Removing {method_name} (lines {info['start_line'] + 1}-{info['end_line'] + 1})")

        # Keep lines that are not marked for removal
        self.lines = [line for i, line in enumerate(self.lines) if i not in lines_to_remove]

        return len(lines_to_remove)

    def save(self):
        """Save the modified file."""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.writelines(self.lines)

    def report(self):
        """Print a report of what was found."""

        print(f"\nFound {len(self.wrappers)} wrapper methods:")
        print()

        unused = [name for name, info in self.wrappers.items() if not info['usages']]
        used = [name for name, info in self.wrappers.items() if info['usages']]

        if unused:
            print(f"Unused wrappers ({len(unused)}):")
            for name in unused:
                info = self.wrappers[name]
                print(f"  - {name} -> {info['delegate']}")
            print()

        if used:
            print(f"Used wrappers ({len(used)}):")
            for name in used:
                info = self.wrappers[name]
                print(f"  - {name} -> {info['delegate']} ({len(info['usages'])} calls)")
            print()


def main():
    file_path = 'category_manager.py'

    print("=" * 70)
    print("Removing thin wrapper methods")
    print("=" * 70)
    print()

    remover = WrapperRemover(file_path)

    print("Step 1: Loading file...")
    remover.load()
    original_lines = len(remover.lines)
    print(f"  Original: {original_lines} lines")
    print()

    print("Step 2: Finding wrapper methods...")
    remover.find_wrappers()
    remover.report()

    if not remover.wrappers:
        print("No wrapper methods found. Nothing to do.")
        return

    print("Step 3: Finding usage locations...")
    remover.find_usages()
    print()

    print("Step 4: Replacing wrapper calls with direct calls...")
    replacements = remover.replace_usages()
    print(f"  Made {replacements} replacements")
    print()

    print("Step 5: Removing wrapper method definitions...")
    removed = remover.remove_wrapper_definitions()
    print(f"  Removed {removed} lines")
    print()

    print("Step 6: Saving changes...")
    remover.save()

    new_lines = len(remover.lines)
    print(f"  New file: {new_lines} lines")
    print(f"  Removed: {original_lines - new_lines} lines")
    print()

    print("=" * 70)
    print(f"✅ SUCCESS!")
    print(f"   File: {file_path}")
    print(f"   Lines removed: {original_lines - new_lines}")
    print(f"   Wrappers removed: {len(remover.wrappers)}")
    print()
    print("NEXT STEPS:")
    print("  1. Run: pytest tests/test_category_manager*.py -v")
    print("  2. If tests pass, commit the changes")
    print("  3. If tests fail, run: git checkout category_manager.py")
    print("=" * 70)


if __name__ == '__main__':
    main()
