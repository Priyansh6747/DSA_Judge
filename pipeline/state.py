"""ProblemSpec — the canonical object passed through the pipeline.

Every stage reads from and writes to this. Nothing is guessed.
Every inference carries a confidence score.
Missing required fields halt the pipeline — no silent assumptions.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class Mode(str, Enum):
    SOLVE = "solve"        # Problem → generate solution
    VERIFY = "verify"      # Problem + code → compile & test
    REPAIR = "repair"      # Problem + failing code → fix & retest
    EXPLAIN = "explain"    # Problem + accepted code → explain approach


class Platform(str, Enum):
    LEETCODE = "leetcode"
    CODEFORCES = "codeforces"
    ATCODER = "atcoder"
    CSES = "cses"
    GEEKSFORGEEKS = "geeksforgeeks"
    HACKERRANK = "hackerrank"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class SolutionStatus(str, Enum):
    """Tracks the state of user-provided code."""
    MISSING = "missing"
    PROVIDED = "provided"
    ACCEPTED = "accepted"
    FAILED = "failed"


@dataclass(frozen=True)
class Sample:
    """A single test case."""
    case_id: str
    input: str
    expected: str


@dataclass(frozen=True)
class Confidence:
    """A value with a confidence score (0.0 to 1.0)."""
    value: Any
    score: float = 1.0  # 1.0 = certain, 0.0 = pure guess
    source: str = "explicit"  # "explicit", "inferred", "guessed"

    def __str__(self) -> str:
        if self.score >= 0.9:
            return str(self.value)
        pct = int(self.score * 100)
        return f"{self.value} ({pct}% confidence, {self.source})"


@dataclass(frozen=True)
class FunctionSignature:
    """Extracted function signature from problem/template."""
    name: str = ""
    return_type: str = ""
    arguments: str = ""  # e.g. "(vector<int>& nums)"
    class_name: str = ""  # e.g. "Solution" for LeetCode


@dataclass(frozen=True)
class ProblemSpec:
    """Canonical problem specification.

    Required fields (pipeline BLOCKS if missing):
        - description
        - samples (at least 1)

    Preferred fields (missing → ask user, never infer):
        - constraints
        - template / starter_code
        - function_signature

    Optional fields:
        - platform, language, user_solution
    """

    # --- Metadata ---
    run_id: str = ""
    problem_hash: str = ""
    timestamp: str = ""
    mode: Mode = Mode.SOLVE

    # --- Required (pipeline blocks if missing) ---
    description: str = ""
    samples: tuple[Sample, ...] = ()

    # --- Preferred (missing → interactive intake) ---
    constraints: dict[str, Any] = field(default_factory=dict)
    template: str = ""
    starter_code: str = ""
    function_signature: FunctionSignature = field(default_factory=FunctionSignature)

    # --- Optional ---
    platform: Confidence = field(default_factory=lambda: Confidence(Platform.UNKNOWN, 0.0, "no signal"))
    language: str = "cpp20"
    user_solution: str = ""
    solution_status: SolutionStatus = SolutionStatus.MISSING
    existing_output: str = ""

    # --- Derived by parser ---
    input_format: str = ""
    output_format: str = ""
    title: str = ""

    # --- Confidence scores for inferences ---
    constraint_confidence: float = 0.0
    template_confidence: float = 0.0
    platform_confidence: float = 0.0

    # --- Planner output ---
    algorithm: str = ""
    planning_reasoning: str = ""
    complexity_time: str = ""
    complexity_memory: str = ""
    edge_cases: tuple[str, ...] = ()

    # --- Generated solution ---
    solution_cpp: str = ""

    # --- Verification output ---
    verification_passed: bool = False
    verification_issues: tuple[str, ...] = ()

    # --- Compiler output ---
    compiled: bool = False
    binary_path: str = ""
    compiler_warnings: tuple[str, ...] = ()
    compiler_errors: tuple[str, ...] = ()
    compile_attempts: int = 0

    # --- Execution output ---
    case_results: tuple[dict[str, Any], ...] = ()

    # --- Validation output ---
    passed_samples: int = 0
    failed_samples: int = 0
    diffs: tuple[dict[str, str], ...] = ()

    # --- Reporter output ---
    report_md: str = ""
    confidence: str = "unknown"
    known_weaknesses: tuple[str, ...] = ()
    reasoning_summary: str = ""

    # --- Requirement gaps (filled by validator) ---
    missing_required: tuple[str, ...] = ()
    missing_preferred: tuple[str, ...] = ()
    questions_for_user: tuple[str, ...] = ()
    gate_status: str = "open"  # "open" or "blocked"

    def updated(self, **kwargs: Any) -> ProblemSpec:
        return replace(self, **kwargs)

    @staticmethod
    def new(description: str, mode: Mode = Mode.SOLVE) -> ProblemSpec:
        h = hashlib.sha256(description.encode()).hexdigest()[:12]
        return ProblemSpec(
            run_id=str(uuid.uuid4())[:8],
            problem_hash=h,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            description=description,
            mode=mode,
        )

    def has_samples(self) -> bool:
        return len(self.samples) > 0

    def has_constraints(self) -> bool:
        return bool(self.constraints)

    def has_template(self) -> bool:
        return bool(self.template or self.starter_code)

    def has_function_signature(self) -> bool:
        return bool(self.function_signature.name)

    def status_table(self) -> str:
        """Human-readable status with gate indicator."""
        def icon(present: bool, required: bool) -> str:
            if present:
                return "✅"
            return "❌" if required else "⚠️"

        req_status = "✓ ALL REQUIRED" if not self.missing_required else "✗ BLOCKED"
        pref_status = "✓ COMPLETE" if not self.missing_preferred else "⚠ INCOMPLETE"

        lines = [
            "─" * 40,
            "  PROBLEM SPEC STATUS",
            "─" * 40,
            "",
            "  Required:",
            f"    {icon(bool(self.description), True)} Description",
            f"    {icon(self.has_samples(), True)} Samples ({len(self.samples)} provided)",
            "",
            "  Preferred:",
            f"    {icon(self.has_constraints(), False)} Constraints",
            f"    {icon(self.has_template(), False)} Code Template",
            f"    {icon(self.has_function_signature(), False)} Function Signature",
            "",
            "  Optional:",
            f"    {icon(bool(self.user_solution), False)} Existing Solution ({self.solution_status.value})",
            "",
            "─" * 40,
            f"  Gate: {req_status}",
            f"  Info: {pref_status}",
            "─" * 40,
        ]
        return "\n".join(lines)
