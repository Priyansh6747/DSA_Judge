"""Platform detection — hint function used by parser.py to seed LLM prompt.

This is a heuristic helper, NOT authoritative. The LLM's structured output
in Stage 1 is the final authority on platform detection.
"""

from __future__ import annotations

import re


PLATFORM_SIGNALS: dict[str, list[str]] = {
    "leetcode": ["leetcode", "class solution", "def solution", "example 1:"],
    "codeforces": ["codeforces", "code force", "codeforces.com"],
    "atcoder": ["atcoder", "at coder", "入力", "出力"],
    "cses": ["cses"],
    "geeksforgeeks": ["geeksforgeeks", "gfg"],
    "hackerrank": ["hackerrank", "hack rank"],
}


def detect_platform(text: str) -> tuple[str, float, str]:
    """Detect platform from problem text with confidence score.

    Returns (platform, confidence, source).
    Confidence is 0.0 to 1.0.
    This is a HINT — the LLM's structured output is authoritative.
    """
    lower = text.lower()
    best_platform = "unknown"
    best_confidence = 0.0
    best_source = "no signal"

    for platform, keywords in PLATFORM_SIGNALS.items():
        matches = sum(1 for kw in keywords if kw in lower)
        if matches > 0:
            confidence = min(matches * 0.3, 0.9)
            if confidence > best_confidence:
                best_platform = platform
                best_confidence = confidence
                best_source = f"matched: {', '.join(kw for kw in keywords if kw in lower)}"

    # Heuristic: platform-specific patterns (boost if low confidence)
    if best_confidence < 0.5:
        if "example 1:" in lower and ("nums" in lower or "vector" in lower):
            best_platform = "leetcode"
            best_confidence = 0.7
            best_source = "heuristic: Example format + array naming"
        elif re.search(r"^a\.", lower) or re.search(r"^b\.", lower):
            best_platform = "codeforces"
            best_confidence = 0.5
            best_source = "heuristic: Codeforces-style problem naming"
        elif "sample input" in lower and "sample output" in lower:
            best_platform = "unknown"
            best_confidence = 0.3
            best_source = "heuristic: competitive programming format"

    return best_platform, best_confidence, best_source
