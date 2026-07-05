"""Stage 6: Compile — with LLM repair loop.

Compiles C++ code, classifies errors, asks LLM to fix, retries up to N times.
Every repair is checked: signature intact, no malicious calls, syntax valid.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from schemas.problem_spec import ProblemSpecJSON
from schemas.repair_spec import ErrorNode, CompileResult
from pipeline import llm as llm_mod


class CompileError(Exception):
    pass


def compile_with_repairs(
    spec: ProblemSpecJSON,
    solution_cpp: str,
    driver_cpp: str = "",
    run_dir: Path | None = None,
    max_attempts: int = 5,
    func_name: str = "",
    class_name: str = "",
) -> CompileResult:
    """Compile solution with up to max_attempts repair iterations.

    Returns CompileResult with success status, binary path, errors, etc.
    """
    if run_dir is None:
        run_dir = Path("/tmp/dsa-judge-compile")
    run_dir.mkdir(parents=True, exist_ok=True)

    source_path = run_dir / "solution.cpp"
    binary_path = run_dir / "solution"

    current_solution = solution_cpp
    all_errors: list[ErrorNode] = []
    warnings: list[str] = []

    for attempt in range(max_attempts):
        # Write combined source
        combined = _combine_source(current_solution, driver_cpp)
        source_path.write_text(combined)

        # Compile
        result = _do_compile(str(source_path), str(binary_path))

        if result["success"]:
            return CompileResult(
                success=True,
                binary_path=str(binary_path),
                attempts=attempt + 1,
                errors=tuple(all_errors),
                warnings=tuple(result["warnings"]),
            )

        # Classify errors
        errors = classify_compiler_errors(result["stderr"])
        all_errors = list(errors)
        warnings = result["warnings"]

        # Last attempt — don't try to repair
        if attempt == max_attempts - 1:
            break

        # Validate solution hasn't been corrupted
        if func_name and func_name not in current_solution:
            # Solution lost the function name — try to recover
            pass  # Let LLM fix it

        if _has_malicious_calls(current_solution):
            # Don't repair solutions with malicious calls
            break

        # Ask LLM to repair
        try:
            previous_attempts = [
                {"attempt": i + 1, "errors_fixed": [], "errors_remaining": [str(e.message)[:100]]}
                for i, e in enumerate(all_errors[-3:])  # Last 3 errors
            ]

            raw = llm_mod.complete("compile_repair", {
                "solution_cpp": current_solution,
                "errors": [e.model_dump() for e in errors],
                "attempt": attempt + 1,
                "previous_attempts": previous_attempts,
            }, expect_json=True)

            patched = raw.get("solution_cpp", "")
            if not patched:
                continue

            # Validate patched solution
            if func_name and func_name not in patched:
                continue  # Signature corrupted — skip this patch

            if _has_malicious_calls(patched):
                continue  # Malicious calls introduced — skip

            current_solution = patched

        except (llm_mod.LLMError, Exception):
            continue  # LLM failed — try next attempt with current code

    return CompileResult(
        success=False,
        binary_path="",
        attempts=max_attempts,
        errors=tuple(all_errors),
        warnings=tuple(warnings),
    )


def _combine_source(solution_cpp: str, driver_cpp: str) -> str:
    """Combine solution and driver into a single source file.

    Strategy: put solution first, then driver. The driver references
    solution symbols via #include or direct linkage.
    """
    if not driver_cpp:
        return solution_cpp

    # Check if driver already includes the solution
    if '#include "solution' in driver_cpp or "#include \"solution" in driver_cpp:
        return driver_cpp  # Driver handles its own includes

    # Concatenate: solution + driver
    return f"{solution_cpp}\n\n{driver_cpp}"


def _do_compile(source_path: str, binary_path: str) -> dict[str, Any]:
    """Run g++ and return result dict."""
    cmd = [
        "g++", "-std=c++20", "-O2", "-Wall", "-Wextra",
        "-o", binary_path, source_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "binary_path": "",
            "warnings": [],
            "stderr": "Compilation timed out after 30s",
        }

    warnings = [
        line for line in result.stderr.splitlines()
        if "warning:" in line.lower()
    ]

    return {
        "success": result.returncode == 0,
        "binary_path": binary_path if result.returncode == 0 else "",
        "warnings": warnings,
        "stderr": result.stderr,
    }


def classify_compiler_errors(stderr: str) -> list[ErrorNode]:
    """Parse g++ stderr into structured ErrorNode list."""
    errors: list[ErrorNode] = []

    # Pattern: file:line:col: error: message
    # or: file:line: error: message
    pattern = re.compile(
        r"^(.+?):(\d+)(?::(\d+))?:\s*(error|warning):\s*(.+)$",
        re.MULTILINE,
    )

    for match in pattern.finditer(stderr):
        file_path = match.group(1)
        line = int(match.group(2))
        col = int(match.group(3)) if match.group(3) else 0
        kind_str = match.group(4)
        message = match.group(5).strip()

        if kind_str == "warning":
            continue  # Skip warnings

        # Classify the error kind
        kind = _classify_error_kind(message)

        errors.append(ErrorNode(
            kind=kind,
            file=file_path,
            line=line,
            column=col,
            message=message,
        ))

    # If no structured errors found but compilation failed, add a generic one
    if not errors and "error" in stderr.lower():
        errors.append(ErrorNode(
            kind="other",
            file="",
            line=0,
            column=0,
            message=stderr[:500],
        ))

    return errors


def _classify_error_kind(message: str) -> str:
    """Classify a compiler error message into a kind."""
    lower = message.lower()
    if "expected" in lower or "unterminated" in lower or "stray" in lower:
        return "syntax"
    if "no match" in lower or "cannot convert" in lower or "invalid conversion" in lower:
        return "type"
    if "was not declared" in lower or "undeclared" in lower or "not a member" in lower:
        return "undeclared"
    if "template" in lower:
        return "template"
    if "undefined reference" in lower or "multiple definition" in lower:
        return "linker"
    return "other"


def _has_malicious_calls(code: str) -> bool:
    """Check for dangerous function calls."""
    dangerous = [
        r'\bsystem\s*\(',
        r'\bexec\s*\(',
        r'\bpopen\s*\(',
        r'\bfopen\s*\(',
        r'\bfreopen\s*\(',
        r'#include\s*<curl/',
        r'#include\s*<winsock',
    ]
    for pattern in dangerous:
        if re.search(pattern, code):
            return True
    return False
