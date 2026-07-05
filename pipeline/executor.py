"""Stage 7: Execute + Validate + Repair loop.

Runs the compiled binary against all test cases (samples + edge),
validates output, and if failures occur, asks the LLM to fix the solution.
Runs all cases every time to catch regressions.
"""

from __future__ import annotations

import resource
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from schemas.problem_spec import ProblemSpecJSON
from schemas.repair_spec import CaseVerdict, FailureClassification, ExecResult
from pipeline import llm as llm_mod
from pipeline.compiler import compile_with_repairs


def execute_with_repairs(
    spec: ProblemSpecJSON,
    binary_path: str,
    test_cases: list[dict[str, str]],
    driver_cpp: str = "",
    run_dir: Path | None = None,
    max_attempts: int = 5,
    timeout_s: float = 5.0,
    memory_limit_mb: int = 256,
) -> ExecResult:
    """Execute binary against all test cases, repair on failure.

    Args:
        spec: problem specification
        binary_path: path to compiled binary
        test_cases: list of {id, input, expected, category}
        driver_cpp: driver code (for recompilation after repair)
        run_dir: workspace directory
        max_attempts: max repair iterations
        timeout_s: per-case timeout
        memory_limit_mb: per-case memory limit

    Returns:
        ExecResult with success status, case results, failures
    """
    if run_dir is None:
        run_dir = Path("/tmp/dsa-judge-exec")
    run_dir.mkdir(parents=True, exist_ok=True)

    current_solution = spec.user_solution or ""
    current_binary = binary_path
    all_repair_attempts = 0
    regressions_caught = 0

    # Track which cases passed in previous iterations
    previously_passing: set[str] = set()

    for attempt in range(max_attempts):
        # Run all cases
        case_results: list[CaseVerdict] = []
        failures: list[FailureClassification] = []

        for tc in test_cases:
            case_id = tc.get("id", "unknown")
            stdin_input = tc.get("input", "")
            expected = tc.get("expected", "")

            result = _run_case(current_binary, stdin_input, timeout_s, memory_limit_mb)

            actual = result["stdout"]
            passed = _validate_output(expected, actual)

            verdict = CaseVerdict(
                case_id=case_id,
                passed=passed,
                actual=actual,
                time_ms=result["time_ms"],
                memory_kb=result["memory_kb"],
                error=result["stderr"] if result["exit_code"] != 0 else "",
            )
            case_results.append(verdict)

            if not passed:
                classification = _classify_failure(result, expected, actual)
                failures.append(classification)

        # Check if all passed
        if all(v.passed for v in case_results):
            return ExecResult(
                success=True,
                attempts=attempt + 1,
                case_results=tuple(case_results),
                failures=(),
                passed=len(case_results),
                failed=0,
            )

        # Check for regressions
        current_passing = {v.case_id for v in case_results if v.passed}
        regressions = current_passing - previously_passing
        regressions_caught += len(regressions & previously_passing) if attempt > 0 else 0

        # Last attempt — don't try to repair
        if attempt == max_attempts - 1:
            break

        # Build repair prompt
        repair_failures = [
            f.model_dump() for f in failures
        ]
        regression_info = []
        for reg_case_id in (previously_passing - current_passing):
            regression_info.append({
                "case_id": reg_case_id,
                "diff": f"Previously passed, now fails",
            })

        # Ask LLM to repair
        try:
            previous_attempts = [
                {
                    "attempt": i + 1,
                    "fix_description": "previous repair attempt",
                    "result": "still failing",
                }
                for i in range(attempt)
            ]

            raw = llm_mod.complete("exec_repair", {
                "solution_cpp": current_solution,
                "failures": repair_failures,
                "regressions": regression_info,
                "edge_cases": list(spec.parse_notes) or [],
                "attempt": attempt + 1,
                "previous_attempts": previous_attempts,
                "algorithm": "",
                "return_type": spec.function_signature.return_type or "int",
                "class_name": spec.function_signature.class_name or "",
                "function_name": spec.function_signature.name or "solve",
                "arguments": spec.function_signature.arguments or "()",
            }, expect_json=True)

            patched = raw.get("solution_cpp", "")
            if not patched:
                continue

            # Recompile the patched solution
            from pipeline.compiler import _combine_source
            combined = _combine_source(patched, driver_cpp)
            source_path = run_dir / "solution.cpp"
            source_path.write_text(combined)
            new_binary = run_dir / "solution"

            compile_result = compile_with_repairs(
                spec, patched, driver_cpp, run_dir=run_dir,
                max_attempts=3,
                func_name=spec.function_signature.name,
                class_name=spec.function_signature.class_name,
            )

            all_repair_attempts += compile_result.attempts

            if not compile_result.success:
                continue  # Compilation failed — try next attempt

            current_solution = patched
            current_binary = compile_result.binary_path
            previously_passing = current_passing

        except (llm_mod.LLMError, Exception):
            continue

    # Build final result
    passed_count = sum(1 for v in case_results if v.passed)
    failed_count = len(case_results) - passed_count

    return ExecResult(
        success=False,
        attempts=max_attempts,
        case_results=tuple(case_results),
        failures=tuple(failures),
        passed=passed_count,
        failed=failed_count,
    )


def _run_case(
    binary_path: str,
    stdin_input: str,
    timeout_s: float,
    memory_limit_mb: int,
) -> dict[str, Any]:
    """Run a single test case."""
    def set_limits():
        mem_bytes = memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout_s) + 1, int(timeout_s) + 1))
        except (ValueError, OSError):
            pass

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [binary_path], input=stdin_input, capture_output=True, text=True,
            timeout=timeout_s, preexec_fn=set_limits,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        try:
            mem_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception:
            mem_kb = 0

        return {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "timed_out": False,
            "time_ms": elapsed_ms,
            "memory_kb": mem_kb,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return {
            "stdout": "",
            "stderr": f"Timed out after {timeout_s}s",
            "exit_code": -1,
            "timed_out": True,
            "time_ms": elapsed_ms,
            "memory_kb": 0,
        }


def _validate_output(expected: str, actual: str) -> bool:
    """Compare expected vs actual output."""
    exp = expected.strip().rstrip("\n")
    act = actual.strip().rstrip("\n")
    return exp == act


def _classify_failure(
    result: dict[str, Any],
    expected: str,
    actual: str,
) -> FailureClassification:
    """Classify a test case failure."""
    if result.get("timed_out"):
        return FailureClassification(
            kind="tle",
            diff=f"Timed out after {result.get('time_ms', 0):.0f}ms",
        )

    exit_code = result.get("exit_code", 0)
    if exit_code != 0:
        # Check for signals
        if exit_code == -signal.SIGSEGV or exit_code == 139:
            return FailureClassification(kind="sigsegv", exit_code=exit_code, signal="SIGSEGV")
        if exit_code == -signal.SIGFPE or exit_code == 136:
            return FailureClassification(kind="sigfpe", exit_code=exit_code, signal="SIGFPE")
        return FailureClassification(
            kind="rte",
            exit_code=exit_code,
            diff=result.get("stderr", "")[:500],
        )

    # Wrong answer
    diff_lines = []
    exp_lines = expected.strip().split("\n")
    act_lines = actual.strip().split("\n")
    for i in range(max(len(exp_lines), len(act_lines))):
        e = exp_lines[i] if i < len(exp_lines) else "<missing>"
        a = act_lines[i] if i < len(act_lines) else "<missing>"
        if e != a:
            diff_lines.append(f"  Line {i+1}:")
            diff_lines.append(f"    - expected: {e}")
            diff_lines.append(f"    + actual:   {a}")

    return FailureClassification(
        kind="wrong_answer",
        diff="\n".join(diff_lines),
    )
