# settings.py
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple
from PySide6.QtCore import QSettings


# App identity for QSettings (macOS -> ~/Library/Preferences/<org>.<app>.plist)
ORG_NAME = "Topository"
APP_NAME = "LearnCanto_01"

@dataclass(frozen=True)
class Defaults:
    wpm: int = 120              # 60–220 (step 20 in UI)
    intro_delay: int = 2        # 0–10
    repeat_delay: int = 1       # 0–10
    extro_delay: int = 1        # 0–10
    auto_delay: int = 0         # 0–10
    repeats: int = 1            # 0–10
    category: str = "All"

# Keys used in the settings store (avoid typos; one place to change)
KEYS = {
    "wpm": "tts/wpm",
    "intro_delay": "delays/intro",
    "repeat_delay": "delays/repeat",
    "extro_delay": "delays/extro",
    "auto_delay": "delays/auto",
    "repeats": "play/repeats",   # NEW
    "category": "ui/category",
}

def _qs() -> QSettings:
    s = QSettings(ORG_NAME, APP_NAME)
    return s

def load_all() -> Dict[str, Any]:
    """Return a dict of current values, falling back to defaults."""
    d = Defaults()
    s = _qs()
    current = {
        "wpm": s.value(KEYS["wpm"], d.wpm, type=int),
        "intro_delay": s.value(KEYS["intro_delay"], d.intro_delay, type=int),
        "repeat_delay": s.value(KEYS["repeat_delay"], d.repeat_delay, type=int),
        "extro_delay": s.value(KEYS["extro_delay"], d.extro_delay, type=int),
        "auto_delay": s.value(KEYS["auto_delay"], d.auto_delay, type=int),
        "repeats": s.value(KEYS["repeats"], d.repeats, type=int),    # NEW
        "category": s.value(KEYS["category"], d.category, type=str),
    }
    return current

def save_one(name: str, value: Any) -> None:
    """Persist a single setting by name using KEYS mapping."""
    if name not in KEYS:
        raise KeyError("Unknown setting: " + name)
    s = _qs()
    s.setValue(KEYS[name], value)
    s.sync()

def reset_all() -> Dict[str, Any]:
    """Reset everything to Defaults and return the fresh dict."""
    d = Defaults()
    s = _qs()
    for k, v in asdict(d).items():
        s.setValue(KEYS[k], v)
    s.sync()
    return load_all()

def bounds() -> Dict[str, Tuple[int, int, int]]:
    """UI helpers: (min, max, step) for each setting that uses a slider."""
    return {
        "wpm": (60, 220, 20),
        "intro_delay": (0, 10, 1),
        "repeat_delay": (0, 10, 1),
        "extro_delay": (0, 10, 1),
        "auto_delay": (0, 10, 1),
        "repeats": (1, 10, 1),
    }