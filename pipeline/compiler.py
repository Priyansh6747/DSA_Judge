"""Compile C++ source code — deterministic, no LLM calls.

Exposes:
    compile(source_cpp, driver_cpp, run_dir, func_name) -> CompileResult
    classify_compiler_errors(stderr) -> list[ErrorNode]
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from schemas.repair_spec import ErrorNode, CompileResult


def compile(
    source_cpp: str,
    driver_cpp: str = "",
    run_dir: Path | None = None,
    func_name: str = "",
    binary_name: str = "solution",
) -> CompileResult:
    """Compile C++ source + driver into a binary.

    Args:
        source_cpp: the solution code
        driver_cpp: the test harness (optional, concatenated after source)
        run_dir: working directory for intermediate files
        func_name: expected function name (checked post-compile)
        binary_name: output binary name

    Returns:
        CompileResult with success status, binary path, errors
    """
    if run_dir is None:
        run_dir = Path("/tmp/dsa-judge-compile")
    run_dir.mkdir(parents=True, exist_ok=True)

    combined = _combine_source(source_cpp, driver_cpp)
    source_path = run_dir / "solution.cpp"
    binary_path = run_dir / binary_name
    source_path.write_text(combined)

    result = _do_compile(str(source_path), str(binary_path))

    if not result["success"]:
        errors = classify_compiler_errors(result["stderr"])
        return CompileResult(
            success=False,
            binary_path="",
            attempts=1,
            errors=tuple(errors),
            warnings=tuple(result["warnings"]),
        )

    # Post-compile check: function name present
    if func_name and func_name not in combined:
        return CompileResult(
            success=False,
            binary_path="",
            attempts=1,
            errors=(ErrorNode(
                kind="undeclared",
                message=f"Function '{func_name}' not found in compiled source",
            ),),
            warnings=tuple(result["warnings"]),
        )

    return CompileResult(
        success=True,
        binary_path=str(binary_path),
        attempts=1,
        errors=(),
        warnings=tuple(result["warnings"]),
    )


def _combine_source(source_cpp: str, driver_cpp: str) -> str:
    """Combine solution and driver into a single source file."""
    if not driver_cpp:
        return source_cpp
    if "#include \"solution" in driver_cpp or "#include <solution" in driver_cpp:
        return driver_cpp
    return f"{source_cpp}\n\n{driver_cpp}"


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
            continue

        kind = _classify_error_kind(message)
        errors.append(ErrorNode(
            kind=kind,
            file=file_path,
            line=line,
            column=col,
            message=message,
        ))

    if not errors and "error" in stderr.lower():
        errors.append(ErrorNode(
            kind="other",
            message=stderr[:500],
        ))

    return errors


def _classify_error_kind(message: str) -> str:
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


def has_malicious_calls(code: str) -> bool:
    """Check for dangerous function calls in code."""
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
