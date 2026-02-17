"""Cue spelling generator for Jyutping syllables."""

from __future__ import annotations

import re
from typing import Dict, Tuple


_SYLLABLE_RE = re.compile(r"^([a-z]+)([1-6])$", re.IGNORECASE)

_INITIALS = [
    "gw",
    "kw",
    "ng",
    "b",
    "p",
    "m",
    "f",
    "d",
    "t",
    "n",
    "l",
    "g",
    "k",
    "h",
    "w",
    "z",
    "c",
    "s",
    "j",
]

_INITIAL_MAP: Dict[str, str] = {
    "b": "B",
    "p": "P",
    "m": "M",
    "f": "F",
    "d": "D",
    "t": "T",
    "n": "N",
    "l": "L",
    "g": "G",
    "k": "K",
    "ng": "NG",
    "h": "H",
    "gw": "GW",
    "kw": "KW",
    "w": "W",
    "z": "DZ",
    "c": "TS",
    "s": "S",
    "j": "Y",
    "": "",
}

_TONE_SUPERSCRIPT = {
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
}

_BASE_FINAL_MAP: Dict[str, str] = {
    "aa": "AH",
    "a": "UH",
    "i": "EE",
    "u": "OO",
    "e": "EH",
    "o": "AW",
    "ai": "EYE",
    "au": "OW",
    "ei": "AY",
    "ou": "OH",
    "oi": "OY",
    "ui": "OOEY",
    "eoi": "OEY",
    "oe": "OE",
    "eo": "OE",
    "iu": "EEU",
    "yu": "YOO",
    "aai": "AHY",
}

_CODA_MAP = {
    "m": "M",
    "n": "N",
    "ng": "NG",
    "p": "P",
    "t": "T",
    "k": "K",
}

_FINAL_HINTS: Dict[str, str] = {
    "aa": "AH like “spa”",
    "a": "UH like “uh”",
    "i": "EE like “see”",
    "u": "OO like “too”",
    "e": "EH like “bed”",
    "o": "AW like “law”",
    "ai": "EYE like “eye”",
    "au": "OW like “cow”",
    "ei": "AY like “say”",
    "ou": "OH like “go”",
    "oi": "OY like “boy”",
    "ui": "OO‑EE glide",
    "eoi": "rounded “uh/er”",
    "oe": "rounded “uh/er”",
    "eo": "rounded “uh/er”",
    "iu": "EE‑OO glide",
    "yu": "front “oo” (like “you”)",
}


def _split_syllable(syl: str) -> Tuple[str, str, str]:
    m = _SYLLABLE_RE.match(syl.strip().lower())
    if not m:
        return "", syl, ""
    base, tone = m.group(1), m.group(2)
    initial = ""
    rest = base
    for ini in _INITIALS:
        if base.startswith(ini):
            initial = ini
            rest = base[len(ini):]
            break
    return initial, rest, tone


def _cue_final(final: str) -> str | None:
    if final in _BASE_FINAL_MAP:
        return _BASE_FINAL_MAP[final]
    for coda in ("ng", "m", "n", "p", "t", "k"):
        if final.endswith(coda) and final != coda:
            base = final[: -len(coda)]
            base_cue = _BASE_FINAL_MAP.get(base)
            if base_cue is None:
                return None
            return base_cue + _CODA_MAP[coda]
    if final == "":
        return ""
    return None


def cue_for_syllable(syl: str) -> str:
    initial, final, tone = _split_syllable(syl)
    tone_mark = _TONE_SUPERSCRIPT.get(tone, tone)
    final_cue = _cue_final(final)
    init_cue = _INITIAL_MAP.get(initial, initial.upper())
    if final_cue is None:
        return f"{(initial + final).upper()}{tone_mark}"
    return f"{init_cue}{final_cue}{tone_mark}"


def cue_for_phrase(jyutping: str) -> str:
    parts = [p for p in re.split(r"\s+", (jyutping or "").strip()) if p]
    if not parts:
        return ""
    cues = [cue_for_syllable(p) for p in parts]
    return " · ".join(cues)


def hint_for_syllable(syl: str) -> str:
    initial, final, _tone = _split_syllable(syl)
    _ = initial  # unused but kept for clarity
    if not final:
        return ""
    for coda in ("ng", "m", "n", "p", "t", "k"):
        if final.endswith(coda) and final != coda:
            base = final[: -len(coda)]
            base_hint = _FINAL_HINTS.get(base)
            if base_hint:
                if coda in ("p", "t", "k"):
                    return f"{base_hint}, checked -{coda}"
                return f"{base_hint}, ending -{coda}"
    return _FINAL_HINTS.get(final, "")


__all__ = ["cue_for_phrase", "cue_for_syllable", "hint_for_syllable"]
