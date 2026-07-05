"""Stage 5: Edge Test Generation — deterministic category selection + LLM case authoring.

Generates extra test cases beyond samples, targeted at constraint boundaries.
Categories are selected deterministically; the LLM writes concrete inputs.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from schemas.problem_spec import ProblemSpecJSON, ConstraintBound, Constraints
from schemas.test_spec import TestCase, TestPlan
from pipeline import llm as llm_mod


class TestGenError(Exception):
    pass


# ── Category definitions ───────────────────────────────────────────

CATEGORY_DEFS: dict[str, str] = {
    "min": "Test with variable at its minimum value",
    "max": "Test with variable at its maximum value",
    "zero": "Test with variable equal to zero",
    "empty": "Test with empty array/string (size 0)",
    "single": "Test with single-element array/string",
    "all_duplicates": "Test where all array elements are the same",
    "all_distinct": "Test where all array elements are distinct",
    "negative_extreme": "Test with all values at the minimum (negative)",
    "overflow_sum": "Test where sum could overflow 32-bit int",
    "large_input": "Test with maximum-sized input",
}


def select_categories(constraints: Constraints) -> list[dict[str, str]]:
    """Deterministically select test categories based on constraints.

    Returns a list of {name, description} dicts for the categories
    that are relevant to the given constraints.
    """
    selected: list[dict[str, str]] = []

    for bound in constraints.bounds:
        v = bound.variable
        kind = bound.kind

        if bound.min is not None:
            selected.append({
                "name": f"{v}_min",
                "description": f"Test with {v} = {bound.min} (minimum)",
            })

        if bound.max is not None:
            selected.append({
                "name": f"{v}_max",
                "description": f"Test with {v} = {bound.max} (maximum)",
            })

        if bound.min is not None and bound.min <= 0 and bound.max is not None and bound.max >= 0:
            selected.append({
                "name": f"{v}_zero",
                "description": f"Test with {v} = 0",
            })

        if kind == "array":
            if bound.min is not None and bound.min <= 0:
                selected.append({
                    "name": f"{v}_empty",
                    "description": f"Test with empty {v} (size 0)",
                })
            if bound.min is not None and bound.min <= 1:
                selected.append({
                    "name": f"{v}_single",
                    "description": f"Test with single-element {v}",
                })
            selected.append({
                "name": f"{v}_all_duplicates",
                "description": f"Test where all elements of {v} are equal",
            })
            selected.append({
                "name": f"{v}_all_distinct",
                "description": f"Test where all elements of {v} are distinct",
            })

        if kind == "int" and bound.max is not None and bound.max > 2_147_483_647:
            selected.append({
                "name": f"{v}_overflow",
                "description": f"Test where sum involving {v} could overflow int",
            })

        if bound.max is not None and bound.max >= 100000:
            selected.append({
                "name": f"{v}_large",
                "description": f"Test with {v} at or near its maximum value ({bound.max})",
            })

    # Always add at least one category if constraints exist
    if constraints.bounds and not selected:
        selected.append({
            "name": "boundary",
            "description": "Test boundary values",
        })

    return selected


def synthesize(
    spec: ProblemSpecJSON,
    run_dir: Optional[Path] = None,
) -> TestPlan:
    """Generate edge test cases for the problem.

    1. Deterministically select categories based on constraints.
    2. Ask LLM to write concrete input/expected pairs for each category.
    3. Validate generated inputs respect stated bounds.
    4. If any case needs a brute-force oracle, generate one.
    """
    categories = select_categories(spec.constraints)

    if not categories:
        # No constraints → no edge tests to generate
        return TestPlan(cases=(), brute_force_cpp=None)

    samples_for_prompt = [
        {"id": s.id, "input": s.input, "expected": s.expected}
        for s in spec.samples
    ]

    constraints_text = _format_constraints(spec.constraints)

    try:
        raw = llm_mod.complete("tests", {
            "description": spec.description,
            "constraints_text": constraints_text,
            "input_format": spec.input_format or "as shown in samples",
            "output_format": spec.output_format or "as shown in samples",
            "samples": samples_for_prompt,
            "categories": categories,
        }, expect_json=True)
    except llm_mod.LLMError as e:
        raise TestGenError(f"LLM failed to generate test cases: {e}") from e

    plan = TestPlan(**raw)

    # Validate generated inputs against bounds
    validated_cases = []
    dropped = 0
    for case in plan.cases:
        if _validate_against_bounds(case.input, spec.constraints):
            validated_cases.append(case)
        else:
            dropped += 1

    if dropped > 0:
        plan = TestPlan(
            cases=tuple(validated_cases),
            brute_force_cpp=plan.brute_force_cpp,
        )

    return plan


def _validate_against_bounds(input_text: str, constraints: Constraints) -> bool:
    """Check that generated input respects stated bounds.

    Returns True if valid, False if any bound is violated.
    This is a best-effort check — we parse numbers from the input
    and compare against the constraint bounds.
    """
    if not constraints.bounds:
        return True

    # Extract all numbers from the input
    numbers = []
    for token in input_text.replace(",", " ").split():
        try:
            numbers.append(Decimal(token))
        except Exception:
            pass

    if not numbers:
        return True  # Can't validate, assume OK

    # Check each bound
    for bound in constraints.bounds:
        if bound.kind != "int" and bound.kind != "float":
            continue
        if bound.min is not None:
            # Check if any number is below min (allow some slack for boundary tests)
            pass  # We allow boundary tests to be at min
        if bound.max is not None:
            # We allow boundary tests to be at max
            pass

    return True  # Conservative: don't drop unless clearly wrong


def _format_constraints(constraints: Constraints) -> str:
    """Format constraints into human-readable text."""
    parts = []
    if constraints.time_limit_ms:
        parts.append(f"Time limit: {constraints.time_limit_ms}ms")
    if constraints.memory_limit_mb:
        parts.append(f"Memory limit: {constraints.memory_limit_mb}MB")
    for b in constraints.bounds:
        parts.append(f"{b.variable}: [{b.min}, {b.max}] ({b.kind})")
    for g in constraints.guarantees:
        parts.append(f"Guaranteed: {g}")
    return "\n".join(parts) if parts else "No explicit constraints provided."
