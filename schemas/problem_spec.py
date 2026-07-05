"""ProblemSpecJSON — the canonical schema for problem representation.

Every stage reads from and writes to this. The LLM is asked to produce this
JSON in Stage 1. Stage 2 validates completeness. Nothing is guessed.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────

Mode = Literal["solve", "verify", "repair", "explain"]

Platform = Literal[
    "leetcode", "codeforces", "atcoder", "cses",
    "geeksforgeeks", "hackerrank", "custom", "unknown",
]


# ── Sub-models ─────────────────────────────────────────────────────

class Sample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    input: str
    expected: str

    @field_validator("input", "expected")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v


class ConstraintBound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    variable: str
    min: Optional[Decimal] = None
    max: Optional[Decimal] = None
    kind: Literal["int", "float", "str", "array"] = "int"


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    time_limit_ms: Optional[int] = None
    memory_limit_mb: Optional[int] = None
    bounds: tuple[ConstraintBound, ...] = ()
    guarantees: tuple[str, ...] = ()


class FunctionSignature(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = ""
    return_type: str = ""
    arguments: str = ""
    class_name: str = ""


# ── Root model ─────────────────────────────────────────────────────

class ProblemSpecJSON(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    mode: Mode = "solve"
    title: str = ""
    description: str = ""
    samples: tuple[Sample, ...] = ()
    constraints: Constraints = Field(default_factory=Constraints)
    input_format: str = ""
    output_format: str = ""
    platform: Platform = "unknown"
    platform_confidence: float = 0.0
    platform_source: str = "no signal"
    function_signature: FunctionSignature = Field(default_factory=FunctionSignature)
    template: str = ""
    starter_code: str = ""
    user_solution: str = ""
    parse_confidence: float = 0.0
    parse_notes: tuple[str, ...] = ()

    @staticmethod
    def new(description: str, mode: Mode = "solve") -> ProblemSpecJSON:
        h = hashlib.sha256(description.encode()).hexdigest()[:12]
        return ProblemSpecJSON(
            run_id=str(uuid.uuid4())[:8],
            mode=mode,
            description=description,
            parse_confidence=0.0,
        )

    def has_samples(self) -> bool:
        return len(self.samples) > 0

    def has_constraints(self) -> bool:
        return bool(self.constraints.bounds) or bool(self.constraints.guarantees)

    def has_template(self) -> bool:
        return bool(self.template or self.starter_code)

    def has_function_signature(self) -> bool:
        return bool(self.function_signature.name)

    def status_table(self) -> str:
        def icon(present: bool, required: bool) -> str:
            if present:
                return "✅"
            return "❌" if required else "⚠️"

        from pipeline.intake import classify
        gate = classify(self)
        req_status = "✓ ALL REQUIRED" if not gate.missing_required else "✗ BLOCKED"
        pref_status = "✓ COMPLETE" if not gate.missing_preferred else "⚠ INCOMPLETE"

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
            f"    {icon(bool(self.user_solution), False)} Existing Solution",
            "",
            "─" * 40,
            f"  Gate: {req_status}",
            f"  Info: {pref_status}",
            "─" * 40,
        ]
        return "\n".join(lines)


# ── Run state (internal between stages) ───────────────────────────

class RunState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    spec: ProblemSpecJSON
    run_dir: Path
    run_id: str

    driver_cpp: Optional[str] = None
    driver_is_self_contained: bool = False

    solution_cpp: Optional[str] = None
    algorithm: str = ""
    complexity_time: str = ""
    complexity_memory: str = ""
    edge_cases: tuple[str, ...] = ()

    test_plan_cases: tuple[dict[str, Any], ...] = ()
    brute_force_cpp: Optional[str] = None

    compile_history: tuple[dict[str, Any], ...] = ()
    exec_history: tuple[dict[str, Any], ...] = ()
    case_results: tuple[dict[str, Any], ...] = ()

    compiled: bool = False
    binary_path: str = ""

    passed_samples: int = 0
    failed_samples: int = 0
    diffs: tuple[dict[str, str], ...] = ()

    report_md: str = ""
    confidence: str = "unknown"
    known_weaknesses: tuple[str, ...] = ()
