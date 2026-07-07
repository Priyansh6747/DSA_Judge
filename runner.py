#!/usr/bin/env python3
"""DSA Judge — deterministic tooling for agent-orchestrated solving.

The agent (LLM) handles all reasoning: parsing, code generation, repair.
This CLI exposes only deterministic operations: compile, execute, diff.

Usage:
    # Compile source + driver into binary
    python3 runner.py compile --source solution.cpp --driver driver.cpp --out-dir workspace/run1

    # Execute binary against test cases (JSON file or inline)
    python3 runner.py execute --binary workspace/run1/solution --tests tests.json

    # Run both compile + execute in one shot
    python3 runner.py run --source solution.cpp --driver driver.cpp --tests tests.json --out-dir workspace/run1

    # Just compile (no driver)
    python3 runner.py compile --source solution.cpp --out-dir workspace/run1

Exit codes:
    0 — success (all tests passed or compilation succeeded)
    1 — compilation failed
    2 — one or more tests failed
    3 — runtime error / TLE
"""

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))

from pipeline.compiler import compile, CompileResult
from pipeline.executor import execute, ExecResult
from pipeline.reporter import build_report
from schemas.problem_spec import ProblemSpecJSON, RunState


def cmd_compile(args):
    """Compile source + driver into a binary."""
    source = Path(args.source).read_text()
    driver = Path(args.driver).read_text() if args.driver else ""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = compile(
        source_cpp=source,
        driver_cpp=driver,
        run_dir=out_dir,
        func_name=args.func_name or "",
    )

    # Output structured JSON to stdout
    print(json.dumps(result.model_dump(), indent=2, default=str))

    return 0 if result.success else 1


def cmd_execute(args):
    """Execute binary against test cases."""
    # Load test cases
    if args.tests:
        with open(args.tests) as f:
            data = json.load(f)
        # Accept both {cases: [...]} and [...] formats
        if isinstance(data, list):
            test_cases = data
        elif isinstance(data, dict) and "cases" in data:
            test_cases = data["cases"]
        else:
            test_cases = [data]
    elif args.stdin:
        test_cases = json.loads(sys.stdin.read())
    else:
        print("Error: --tests or --stdin required", file=sys.stderr)
        return 3

    result = execute(
        binary_path=args.binary,
        test_cases=test_cases,
        timeout_s=args.timeout,
        memory_limit_mb=args.memory,
    )

    print(json.dumps(result.model_dump(), indent=2, default=str))

    if result.failed > 0:
        return 2
    return 0


def cmd_run(args):
    """Compile + execute in one shot."""
    source = Path(args.source).read_text()
    driver = Path(args.driver).read_text() if args.driver else ""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Compile
    compile_result = compile(
        source_cpp=source,
        driver_cpp=driver,
        run_dir=out_dir,
        func_name=args.func_name or "",
    )

    if not compile_result.success:
        print(json.dumps({
            "stage": "compile",
            "result": compile_result.model_dump(),
        }, indent=2, default=str))
        return 1

    # Step 2: Load tests
    if args.tests:
        with open(args.tests) as f:
            data = json.load(f)
        if isinstance(data, list):
            test_cases = data
        elif isinstance(data, dict) and "cases" in data:
            test_cases = data["cases"]
        else:
            test_cases = [data]
    elif args.stdin:
        test_cases = json.loads(sys.stdin.read())
    else:
        test_cases = []

    if not test_cases:
        # No tests — just report compile success
        print(json.dumps({
            "stage": "compile",
            "result": compile_result.model_dump(),
            "message": "Compilation succeeded, no tests provided",
        }, indent=2, default=str))
        return 0

    # Step 3: Execute
    exec_result = execute(
        binary_path=compile_result.binary_path,
        test_cases=test_cases,
        timeout_s=args.timeout,
        memory_limit_mb=args.memory,
    )

    # Combined output
    output = {
        "compile": compile_result.model_dump(),
        "execute": exec_result.model_dump(),
        "all_passed": exec_result.success,
        "passed": exec_result.passed,
        "failed": exec_result.failed,
    }
    print(json.dumps(output, indent=2, default=str))

    if exec_result.failed > 0:
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description="DSA Judge — deterministic tooling")
    sub = parser.add_subparsers(dest="command", required=True)

    # compile
    p_compile = sub.add_parser("compile", help="Compile C++ source into binary")
    p_compile.add_argument("--source", required=True, help="Path to solution.cpp")
    p_compile.add_argument("--driver", help="Path to driver.cpp (optional)")
    p_compile.add_argument("--out-dir", default="workspace/run", help="Output directory")
    p_compile.add_argument("--func-name", help="Expected function name (verified post-compile)")

    # execute
    p_exec = sub.add_parser("execute", help="Execute binary against test cases")
    p_exec.add_argument("--binary", required=True, help="Path to compiled binary")
    p_exec.add_argument("--tests", help="Path to tests JSON file")
    p_exec.add_argument("--stdin", action="store_true", help="Read test cases from stdin")
    p_exec.add_argument("--timeout", type=float, default=5.0, help="Per-case timeout (seconds)")
    p_exec.add_argument("--memory", type=int, default=256, help="Per-case memory limit (MB)")

    # run (compile + execute)
    p_run = sub.add_parser("run", help="Compile and execute in one shot")
    p_run.add_argument("--source", required=True, help="Path to solution.cpp")
    p_run.add_argument("--driver", help="Path to driver.cpp (optional)")
    p_run.add_argument("--tests", help="Path to tests JSON file")
    p_run.add_argument("--stdin", action="store_true", help="Read test cases from stdin")
    p_run.add_argument("--out-dir", default="workspace/run", help="Output directory")
    p_run.add_argument("--func-name", help="Expected function name")
    p_run.add_argument("--timeout", type=float, default=5.0, help="Per-case timeout (seconds)")
    p_run.add_argument("--memory", type=int, default=256, help="Per-case memory limit (MB)")

    args = parser.parse_args()

    if args.command == "compile":
        sys.exit(cmd_compile(args))
    elif args.command == "execute":
        sys.exit(cmd_execute(args))
    elif args.command == "run":
        sys.exit(cmd_run(args))


if __name__ == "__main__":
    main()
