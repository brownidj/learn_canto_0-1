"""
utils package

Explicit re-exports only.
Avoid circular imports and test-time failures.
"""

# --- Category Manager domain rules (pure helpers) ---
from domain.category_rules import (
    CATEGORY_PLACEHOLDER_TEXT,
    is_category_placeholder,
    save_enabled_gate,
    should_show_custom_hanzi_button,
    prefer_meanings,
)

__all__ = [
    "CATEGORY_PLACEHOLDER_TEXT",
    "is_category_placeholder",
    "save_enabled_gate",
    "should_show_custom_hanzi_button",
    "prefer_meanings",
]