import logging
import math
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger("FileSearch.Matcher")

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
    logger.info("Using rapidfuzz for fuzzy matching.")
except ImportError:
    import difflib
    HAS_RAPIDFUZZ = False
    logger.info("rapidfuzz not available. Falling back to difflib.")

class FileMatcher:
    def __init__(self, threshold: float = 50.0):
        self.threshold = threshold

    def score_match(self, query: str, filename: str, ext: str, mtime: float, current_time: float) -> float:
        """Calculates a match score between 0 and 100+ based on similarity, recency, and exact matches."""
        query_clean = query.strip().lower()
        filename_clean = filename.strip().lower()
        
        # Stem is the filename without extension
        stem = Path(filename_clean).stem
        ext_clean = ext.strip().lower().lstrip('.')
        
        # Calculate base similarity
        if HAS_RAPIDFUZZ:
            # We check match against both stem and full filename
            ratio_stem = fuzz.ratio(query_clean, stem)
            token_sort_stem = fuzz.token_sort_ratio(query_clean, stem)
            partial_stem = fuzz.partial_ratio(query_clean, stem)
            
            ratio_full = fuzz.ratio(query_clean, filename_clean)
            token_sort_full = fuzz.token_sort_ratio(query_clean, filename_clean)
            partial_full = fuzz.partial_ratio(query_clean, filename_clean)
            
            # Combine scores, slightly penalizing partial matches to prevent random character hits
            base_score = max(
                ratio_stem,
                token_sort_stem,
                partial_stem * 0.9,
                ratio_full,
                token_sort_full,
                partial_full * 0.9
            )
        else:
            # difflib fallback
            ratio_stem = difflib.SequenceMatcher(None, query_clean, stem).ratio() * 100
            ratio_full = difflib.SequenceMatcher(None, query_clean, filename_clean).ratio() * 100
            
            # Boost substring matches since SequenceMatcher isn't great at partial word hits
            substring_boost = 0.0
            if query_clean in stem:
                substring_boost = 85.0 + (len(query_clean) / max(1, len(stem))) * 15.0
            elif query_clean in filename_clean:
                substring_boost = 80.0 + (len(query_clean) / max(1, len(filename_clean))) * 20.0
                
            base_score = max(ratio_stem, ratio_full, substring_boost)

        # 1. Exact match boosts
        exact_boost = 0.0
        if query_clean == stem:
            exact_boost = 15.0
        elif query_clean == filename_clean:
            exact_boost = 20.0

        # 2. Recency boost (up to 10 points)
        # Decays over time: 10 / (1 + days_since_modification)
        age_seconds = max(0.0, current_time - mtime)
        age_days = age_seconds / 86400.0
        recency_boost = 10.0 / (1.0 + age_days)

        # 3. Extension match boost
        # If the user query specifically mentions the extension, boost files with that extension.
        ext_boost = 0.0
        if ext_clean:
            # Query ends with extension (e.g. "resume.pdf" or "resume pdf")
            if query_clean.endswith(f".{ext_clean}") or query_clean.endswith(f" {ext_clean}"):
                ext_boost = 15.0

        total_score = base_score + exact_boost + recency_boost + ext_boost
        return total_score

    def pre_filter(self, query: str, filename: str) -> bool:
        """Fast heuristic to discard obviously irrelevant files before running slow scoring."""
        query_clean = query.strip().lower()
        filename_clean = filename.strip().lower()
        stem = Path(filename_clean).stem
        
        # If query is a substring of stem or filename, it's a match
        if query_clean in stem or query_clean in filename_clean:
            return True
            
        # Check if any word in the query is in the stem/filename
        words = [w for w in query_clean.split() if len(w) >= 3]
        if words and any(w in stem for w in words):
            return True
            
        # Check character intersection on the stem (ignoring extension noise)
        query_chars = set(query_clean)
        stem_chars = set(stem)
        intersection_len = len(query_chars & stem_chars)
        
        # We require at least 80% of query characters to be in the stem
        min_required_overlap = max(2, int(len(query_chars) * 0.8))
        return intersection_len >= min_required_overlap
