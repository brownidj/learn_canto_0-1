"""
Reverse lookup service for Hanzi candidates from Jyutping.

This service provides tiered reverse lookup:
- Tier 1: Pre-built reverse index (fast, manual/curated)
- Tier 2: Compose from Unihan character map and rank by utility
"""
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ReverseLookupService:
    """Service for finding Hanzi candidates from Jyutping input.

    This implements a two-tier strategy:
    1. Pre-built reverse index (manual/cache)
    2. Dynamic composition from Unihan + shortlist ranking
    """

    def __init__(
        self,
        reverse_index: Optional[dict] = None,
        char_map: Optional[dict] = None,
        compose_fn: Optional[Callable] = None,
        shortlist_fn: Optional[Callable] = None
    ):
        """Initialize the reverse lookup service.

        Args:
            reverse_index: Pre-built jyutping -> [(hanzi, source, score)] mapping
            char_map: Unihan character map for Tier 2 composition
            compose_fn: Function to compose candidates from char map
            shortlist_fn: Function to rank/shortlist composed candidates
        """
        self.reverse_index = reverse_index or {}
        self.char_map = char_map or {}
        self.compose_fn = compose_fn
        self.shortlist_fn = shortlist_fn

    def candidates_for_jyutping(self, jyutping: str) -> list[tuple[str, str, int]]:
        """Get Hanzi candidates for a Jyutping phrase.

        Returns candidates in priority order:
        1. Tier 1: From reverse index (if available)
        2. Tier 2: Composed from Unihan + ranked

        Args:
            jyutping: Jyutping string (e.g. "nei5 hou2")

        Returns:
            List of (hanzi, source, score) tuples, ordered by relevance
        """
        # Normalize jyutping
        try:
            jy_normalized = " ".join((jyutping or "").strip().lower().split())
        except Exception:
            jy_normalized = (jyutping or "").strip().lower()

        # Tier 1: Pre-built reverse index
        if self.reverse_index and jy_normalized in self.reverse_index:
            hits = self.reverse_index.get(jy_normalized)
            if hits:
                logger.debug("Reverse lookup Tier 1: %d candidates for '%s'", 
                           len(hits), jy_normalized)
                return list(hits)

        # Tier 2: Compose from Unihan and rank
        if callable(self.compose_fn) and callable(self.shortlist_fn):
            if not self.char_map:
                logger.debug("Reverse lookup Tier 2: no char_map available for '%s'", 
                           jy_normalized)
                return []

            try:
                logger.debug("Reverse lookup Tier 2: composing from Unihan for '%s'", 
                           jy_normalized)
                combos = self.compose_fn(jy_normalized, self.char_map) or []

                # Try new signature first (keyword args)
                try:
                    ranked_pairs = self.shortlist_fn(jyut=jy_normalized, combos=combos, top_n=10) or []
                except TypeError:
                    # Fallback to positional args
                    ranked_pairs = self.shortlist_fn(jy_normalized, combos, 10) or []

                result = [(hz, "tier2-char-ranked", int(score)) for hz, score in ranked_pairs]
                logger.debug("Reverse lookup Tier 2: ranked %d candidates for '%s'", 
                           len(result), jy_normalized)
                return result
            except Exception as e:
                logger.debug("Reverse lookup Tier 2 failed for '%s': %r", jy_normalized, e)

        logger.debug("Reverse lookup: no candidates available for '%s'", jy_normalized)
        return []
