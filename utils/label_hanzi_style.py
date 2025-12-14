#!/usr/bin/env python3
"""
Utility: ask ChatGPT to label Hanzi entries with style information.

Usage (from project root):

  .venv/bin/python3 utils/label_hanzi_style.py "紅色" "粉紅" "米色"

or:

  .venv/bin/python3 utils/label_hanzi_style.py --file data/hanzi_list.txt

The script prints a YAML fragment you can paste into hanzi_style.yaml.
"""

import argparse
import sys
from typing import List, Dict

from openai import OpenAI

STYLE_VOCAB = [
    "colloquial-core",
    "colloquial-casual",
    "written-formal",
    "function-word",
    "slang",
    "taboo",
    "both colloquial and written",
    "unknown",
]


def build_system_prompt() -> str:
    """Return the system prompt describing the style labelling task."""
    vocab_str = "\n".join(f"- {label}" for label in STYLE_VOCAB)
    return (
        "You are an expert in Cantonese lexicography.\n"
        "Your task is to assign a style label to each given Hanzi word/phrase.\n\n"
        "Use ONLY one of these labels:\n"
        f"{vocab_str}\n\n"
        "Definitions (informal):\n"
        "- colloquial-core: very common in everyday spoken Cantonese.\n"
        "- colloquial-casual: informal / spoken, but not part of the core day-to-day set.\n"
        "- written-formal: mainly used in written / formal contexts, not natural speech.\n"
        "- function-word: grammatical items (particles, pronouns, etc.).\n"
        "- slang: informal / youth / internet slang.\n"
        "- taboo: offensive, vulgar, or very coarse.\n"
        "- both colloquial and written: widely used in both speech and standard writing.\n"
        "- unknown: you are genuinely unsure.\n\n"
        "Output STRICTLY in JSON of the form:\n"
        '{\"items\": [{\"hanzi\": \"…\", \"style\": \"…\"}, …]}'
    )


def build_user_prompt(items: List[str]) -> str:
    """Build the user prompt listing the items to classify."""
    lines = ["Label the style for these Hanzi items:", ""]
    for h in items:
        lines.append(f"- {h}")
    return "\n".join(lines)


def call_chatgpt(hanzi_items: List[str], model: str = "gpt-4.1-mini") -> List[Dict[str, str]]:
    """
    Call the ChatGPT API to get style labels.

    Returns a list of dicts: {"hanzi": str, "style": str}
    """
    client = OpenAI()

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(hanzi_items)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )

    content = resp.choices[0].message.content
    if content is None:
        raise RuntimeError("Empty response from ChatGPT")

    import json

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse JSON from ChatGPT response: {content!r}") from exc

    items = data.get("items", [])
    results: List[Dict[str, str]] = []

    for item in items:
        hanzi = str(item.get("hanzi", "")).strip()
        style = str(item.get("style", "")).strip()
        if not hanzi:
            continue
        if style not in STYLE_VOCAB:
            # Safety fallback: if model invents a label, normalise to unknown
            style = "unknown"
        results.append({"hanzi": hanzi, "style": style})

    return results


def print_yaml_fragment(items: List[Dict[str, str]]) -> None:
    """
    Print a YAML fragment suitable for pasting into hanzi_style.yaml.

    Each entry looks like:

      紅色:
        source: chatgpt-style
        style: both colloquial and written
    """
    for item in items:
        hanzi = item["hanzi"]
        style = item["style"]
        # Tiny safeguard against weird keys
        if "\n" in hanzi or ":" in hanzi:
            # You can improve this later with proper YAML escaping if needed
            hanzi_key = f"'{hanzi}'"
        else:
            hanzi_key = hanzi

        print(f"{hanzi_key}:")
        print("  source: chatgpt-style")
        print(f"  style: {style}")
        print()


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Ask ChatGPT to classify Hanzi items by style and output YAML fragments."
    )
    parser.add_argument(
        "hanzi",
        nargs="*",
        help="Hanzi items to classify (e.g. 紅色 粉紅 米色).",
    )
    parser.add_argument(
        "--file",
        "-f",
        metavar="PATH",
        help="Text file with one Hanzi item per line (blank lines ignored).",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="gpt-4.1-mini",
        help="OpenAI model to use (default: gpt-4.1-mini).",
    )
    return parser.parse_args(argv)


def load_hanzi_from_file(path: str) -> List[str]:
    """Load Hanzi items from a text file (one per line)."""
    items: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            items.append(s)
    return items


def main(argv: List[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    hanzi_items: List[str] = []
    if args.file:
        hanzi_items.extend(load_hanzi_from_file(args.file))
    if args.hanzi:
        hanzi_items.extend(args.hanzi)

    if not hanzi_items:
        print("No Hanzi items provided. Use positional args or --file.", file=sys.stderr)
        sys.exit(1)

    # De-duplicate while preserving order
    seen = set()
    unique_items: List[str] = []
    for h in hanzi_items:
        if h not in seen:
            seen.add(h)
            unique_items.append(h)

    results = call_chatgpt(unique_items, model=args.model)
    print_yaml_fragment(results)


if __name__ == "__main__":
    main()