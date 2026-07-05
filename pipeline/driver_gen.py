"""Stage 3: Driver Code Generation — harness for testing.

Generates a main() driver that reads stdin, calls the solution, writes stdout.
For main()-style problems (CF/AtCoder/CSES), marks as self-contained.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from schemas.problem_spec import ProblemSpecJSON
from schemas.driver_spec import DriverArtifact
from pipeline import llm as llm_mod


class DriverGenError(Exception):
    pass


def generate_driver(spec: ProblemSpecJSON, run_dir: Path) -> DriverArtifact:
    """Generate a C++ driver/harness for the problem.

    For LeetCode-style problems, generates a main() that reads stdin,
    calls Solution().method(), writes stdout.

    For main()-style problems, returns an empty self-contained artifact.
    """
    # If no class name and function is main → self-contained
    if not spec.function_signature.class_name and spec.function_signature.name == "main":
        return DriverArtifact(
            driver_cpp="",
            linker_note="self-contained: solution has its own main()",
            expected_stdio_format="stdin/stdout as described in problem",
            is_self_contained=True,
        )

    # If no signature at all, we still need a driver — generate one
    func_name = spec.function_signature.name or "solve"
    class_name = spec.function_signature.class_name or ""
    return_type = spec.function_signature.return_type or "int"
    arguments = spec.function_signature.arguments or "()"

    samples_for_prompt = [
        {"id": s.id, "input": s.input, "expected": s.expected}
        for s in spec.samples
    ]

    try:
        raw = llm_mod.complete("driver", {
            "title": spec.title,
            "class_name": class_name,
            "function_name": func_name,
            "return_type": return_type,
            "arguments": arguments,
            "platform": spec.platform,
            "input_format": spec.input_format or "as shown in samples",
            "output_format": spec.output_format or "as shown in samples",
            "samples": samples_for_prompt,
        }, expect_json=True)
    except llm_mod.LLMError as e:
        raise DriverGenError(f"LLM failed to generate driver: {e}") from e

    artifact = DriverArtifact(**raw)

    # If self-contained, return immediately
    if artifact.is_self_contained:
        return artifact

    # Deterministic guard: syntax check the driver with a stub solution
    if not artifact.driver_cpp:
        raise DriverGenError("Driver is not self-contained but driver_cpp is empty")

    _validate_driver_syntax(artifact.driver_cpp, spec, run_dir)

    return artifact


def _validate_driver_syntax(driver_cpp: str, spec: ProblemSpecJSON, run_dir: Path) -> None:
    """Run g++ -fsyntax-only on driver + stub solution. Retry once on failure."""
    # Create a stub solution
    stub = _make_stub_solution(spec)
    combined = f"{stub}\n\n{driver_cpp}"

    test_file = run_dir / "_driver_syntax_check.cpp"
    test_file.write_text(combined)

    cmd = ["g++", "-std=c++20", "-fsyntax-only", "-x", "c++", str(test_file)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

    test_file.unlink(missing_ok=True)

    if result.returncode != 0:
        raise DriverGenError(
            f"Driver syntax check failed:\n{result.stderr[:1000]}"
        )


def _make_stub_solution(spec: ProblemSpecJSON) -> str:
    """Generate a minimal stub solution for syntax checking."""
    cls = spec.function_signature.class_name
    ret = spec.function_signature.return_type or "int"
    name = spec.function_signature.name or "solve"
    args = spec.function_signature.arguments or "()"

    if cls:
        return (
            f"#include <bits/stdc++.h>\n"
            f"using namespace std;\n"
            f"class {cls} {{\npublic:\n"
            f"    {ret} {name}{args} {{\n"
            f"        return {{}};\n"
            f"    }}\n"
            f"}};\n"
        )
    else:
        return (
            f"#include <bits/stdc++.h>\n"
            f"using namespace std;\n"
            f"{ret} {name}{args} {{\n"
            f"    return {{}};\n"
            f"}}\n"
        )
