"""List theme colors and where they're used in the Qt stylesheet."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


_BLOCK_RE = re.compile(r"(?s)([^{}]+)\{([^{}]+)\}")
_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def _extract_stylesheet(text: str) -> str:
    # Pull the triple-quoted stylesheet inside _apply_victoria_harbour_theme.
    # This is intentionally simple and scoped to the current file layout.
    m = re.search(
        r"_apply_victoria_harbour_theme\(.*?app\.setStyleSheet\(\s*\"\"\"(.*?)\"\"\"\s*\)",
        text,
        re.S,
    )
    if not m:
        raise SystemExit("Could not find stylesheet in _apply_victoria_harbour_theme.")
    return m.group(1)


def _parse_stylesheet(stylesheet: str) -> dict[str, list[tuple[str, str]]]:
    # color -> list of (selector, property)
    uses: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for selector, body in _BLOCK_RE.findall(stylesheet):
        selector = " ".join(selector.split())
        for line in body.split(";"):
            line = line.strip()
            if not line or ":" not in line:
                continue
            prop, value = [s.strip() for s in line.split(":", 1)]
            for color in _COLOR_RE.findall(value):
                uses[color.lower()].append((selector, prop))

    return uses


def _format_output(uses: dict[str, list[tuple[str, str]]]) -> str:
    lines = []
    for color in sorted(uses.keys()):
        lines.append(f"{color}")
        for selector, prop in sorted(uses[color], key=lambda x: (x[0], x[1])):
            lines.append(f"  {selector} -> {prop}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _show_ui(uses: dict[str, list[tuple[str, str]]]) -> int:
    app = QApplication([])

    root = QWidget()
    root.setWindowTitle("Theme Colors")
    layout = QVBoxLayout(root)
    title = QLabel("Victoria Harbour Theme Colors")
    layout.addWidget(title)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    layout.addWidget(scroll)

    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(6, 6, 6, 6)
    content_layout.setSpacing(12)

    colors = sorted(uses.keys())
    swatch_size = 72

    for idx, color in enumerate(colors):
        cell = QWidget()
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(4, 4, 4, 4)
        cell_layout.setSpacing(6)

        swatch = QLabel()
        swatch.setFixedSize(swatch_size, swatch_size)
        swatch.setAutoFillBackground(True)
        palette = swatch.palette()
        palette.setColor(QPalette.Window, QColor(color))
        swatch.setPalette(palette)
        swatch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        label = QLabel(color)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        usage_lines = []
        for selector, prop in sorted(uses[color], key=lambda x: (x[0], x[1])):
            usage_lines.append(f"{selector} -> {prop}")
        usage = QLabel("\n".join(usage_lines))
        usage.setWordWrap(True)

        cell_layout.addWidget(swatch)
        cell_layout.addWidget(label)
        cell_layout.addWidget(usage)
        content_layout.addWidget(cell)

    scroll.setWidget(content)
    root.resize(520, 700)
    root.show()
    return app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="Show theme colors and their selectors.")
    parser.add_argument(
        "--file",
        default="app/main_window.py",
        help="Path to file containing _apply_victoria_harbour_theme.",
    )
    parser.add_argument(
        "--group",
        action="store_true",
        help="Group output by selector instead of by color.",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Show a small UI with color blocks instead of printing.",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        repo_root = Path(__file__).resolve().parent.parent
        path = (repo_root / path).resolve()
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    stylesheet = _extract_stylesheet(text)
    uses = _parse_stylesheet(stylesheet)

    if args.ui:
        return _show_ui(uses)
    if args.group:
        grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for color, entries in uses.items():
            for selector, prop in entries:
                grouped[selector].append((prop, color))

        lines = []
        for selector in sorted(grouped.keys()):
            lines.append(selector)
            for prop, color in sorted(grouped[selector], key=lambda x: (x[0], x[1])):
                lines.append(f"  {prop} -> {color}")
            lines.append("")
        output = "\n".join(lines).rstrip() + "\n"
    else:
        output = _format_output(uses)

    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
