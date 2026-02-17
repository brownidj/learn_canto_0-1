"""Vocab table row model + row building helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TableRow:
    """Single row in vocabulary table."""
    hanzi: str
    jyutping: str
    meanings: str
    categories: list[str]

    def to_list(self) -> list[str]:
        """Convert to list for table display."""
        return [
            self.hanzi,
            self.jyutping,
            self.meanings,
            ", ".join(self.categories) if self.categories else "",
        ]


def build_rows_from_vocab(
    vocab: dict[str, Any],
    categories: dict[str, list[str]],
) -> list[TableRow]:
    """Build TableRow list from vocab + category mapping."""
    rows: list[TableRow] = []

    # Build hanzi -> categories mapping
    hz_to_cats: dict[str, list[str]] = {}
    for cat, members in categories.items():
        for hz in members:
            if hz not in hz_to_cats:
                hz_to_cats[hz] = []
            hz_to_cats[hz].append(cat)

    # Build rows
    for hanzi, data in vocab.items():
        if not isinstance(data, (list, tuple)) or len(data) < 2:
            continue

        meanings_raw, jyutping = data[0], data[1]

        # Flatten meanings
        meanings_list: list[str] = []
        if isinstance(meanings_raw, (list, tuple)):
            for item in meanings_raw:
                if isinstance(item, (list, tuple)):
                    meanings_list.extend(str(x) for x in item if x)
                else:
                    meanings_list.append(str(item))
        else:
            meanings_list.append(str(meanings_raw))

        meanings = ", ".join(m.strip() for m in meanings_list if m.strip())
        cats = hz_to_cats.get(hanzi, [])

        rows.append(
            TableRow(
                hanzi=hanzi,
                jyutping=str(jyutping),
                meanings=meanings,
                categories=sorted(cats, key=lambda s: s.lower()),
            )
        )

    return rows


__all__ = ["TableRow", "build_rows_from_vocab"]
