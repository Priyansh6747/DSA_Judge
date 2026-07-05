"""Requirement Validator — HARD GATE.

Checks ProblemSpec completeness. If required fields are missing,
the pipeline is BLOCKED. No guessing, no inferring, no silent assumptions.

Missing preferred fields trigger an Interactive Intake — the user is asked.
"""

from __future__ import annotations

import re

from pipeline.state import ProblemSpec, Mode, Platform, SolutionStatus


def validate_requirements(spec: ProblemSpec) -> ProblemSpec:
    """Check completeness. Returns updated spec with gate_status.

    Gate statuses:
        "blocked" — required fields missing, cannot proceed
        "open"    — all required fields present, may proceed
        "intake"  — preferred fields missing, user needs to answer questions
    """
    missing_required = []
    missing_preferred = []
    questions = []

    # ══════════════════════════════════════════════════════════════
    # REQUIRED — pipeline BLOCKS if these are missing
    # ══════════════════════════════════════════════════════════════

    if not spec.description.strip():
        missing_required.append("description")
        questions.append(
            "Please provide the problem statement."
        )

    if not spec.has_samples():
        missing_required.append("samples")
        questions.append(
            "No sample test cases provided.\n"
            "I cannot validate the solution without at least one sample input and expected output.\n"
            "Please provide at least one sample test case."
        )

    # Mode-specific required fields
    if spec.mode in (Mode.VERIFY, Mode.REPAIR, Mode.EXPLAIN) and not spec.user_solution:
        missing_required.append("user_solution")
        mode_instructions = {
            Mode.VERIFY: "Verify mode requires existing code to test.",
            Mode.REPAIR: "Repair mode requires the failing code.",
            Mode.EXPLAIN: "Explain mode requires accepted code.",
        }
        questions.append(f"{mode_instructions[spec.mode]} Please provide the code.")

    # ══════════════════════════════════════════════════════════════
    # PREFERRED — missing triggers Interactive Intake
    # NEVER inferred. Always asked.
    # ══════════════════════════════════════════════════════════════

    if not spec.has_constraints():
        missing_preferred.append("constraints")
        questions.append(
            "Constraints were not provided.\n"
            "I will plan and generate code without explicit constraints.\n"
            "Confidence will be reduced.\n\n"
            "Should I:\n"
            "1. Continue without constraints\n"
            "2. Wait for you to provide them"
        )

    if not spec.has_template() and spec.mode in (Mode.SOLVE, Mode.REPAIR):
        missing_preferred.append("template")
        questions.append(
            "I cannot identify the required code template.\n"
            "I need to know the entry point before generating code.\n\n"
            "Reply with ONE of:\n"
            "1 — LeetCode (class Solution)\n"
            "2 — Codeforces (main)\n"
            "3 — AtCoder (main)\n"
            "4 — CSES (main)\n"
            "5 — Paste custom template"
        )

    if not spec.has_function_signature() and spec.mode in (Mode.SOLVE, Mode.REPAIR):
        missing_preferred.append("function_signature")
        questions.append(
            "I need the function name and signature.\n"
            "What should the solution function be called?\n\n"
            "Examples:\n"
            "  int maximumDigitRange(vector<int>& nums)\n"
            "  int main()"
        )

    # ══════════════════════════════════════════════════════════════
    # Determine gate status
    # ══════════════════════════════════════════════════════════════

    if missing_required:
        gate_status = "blocked"
    elif missing_preferred:
        gate_status = "intake"
    else:
        gate_status = "open"

    return spec.updated(
        missing_required=tuple(missing_required),
        missing_preferred=tuple(missing_preferred),
        questions_for_user=tuple(questions),
        gate_status=gate_status,
    )


def can_proceed(spec: ProblemSpec) -> bool:
    """True only if gate is open (all required + all preferred present)."""
    return spec.gate_status == "open"


def is_blocked(spec: ProblemSpec) -> bool:
    """True if required fields are missing."""
    return spec.gate_status == "blocked"


def needs_intake(spec: ProblemSpec) -> bool:
    """True if preferred fields are missing (user must answer questions)."""
    return spec.gate_status == "intake"


def intake_summary(spec: ProblemSpec) -> str:
    """Generate the Interactive Intake prompt for missing preferred fields."""
    if not spec.missing_preferred:
        return ""

    lines = [
        "─" * 40,
        "  REQUIRED INFORMATION",
        "─" * 40,
        "",
    ]

    for i, question in enumerate(spec.questions_for_user, 1):
        lines.append(f"  {question}")
        lines.append("")

    lines.append("─" * 40)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# Platform Detection — with confidence score
# ══════════════════════════════════════════════════════════════════

PLATFORM_SIGNALS: dict[Platform, list[str]] = {
    Platform.LEETCODE: ["leetcode", "class solution", "def solution"],
    Platform.CODEFORCES: ["codeforces", "code force", "codeforces.com"],
    Platform.ATCODER: ["atcoder", "at coder", "入力", "出力"],
    Platform.CSES: ["cses"],
    Platform.GEEKSFORGEEKS: ["geeksforgeeks", "gfg"],
    Platform.HACKERRANK: ["hackerrank", "hack rank"],
}


def detect_platform(text: str) -> tuple[Platform, float, str]:
    """Detect platform from problem text with confidence score.

    Returns (platform, confidence, source).
    Confidence is 0.0 to 1.0.
    """
    lower = text.lower()
    best_platform = Platform.UNKNOWN
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

    # Heuristic: platform-specific patterns
    if best_platform == Platform.UNKNOWN:
        if "example 1:" in lower and ("nums" in lower or "vector" in lower):
            # LeetCode-style example format with array naming
            best_platform = Platform.LEETCODE
            best_confidence = 0.7
            best_source = "heuristic: Example format + array naming"
        elif re.search(r"^a\.", lower) or re.search(r"^b\.", lower):
            # Codeforces-style problem naming (A. Problem Name)
            best_platform = Platform.CODEFORCES
            best_confidence = 0.5
            best_source = "heuristic: Codeforces-style problem naming"
        elif "sample input" in lower and "sample output" in lower:
            # Generic competitive programming format
            best_platform = Platform.UNKNOWN
            best_confidence = 0.3
            best_source = "heuristic: competitive programming format"

    return best_platform, best_confidence, best_source


# ══════════════════════════════════════════════════════════════════
# Function Signature Extraction
# ══════════════════════════════════════════════════════════════════

def extract_function_signature(text: str) -> tuple[str, str, str, str]:
    """Try to extract function name, return type, arguments, class name from text.

    Returns (name, return_type, arguments, class_name).
    Empty strings if not found.
    """
    import re

    # LeetCode style: class Solution { public: int funcName(vector<int>& nums) {} }
    leetcode_match = re.search(
        r"class\s+(\w+)\s*\{[^}]*?(\w+)\s+(\w+)\s*\(([^)]*)\)",
        text, re.S,
    )
    if leetcode_match:
        return (
            leetcode_match.group(3),
            leetcode_match.group(2),
            leetcode_match.group(4),
            leetcode_match.group(1),
        )

    # Standalone function: int funcName(vector<int>& nums)
    func_match = re.search(
        r"(?:int|void|long\s+long|bool|double|float|string|auto)\s+(\w+)\s*\(([^)]*)\)",
        text,
    )
    if func_match:
        return_type = text[func_match.start():func_match.start() + len(text[func_match.start():].split("(")[0].split()[-1])]
        return (
            func_match.group(1),
            return_type.strip(),
            func_match.group(2),
            "",
        )

    return ("", "", "", "")
