#!/usr/bin/env python3
"""DSA Judge runner — self-sufficient pipeline execution.

Usage:
    python3 runner.py --problem-file problem.txt
    python3 runner.py --problem "problem text"
    python3 runner.py --stdin
    python3 runner.py --resume <run_id>

Exit codes:
    0 — success, report written to workspace/<run_id>/report.md
    2 — blocked intake (agent must ask user, read gate.json)
    3 — soft intake (agent prompts user, read gate.json)
    4 — compile failed after repairs
    5 — exec/tests failed after repairs
    6 — parser gave up (rephrase the problem)
"""

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))

from schemas.problem_spec import ProblemSpecJSON, RunState
from pipeline.parser import parse_problem, ParseError
from pipeline.intake import classify, apply_user_response
from pipeline.engine import run_pipeline
from pipeline.reporter import build_report


def main():
    parser = argparse.ArgumentParser(description="DSA Judge Runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--problem", help="Problem text directly")
    group.add_argument("--problem-file", help="Path to problem text file")
    group.add_argument("--stdin", action="store_true", help="Read problem from stdin")
    group.add_argument("--resume", help="Resume a previous run by run_id")
    parser.add_argument("--mode", default="solve",
                        choices=["solve", "verify", "repair", "explain"])
    parser.add_argument("--workspace", default=str(SKILL_DIR / "workspace" / "runs"))
    parser.add_argument("--max-compile-attempts", type=int, default=5)
    parser.add_argument("--max-exec-attempts", type=int, default=5)
    args = parser.parse_args()

    workspace = Path(args.workspace)

    # ── Resume mode ──
    if args.resume:
        run_dir = workspace / args.resume
        if not run_dir.exists():
            print(f"Run {args.resume} not found at {run_dir}", file=sys.stderr)
            sys.exit(1)
        _resume_run(run_dir, args)
        return

    # ── Read problem text ──
    if args.stdin:
        problem_text = sys.stdin.read()
    elif args.problem:
        problem_text = args.problem
    else:
        problem_text = Path(args.problem_file).read_text()

    # ── Stage 1: Parse ──
    try:
        spec = parse_problem(problem_text, mode=args.mode)
    except ParseError as e:
        print(f"Parse failed: {e}", file=sys.stderr)
        sys.exit(6)

    # Persist problem spec
    run_dir = workspace / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "problem_spec.json").write_text(
        json.dumps(spec.model_dump(), indent=2, default=str)
    )

    # ── Stage 2: Intake Gate ──
    gate = classify(spec)
    (run_dir / "gate.json").write_text(
        json.dumps(gate.model_dump(), indent=2)
    )

    if gate.status == "blocked":
        print(gate.question_md, file=sys.stderr)
        sys.exit(2)

    if gate.status == "intake":
        print(gate.question_md, file=sys.stderr)
        sys.exit(3)

    # ── Gate is open — run pipeline ──
    print(f"Run {spec.run_id} — {spec.title}")
    print(f"Parsed {len(spec.samples)} sample(s)")
    print()

    state = run_pipeline(
        spec,
        workspace=str(workspace),
        max_compile_attempts=args.max_compile_attempts,
        max_exec_attempts=args.max_exec_attempts,
    )

    # Print summary
    print(f"Compilation: {'✅' if state.compiled else '❌'} ({len(state.compile_history)} attempt(s))")
    print(f"Samples: {state.passed_samples}/{state.passed_samples + state.failed_samples} passed")
    print(f"Confidence: {state.confidence}")
    print()

    if state.report_md:
        print(state.report_md)

    # Exit code
    if not state.compiled:
        sys.exit(4)
    if state.failed_samples > 0:
        sys.exit(5)
    sys.exit(0)


def _resume_run(run_dir: Path, args):
    """Resume a previous run after intake."""
    # Read the gate response
    gate_response_path = run_dir / "gate_response.json"
    if not gate_response_path.exists():
        print(
            f"No gate_response.json found in {run_dir}.\n"
            f"Write the user's answers to {gate_response_path} and re-run.",
            file=sys.stderr,
        )
        sys.exit(3)

    # Load the spec
    spec_path = run_dir / "problem_spec.json"
    if not spec_path.exists():
        print(f"No problem_spec.json found in {run_dir}", file=sys.stderr)
        sys.exit(1)

    spec_data = json.loads(spec_path.read_text())
    spec = ProblemSpecJSON(**spec_data)

    # Apply user response
    gate_response = json.loads(gate_response_path.read_text())
    spec = apply_user_response(spec, gate_response)

    # Re-check gate
    gate = classify(spec)
    (run_dir / "gate.json").write_text(json.dumps(gate.model_dump(), indent=2))

    if gate.status == "blocked":
        print(gate.question_md, file=sys.stderr)
        sys.exit(2)
    if gate.status == "intake":
        print(gate.question_md, file=sys.stderr)
        sys.exit(3)

    # Run pipeline
    print(f"Resuming run {spec.run_id} — {spec.title}")

    state = run_pipeline(
        spec,
        workspace=str(run_dir.parent),
        max_compile_attempts=args.max_compile_attempts,
        max_exec_attempts=args.max_exec_attempts,
    )

    print(f"Compilation: {'✅' if state.compiled else '❌'}")
    print(f"Samples: {state.passed_samples}/{state.passed_samples + state.failed_samples} passed")
    print(f"Confidence: {state.confidence}")

    if state.report_md:
        print(state.report_md)

    if not state.compiled:
        sys.exit(4)
    if state.failed_samples > 0:
        sys.exit(5)
    sys.exit(0)


if __name__ == "__main__":
    main()
