"""Pipeline engine — deterministic stages for DSA Judge.

Handles: parse → validate requirements → compile → execute → validate output → report.

The agent (LLM) handles: planning, code generation, verification, repair, explanation.
These happen BETWEEN engine calls, guided by SKILL.md.

Key principle: The engine NEVER guesses. If information is missing, it asks.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

from pipeline.state import ProblemSpec, Sample, Mode, Platform, Confidence, FunctionSignature, SolutionStatus
from pipeline.validator import (
    validate_requirements, can_proceed, is_blocked, needs_intake,
    detect_platform, extract_function_signature, intake_summary,
)


# ══════════════════════════════════════════════════════════════════
# Parser
# ══════════════════════════════════════════════════════════════════

def parse_problem(text: str) -> ProblemSpec:
    """Parse problem text into a ProblemSpec.

    Extracts what it can from the text. Missing fields are left empty —
    the Requirement Validator will flag them and the Interactive Intake
    will ask the user. Nothing is guessed.
    """
    spec = ProblemSpec.new(text)

    # Platform detection with confidence
    platform, p_confidence, p_source = detect_platform(text)
    spec = spec.updated(
        platform=Confidence(platform, p_confidence, p_source),
        platform_confidence=p_confidence,
    )

    lines = text.strip().split("\n")

    # Title: first non-empty line that isn't a keyword
    for line in lines:
        stripped = line.strip()
        if stripped and not any(kw in stripped.lower() for kw in [
            "example", "input", "output", "sample", "constraint", "you are given"
        ]):
            spec = spec.updated(title=stripped)
            break

    # Constraints — look for explicit numeric ranges ONLY
    # Do NOT infer from platform or problem type
    constraints = {}
    for pattern, key in [
        (r"(\d+)\s*[≤<=]\s*(\w+)\s*[≤<=]\s*(\d+)", "range"),
        (r"time limit[:\s]*(\d+)", "time_limit"),
        (r"memory limit[:\s]*(\d+)", "memory_limit"),
        (r"(\d+)\s*<=?\s*n\s*<=?\s*(\d+)", "n_range"),
        (r"(\d+)\s*<=?\s*nums\[i\]\s*<=?\s*(\d+)", "nums_range"),
    ]:
        match = re.search(pattern, text, re.I)
        if match:
            constraints[key] = match.groups()
    if constraints:
        spec = spec.updated(
            constraints=constraints,
            constraint_confidence=1.0,
        )

    # Samples — find "Sample Input N:" / "Sample Output N:" pairs
    samples = []
    sample_pattern = re.compile(
        r"[Ss]ample\s+[Ii]nput\s*(\d+)\s*[:\n]\s*(.*?)[\n]+[Ss]ample\s+[Oo]utput\s*\1\s*[:\n]\s*(.*?)(?=\n[Ss]ample|\Z)",
        re.S,
    )
    for m in sample_pattern.finditer(text):
        inp = m.group(2).strip()
        out = m.group(3).strip()
        if inp and out:
            samples.append(Sample(
                case_id=m.group(1).zfill(2),
                input=inp,
                expected=out,
            ))

    # Fallback: unnumbered Input:/Output: pairs
    if not samples:
        unnumbered = re.compile(
            r"[Ii]nput\s*[:\n]\s*(.*?)[\n]+[Oo]utput\s*[:\n]\s*(.*?)(?=\n[Ii]nput|\n[Ee]xample|\Z)",
            re.S,
        )
        for i, m in enumerate(unnumbered.finditer(text)):
            inp = m.group(1).strip()
            out = m.group(2).strip()
            if inp and out:
                samples.append(Sample(
                    case_id=f"{i+1:02d}",
                    input=inp,
                    expected=out,
                ))

    if samples:
        spec = spec.updated(samples=tuple(samples))

    # Input/output format sections
    input_format = _extract_section(text, ["input format", "input"])
    output_format = _extract_section(text, ["output format", "output"])
    if input_format:
        spec = spec.updated(input_format=input_format)
    if output_format:
        spec = spec.updated(output_format=output_format)

    # Try to extract function signature from the problem text
    name, ret_type, args, cls = extract_function_signature(text)
    if name:
        spec = spec.updated(
            function_signature=FunctionSignature(name, ret_type, args, cls),
            template_confidence=0.8,
        )

    # Validate requirements (sets gate_status)
    spec = validate_requirements(spec)

    return spec


def _extract_section(text: str, headers: list[str]) -> str:
    for header in headers:
        pattern = rf"(?:^|\n)(?:{header})\s*[:\n](.*?)(?:\n(?:input|output|sample|constraint|note|example)|\Z)"
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return match.group(1).strip()
    return ""


# ══════════════════════════════════════════════════════════════════
# Compiler
# ══════════════════════════════════════════════════════════════════

def compile_cpp(source_path: str, binary_path: str) -> dict[str, Any]:
    cmd = ["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-o", binary_path, source_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    warnings = [l for l in result.stderr.splitlines() if "warning:" in l.lower()]
    errors = [l for l in result.stderr.splitlines() if "error:" in l.lower()]
    return {
        "success": result.returncode == 0,
        "binary_path": binary_path if result.returncode == 0 else "",
        "warnings": warnings,
        "errors": errors,
    }


# ══════════════════════════════════════════════════════════════════
# Executor
# ══════════════════════════════════════════════════════════════════

def execute_binary(binary_path: str, stdin: str, timeout_s: float = 5.0, memory_limit_mb: int = 256) -> dict[str, Any]:
    import resource

    def set_limits():
        mem_bytes = memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (int(timeout_s) + 1, int(timeout_s) + 1))

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [binary_path], input=stdin, capture_output=True, text=True,
            timeout=timeout_s, preexec_fn=set_limits,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        try:
            mem_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception:
            mem_kb = 0
        return {
            "stdout": proc.stdout, "stderr": proc.stderr,
            "exit_code": proc.returncode, "timed_out": False,
            "time_ms": elapsed_ms, "memory_kb": mem_kb,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return {
            "stdout": "", "stderr": f"Timed out after {timeout_s}s",
            "exit_code": -1, "timed_out": True,
            "time_ms": elapsed_ms, "memory_kb": 0,
        }


# ══════════════════════════════════════════════════════════════════
# Output Validator
# ══════════════════════════════════════════════════════════════════

def validate_output(expected: str, actual: str) -> dict[str, Any]:
    exp = expected.strip().rstrip("\n")
    act = actual.strip().rstrip("\n")
    passed = exp == act
    diff = ""
    if not passed:
        exp_lines = exp.split("\n")
        act_lines = act.split("\n")
        parts = []
        for i in range(max(len(exp_lines), len(act_lines))):
            e = exp_lines[i] if i < len(exp_lines) else "<missing>"
            a = act_lines[i] if i < len(act_lines) else "<missing>"
            if e != a:
                parts.append(f"  Line {i+1}:")
                parts.append(f"    - expected: {e}")
                parts.append(f"    + actual:   {a}")
        diff = "\n".join(parts)
    return {"passed": passed, "diff": diff}


# ══════════════════════════════════════════════════════════════════
# Full Pipeline Runner (deterministic stages only)
# ══════════════════════════════════════════════════════════════════

def run_pipeline(spec: ProblemSpec, workspace: str = "workspace/runs") -> ProblemSpec:
    """Run compile → execute → validate.

    Assumes spec.solution_cpp is already populated by the agent.
    Gate must be open before calling this.
    """
    if is_blocked(spec):
        raise ValueError("Cannot run pipeline: gate is blocked. Missing required fields.")
    if needs_intake(spec):
        raise ValueError("Cannot run pipeline: intake required. Missing preferred fields.")

    run_dir = Path(workspace) / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write solution
    source_path = str(run_dir / "solution.cpp")
    binary_path = str(run_dir / "solution")
    Path(source_path).write_text(spec.solution_cpp)

    # Compile
    cr = compile_cpp(source_path, binary_path)
    spec = spec.updated(
        compiled=cr["success"],
        binary_path=cr["binary_path"],
        compiler_warnings=tuple(cr["warnings"]),
        compiler_errors=tuple(cr["errors"]),
        compile_attempts=spec.compile_attempts + 1,
    )

    if not cr["success"]:
        return spec

    # Execute
    case_results = []
    for sample in spec.samples:
        case_dir = run_dir / "cases"
        case_dir.mkdir(exist_ok=True)
        (case_dir / f"{sample.case_id}.stdin").write_text(sample.input)
        (case_dir / f"{sample.case_id}.expected").write_text(sample.expected)

        er = execute_binary(spec.binary_path, sample.input)
        (case_dir / f"{sample.case_id}.actual").write_text(er["stdout"])

        case_results.append({
            "case_id": sample.case_id,
            "actual": er["stdout"],
            "passed": False,
            "time_ms": er["time_ms"],
            "memory_kb": er["memory_kb"],
            "error": er["stderr"] if er["exit_code"] != 0 else "",
        })

    spec = spec.updated(case_results=tuple(case_results))

    # Validate
    passed = 0
    failed = 0
    diffs = []
    validated = []

    for cr_item in spec.case_results:
        expected = next((s.expected for s in spec.samples if s.case_id == cr_item["case_id"]), "")
        vr = validate_output(expected, cr_item["actual"])

        if vr["passed"]:
            passed += 1
        else:
            failed += 1
            diffs.append({
                "case_id": cr_item["case_id"],
                "expected": expected,
                "actual": cr_item["actual"],
                "diff": vr["diff"],
            })

        validated.append({**cr_item, "passed": vr["passed"]})

    spec = spec.updated(
        case_results=tuple(validated),
        passed_samples=passed,
        failed_samples=failed,
        diffs=tuple(diffs),
    )

    return spec
