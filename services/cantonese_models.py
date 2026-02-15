from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CantoneseInfo:
    hanzi: str
    jyutping: str
    meaning_colloquial: str
    register: str
    confidence: float
    notes: str | None = None
    examples: list[dict[str, str]] | None = None
    model: str | None = None
    ts: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hanzi": self.hanzi,
            "jyutping": self.jyutping,
            "meaning_colloquial": self.meaning_colloquial,
            "register": self.register,
            "confidence": float(self.confidence),
            "notes": self.notes or "",
            "examples": list(self.examples or []),
            "model": self.model or "",
            "ts": float(self.ts or 0.0),
        }
