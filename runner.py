#!/usr/bin/env python3
"""DSA Judge runner — standalone pipeline execution.

Usage:
    echo "<problem>" | python3 runner.py --stdin
    python3 runner.py --problem "<problem text>"
    python3 runner.py --problem-file problem.txt

This runner handles the deterministic stages (compile, execute, validate).
The agent handles LLM stages (parse, plan, generate, verify) before calling this.
"""

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))

from pipeline.engine import run_pipeline, parse_problem
from pipeline.state import JudgeState, TestCase


def main():
    parser = argparse.ArgumentParser(description="DSA Judge Runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--problem", help="Problem text directly")
    group.add_argument("--problem-file", help="Path to problem text file")
    group.add_argument("--stdin", action="store_true", help="Read problem from stdin")
    parser.add_argument("--workspace", default=str(SKILL_DIR / "workspace" / "runs"))
    args = parser.parse_args()

    if args.stdin:
        problem_text = sys.stdin.read()
    elif args.problem:
        problem_text = args.problem
    else:
        problem_text = Path(args.problem_file).read_text()

    # Parse problem
    parsed = parse_problem(problem_text)

    # Create state
    state = JudgeState.new(problem_text)
    state = state.updated(
        problem_title=parsed.get("title", ""),
        constraints=parsed.get("constraints", {}),
        input_format=parsed.get("input_format", ""),
        output_format=parsed.get("output_format", ""),
        samples=tuple(
            TestCase(case_id=s["id"], input=s["input"], expected=s["expected"])
            for s in parsed.get("samples", [])
        ),
    )

    print(f"Run {state.run_id} — {state.problem_title}")
    print(f"Parsed {len(state.samples)} sample cases")
    print()

    # The agent must populate solution_cpp before running the pipeline.
    # This runner is for testing the deterministic stages.
    if not state.solution_cpp.strip():
        print("No solution provided. Use the SKILL.md workflow to generate code first.")
        print("Or pass --solution <file> to provide a pre-written solution.")
        sys.exit(1)

    state = run_pipeline(state, workspace=args.workspace)

    print(f"Compilation: {'✅' if state.compiled else '❌'} ({state.compile_attempts} attempt(s))")
    if state.compiler_errors:
        for e in state.compiler_errors:
            print(f"  Error: {e}")

    print(f"\nSamples: {state.passed_samples}/{state.passed_samples + state.failed_samples} passed")
    for cr in state.case_results:
        status = "✅" if cr.passed else "❌"
        print(f"  {cr.case_id}: {status} ({cr.time_ms:.1f}ms)")
        if not cr.passed:
            for d in state.diffs:
                if d["case_id"] == cr.case_id:
                    print(f"    {d['diff']}")

    print(f"\nConfidence: {state.confidence}")


if __name__ == "__main__":
    main()
