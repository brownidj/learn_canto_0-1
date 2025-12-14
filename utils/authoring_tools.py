

"""
Authoring tools for LearnCanto_01 vocabulary data.

This module provides a simple CLI and helper functions to validate and inspect
the unified vocab.yaml file that contains both category definitions and
entries.

Usage (from project root):

    (.venv) python3 -m utils.authoring_tools --path vocab.yaml

or:

    (.venv) python3 utils/authoring_tools.py --path vocab.yaml
"""

import os
import sys
import argparse

import yaml


def load_vocab(path):
    """Load vocab.yaml from the given path.

    Returns the loaded object (dict) or None if loading/parsing fails.
    """
    if not os.path.exists(path):
        print("ERROR: vocab file not found at: {0}".format(path))
        return None

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print("ERROR: Failed to parse YAML: {0}".format(e))
            return None

    if data is None:
        data = {}
    return data


def validate_structure(vocab):
    """Validate the top-level structure of the vocab data.

    Returns (errors, warnings) as lists of strings.
    """
    errors = []
    warnings = []

    if not isinstance(vocab, dict):
        errors.append("Top-level YAML is not a mapping (expected a dict).")
        return errors, warnings

    if "categories" not in vocab:
        errors.append("Missing top-level 'categories' mapping.")
    if "entries" not in vocab:
        errors.append("Missing top-level 'entries' mapping.")

    categories = vocab.get("categories", {}) or {}
    entries = vocab.get("entries", {}) or {}

    if categories and not isinstance(categories, dict):
        errors.append("'categories' should be a mapping of key -> metadata dict.")
    if entries and not isinstance(entries, dict):
        errors.append("'entries' should be a mapping of jyutping-key -> entry dict.")

    return errors, warnings


def analyse_vocab(vocab):
    """Return (errors, warnings, summary) describing issues in vocab.yaml.

    summary is a dict with keys:
        - defined_categories
        - used_categories
        - undefined_categories
        - unused_categories
        - entries_without_categories
        - senses_missing_fields
    """
    errors = []
    warnings = []

    categories = vocab.get("categories", {}) or {}
    entries = vocab.get("entries", {}) or {}

    defined_cats = set(categories.keys())
    used_cats = set()

    entries_without_categories = []
    senses_missing_fields = []

    for key, entry in entries.items():
        if not isinstance(entry, dict):
            errors.append("Entry '{0}' should be a mapping.".format(key))
            continue

        jy = entry.get("jyutping")
        senses = entry.get("senses")

        if jy is None:
            warnings.append("Entry '{0}' has no 'jyutping' field.".format(key))

        if not isinstance(senses, list) or not senses:
            warnings.append("Entry '{0}' has no 'senses' list.".format(key))
            continue

        for idx, sense in enumerate(senses):
            if not isinstance(sense, dict):
                errors.append(
                    "Entry '{0}' sense {1} is not a mapping.".format(key, idx)
                )
                continue

            hanzi = sense.get("hanzi")
            gloss = sense.get("gloss")
            cats = sense.get("categories")

            if hanzi is None or gloss is None:
                senses_missing_fields.append((key, idx, hanzi, gloss))

            if not cats:
                entries_without_categories.append((key, idx, hanzi))
            else:
                if not isinstance(cats, list):
                    errors.append(
                        "Entry '{0}' sense {1} 'categories' should be a list.".format(
                            key, idx
                        )
                    )
                else:
                    for cat in cats:
                        used_cats.add(cat)

    undefined_cats = used_cats.difference(defined_cats)
    unused_cats = defined_cats.difference(used_cats)

    summary = {
        "defined_categories": sorted(defined_cats),
        "used_categories": sorted(used_cats),
        "undefined_categories": sorted(undefined_cats),
        "unused_categories": sorted(unused_cats),
        "entries_without_categories": entries_without_categories,
        "senses_missing_fields": senses_missing_fields,
    }

    return errors, warnings, summary


def print_report(errors, warnings, summary):
    """Pretty-print a validation report for humans."""
    print("=== vocab.yaml validation report ===")

    if errors:
        print("")
        print("ERRORS:")
        for e in errors:
            print("  - {0}".format(e))
    else:
        print("")
        print("No structural errors found.")

    if warnings:
        print("")
        print("WARNINGS:")
        for w in warnings:
            print("  - {0}".format(w))

    undefined = summary.get("undefined_categories", [])
    unused = summary.get("unused_categories", [])
    missing_cat_senses = summary.get("entries_without_categories", [])
    missing_fields = summary.get("senses_missing_fields", [])

    if undefined:
        print("")
        print("Categories used in senses but not defined in 'categories':")
        for cat in undefined:
            print("  - {0}".format(cat))

    if unused:
        print("")
        print("Categories defined but never used in any sense:")
        for cat in unused:
            print("  - {0}".format(cat))

    if missing_cat_senses:
        print("")
        print("Senses with no categories (treated as 'unassigned'):")
        for key, idx, hanzi in missing_cat_senses:
            print(
                "  - entry='{0}', sense={1}, hanzi={2}".format(
                    key, idx, hanzi
                )
            )

    if missing_fields:
        print("")
        print("Senses missing 'hanzi' or 'gloss':")
        for key, idx, hanzi, gloss in missing_fields:
            print(
                "  - entry='{0}', sense={1}, hanzi={2}, gloss={3}".format(
                    key, idx, repr(hanzi), repr(gloss)
                )
            )


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate and inspect the vocab.yaml authoring file."
    )
    parser.add_argument(
        "--path",
        default="../vocab.yaml",
        help="Path to vocab.yaml (default: vocab.yaml)",
    )
    args = parser.parse_args(argv)

    vocab = load_vocab(args.path)
    if vocab is None:
        return 1

    struct_errors, struct_warnings = validate_structure(vocab)
    errors = list(struct_errors)
    warnings = list(struct_warnings)

    if not errors:
        extra_errors, extra_warnings, summary = analyse_vocab(vocab)
        errors.extend(extra_errors)
        warnings.extend(extra_warnings)
    else:
        summary = {
            "defined_categories": [],
            "used_categories": [],
            "undefined_categories": [],
            "unused_categories": [],
            "entries_without_categories": [],
            "senses_missing_fields": [],
        }

    print_report(errors, warnings, summary)

    # Non-zero exit if there are hard errors
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())