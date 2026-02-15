from __future__ import annotations

import os
import time
from typing import Any

from services.cantonese_models import CantoneseInfo


class CantoneseClient:
    def __init__(self, *, model: str = "gpt-4o-mini"):
        self._model = str(model or "gpt-4o-mini")

    def lookup(
        self,
        *,
        hanzi: str = "",
        jyutping: str = "",
        logger: Any | None = None,
    ) -> CantoneseInfo | None:
        hz = str(hanzi or "").strip()
        jy = " ".join(str(jyutping or "").strip().split())
        if not hz and not jy:
            return None

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            if logger is not None:
                try:
                    logger.debug("CANTO: missing OPENAI_API_KEY")
                except Exception:
                    pass
            return None

        try:
            from openai import OpenAI
            from pydantic import BaseModel, Field
            from typing import Literal, List
            try:
                from pydantic import ConfigDict
            except Exception:
                ConfigDict = None  # type: ignore[assignment]
        except Exception:
            if logger is not None:
                try:
                    logger.debug("CANTO: openai/pydantic import failed", exc_info=True)
                except Exception:
                    pass
            return None

        client = OpenAI(api_key=api_key, timeout=20)

        class ExampleItem(BaseModel):
            hanzi: str
            jyutping: str
            gloss: str

        class CantoneseEntry(BaseModel):
            if ConfigDict is not None:
                model_config = ConfigDict(populate_by_name=True)
            hanzi: str
            jyutping: str
            meaning_colloquial: str
            register_: Literal["colloquial", "formal", "neutral"] = Field(alias="register")
            confidence: float = Field(ge=0, le=1)
            notes: str = ""
            examples: List[ExampleItem] = []

        system_msg = (
            "You are an expert in Cantonese lexicography. "
            "Return a JSON object matching the provided schema. "
            "Use colloquial everyday meanings when possible."
        )
        user_msg = "Hanzi: {0}\nJyutping (if known): {1}".format(hz, jy)

        try:
            if logger is not None:
                logger.debug("CANTO: api request model=%r hanzi=%r", self._model, hz)
            resp = client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                text_format=CantoneseEntry,
                temperature=0.2,
            )
        except Exception:
            if logger is not None:
                try:
                    logger.debug("CANTO: responses.parse failed", exc_info=True)
                except Exception:
                    pass
            return None

        try:
            data = resp.output_parsed
        except Exception:
            data = None

        if data is None:
            return None

        try:
            return CantoneseInfo(
                hanzi=str(data.hanzi or hz),
                jyutping=str(data.jyutping or jy),
                meaning_colloquial=str(data.meaning_colloquial or ""),
                register=str(data.register_ or "neutral"),
                confidence=float(data.confidence or 0.0),
                notes=str(data.notes or "") or None,
                examples=[e.model_dump() for e in list(data.examples or [])],
                model=self._model,
                ts=time.time(),
            )
        except Exception:
            return None
