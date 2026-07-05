"""Stage 4: Solution Generation — LLM writes the C++20 solution.

The LLM receives the full problem spec, constraints, signature, edge cases,
and produces a SolutionArtifact with the solution + metadata.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from schemas.problem_spec import ProblemSpecJSON, Constraints
from schemas.solution_spec import SolutionArtifact
from pipeline import llm as llm_mod


class SolutionGenError(Exception):
    pass


def generate_solution(
    spec: ProblemSpecJSON,
    edge_cases: tuple[str, ...] = (),
    run_dir: Optional[Path] = None,
) -> SolutionArtifact:
    """Generate a C++20 solution for the problem."""
    func_name = spec.function_signature.name or "solve"
    class_name = spec.function_signature.class_name or ""
    return_type = spec.function_signature.return_type or "int"
    arguments = spec.function_signature.arguments or "()"

    # Build constraints text
    constraints_text = _format_constraints(spec.constraints)

    # Build warnings
    time_warning = _build_time_warning(spec)
    overflow_warning = _build_overflow_warning(spec)

    samples_for_prompt = [
        {"id": s.id, "input": s.input, "expected": s.expected}
        for s in spec.samples
    ]

    if not edge_cases:
        edge_cases = ("single element", "minimum values", "maximum values")

    try:
        raw = llm_mod.complete("solution", {
            "description": spec.description,
            "function_name": func_name,
            "class_name": class_name,
            "return_type": return_type,
            "arguments": arguments,
            "constraints_text": constraints_text,
            "edge_cases": edge_cases,
            "samples": samples_for_prompt,
            "time_warning": time_warning,
            "overflow_warning": overflow_warning,
        }, expect_json=True)
    except llm_mod.LLMError as e:
        raise SolutionGenError(f"LLM failed to generate solution: {e}") from e

    artifact = SolutionArtifact(**raw)

    # Deterministic checks
    _check_function_name(artifact.solution_cpp, func_name)
    _check_no_debug(artifact.solution_cpp)

    if run_dir and not class_name:
        # If driver exists, syntax-check combined
        driver_path = run_dir / "driver.cpp"
        if driver_path.exists():
            _check_combined_syntax(artifact.solution_cpp, driver_path.read_text(), run_dir)

    return artifact


def _check_function_name(solution_cpp: str, func_name: str) -> None:
    """Verify the solution contains the exact function name."""
    if func_name and func_name not in solution_cpp:
        raise SolutionGenError(
            f"Solution does not contain required function name '{func_name}'. "
            f"Signature must match exactly."
        )


def _check_no_debug(solution_cpp: str) -> None:
    """Reject solutions with debug markers."""
    markers = ["DEBUG", "#ifdef DEBUG", "cerr <<"]
    for marker in markers:
        if marker in solution_cpp:
            raise SolutionGenError(
                f"Solution contains debug marker '{marker}'. "
                f"Remove all debug output before submitting."
            )


def _check_combined_syntax(solution_cpp: str, driver_cpp: str, run_dir: Path) -> None:
    """Syntax-check combined driver + solution."""
    combined = f"{solution_cpp}\n\n{driver_cpp}"
    test_file = run_dir / "_solution_syntax_check.cpp"
    test_file.write_text(combined)

    try:
        cmd = ["g++", "-std=c++20", "-fsyntax-only", "-x", "c++", str(test_file)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            raise SolutionGenError(
                f"Combined driver+solution syntax check failed:\n{result.stderr[:1000]}"
            )
    finally:
        test_file.unlink(missing_ok=True)


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


def _build_time_warning(spec: ProblemSpecJSON) -> str:
    """Build a performance warning if constraints suggest tight limits."""
    for b in spec.constraints.bounds:
        if b.variable == "n" and b.max and b.max > 100000:
            return (
                f"n can be up to {b.max}. Your solution must be O(n log n) or better. "
                f"O(n²) will TLE."
            )
    return ""


def _build_overflow_warning(spec: ProblemSpecJSON) -> str:
    """Build an overflow warning if bounds exceed int range."""
    for b in spec.constraints.bounds:
        if b.max and b.max > 2_147_483_647:
            return (
                f"{b.variable} can be up to {b.max}, which exceeds int range. "
                f"Use `long long` for sums/products involving this variable."
            )
    return ""
