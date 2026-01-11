

from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class AddEntryPreview:
    jyutping: str
    hanzi: str
    meaning: str
    category: str

    # Legacy/test aliases (do not remove)
    @property
    def gloss(self) -> str:
        return self.meaning

    @property
    def categories(self) -> List[str]:
        return [self.category] if self.category else []


class AddEntryPreviewBuilder:
    """
    UI-free builder that constructs an AddEntryPreview payload from
    already-read dialog field values.
    """

    def __init__(
        self,
        *,
        jyutping: str,
        hanzi: str,
        meaning: str,
        category: str,
    ) -> None:
        self.jyutping = (jyutping or "").strip()
        self.hanzi = (hanzi or "").strip()
        self.meaning = (meaning or "").strip()
        self.category = (category or "").strip()

    def is_valid(self) -> bool:
        return bool(self.jyutping and self.hanzi and self.meaning and self.category)

    def build(self) -> Optional[AddEntryPreview]:
        if not self.is_valid():
            return None
        return AddEntryPreview(
            jyutping=self.jyutping,
            hanzi=self.hanzi,
            meaning=self.meaning,
            category=self.category,
        )

    def as_payload(self) -> Optional[Dict[str, Any]]:
        """
        Return the canonical + legacy payload dict expected by downstream
        confirmation and commit logic.
        """
        preview = self.build()
        if preview is None:
            return None

        return {
            # Canonical keys
            "jyutping": preview.jyutping,
            "hanzi": preview.hanzi,
            "meaning": preview.meaning,
            "category": preview.category,
            # Legacy aliases (tests rely on these)
            "gloss": preview.meaning,
            "categories": preview.categories,
        }