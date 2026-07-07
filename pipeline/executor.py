"""Execute compiled binary against test cases — deterministic, no LLM calls.

Exposes:
    execute(binary_path, test_cases, run_dir) -> ExecResult
    run_case(binary_path, stdin_input, timeout_s, memory_limit_mb) -> dict
"""

from __future__ import annotations

import resource
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from schemas.repair_spec import CaseVerdict, FailureClassification, ExecResult


def execute(
    binary_path: str,
    test_cases: list[dict[str, str]],
    run_dir: Path | None = None,
    timeout_s: float = 5.0,
    memory_limit_mb: int = 256,
) -> ExecResult:
    """Run binary against all test cases and return results.

    Args:
        binary_path: path to compiled binary
        test_cases: list of {id, input, expected, category?}
        run_dir: workspace directory (for logging)
        timeout_s: per-case timeout
        memory_limit_mb: per-case memory limit

    Returns:
        ExecResult with case results, pass/fail counts
    """
    case_results: list[CaseVerdict] = []
    failures: list[FailureClassification] = []

    for tc in test_cases:
        case_id = tc.get("id", "unknown")
        stdin_input = tc.get("input", "")
        expected = tc.get("expected", "")

        result = run_case(binary_path, stdin_input, timeout_s, memory_limit_mb)
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

    passed_count = sum(1 for v in case_results if v.passed)
    failed_count = len(case_results) - passed_count

    return ExecResult(
        success=failed_count == 0,
        attempts=1,
        case_results=tuple(case_results),
        failures=tuple(failures),
        passed=passed_count,
        failed=failed_count,
    )


def run_case(
    binary_path: str,
    stdin_input: str,
    timeout_s: float = 5.0,
    memory_limit_mb: int = 256,
) -> dict[str, Any]:
    """Run a single test case and return raw result."""
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
    exp = expected.strip().rstrip("\n")
    act = actual.strip().rstrip("\n")
    return exp == act


def _classify_failure(
    result: dict[str, Any],
    expected: str,
    actual: str,
) -> FailureClassification:
    if result.get("timed_out"):
        return FailureClassification(
            kind="tle",
            diff=f"Timed out after {result.get('time_ms', 0):.0f}ms",
        )

    exit_code = result.get("exit_code", 0)
    if exit_code != 0:
        if exit_code == -signal.SIGSEGV or exit_code == 139:
            return FailureClassification(kind="sigsegv", exit_code=exit_code, signal="SIGSEGV")
        if exit_code == -signal.SIGFPE or exit_code == 136:
            return FailureClassification(kind="sigfpe", exit_code=exit_code, signal="SIGFPE")
        return FailureClassification(
            kind="rte",
            exit_code=exit_code,
            diff=result.get("stderr", "")[:500],
        )

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
