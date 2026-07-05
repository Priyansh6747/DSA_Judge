"""Pipeline engine — thin orchestrator for Stages 1-7.

Handles: parse → intake → driver → solution → test gen → compile → execute → report.

The engine chains the new modules and persists intermediate JSON.
LLM work happens inside each module; the engine just orchestrates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.problem_spec import ProblemSpecJSON, RunState, Mode
from schemas.repair_spec import GateResult
from pipeline.parser import parse_problem, ParseError
from pipeline.intake import classify, apply_user_response
from pipeline.driver_gen import generate_driver, DriverGenError
from pipeline.solution_gen import generate_solution, SolutionGenError
from pipeline.test_gen import synthesize, TestGenError
from pipeline.compiler import compile_with_repairs
from pipeline.executor import execute_with_repairs
from pipeline.reporter import build_report


def run_pipeline(
    spec: ProblemSpecJSON,
    workspace: str = "workspace/runs",
    max_compile_attempts: int = 5,
    max_exec_attempts: int = 5,
) -> RunState:
    """Run the full pipeline: driver → solution → tests → compile → execute → report.

    Assumes spec is complete (gate status == "open").
    Returns a RunState with all results populated.
    """
    run_dir = Path(workspace) / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Persist problem spec
    (run_dir / "problem_spec.json").write_text(
        json.dumps(spec.model_dump(), indent=2, default=str)
    )

    state = RunState(spec=spec, run_dir=run_dir, run_id=spec.run_id)

    # ── Stage 3: Driver Generation ──
    try:
        driver_artifact = generate_driver(spec, run_dir)
        state = state.model_copy(update={
            "driver_cpp": driver_artifact.driver_cpp,
            "driver_is_self_contained": driver_artifact.is_self_contained,
        })
        if driver_artifact.driver_cpp:
            (run_dir / "driver.cpp").write_text(driver_artifact.driver_cpp)
        (run_dir / "driver.json").write_text(
            json.dumps(driver_artifact.model_dump(), indent=2)
        )
    except DriverGenError as e:
        state = state.model_copy(update={
            "known_weaknesses": state.known_weaknesses + (f"Driver generation failed: {e}",),
        })

    # ── Stage 5: Edge Test Generation (before solution, to get edge cases) ──
    try:
        test_plan = synthesize(spec, run_dir)
        state = state.model_copy(update={
            "test_plan_cases": tuple(tc.model_dump() for tc in test_plan.cases),
            "brute_force_cpp": test_plan.brute_force_cpp,
        })
        (run_dir / "tests.json").write_text(
            json.dumps(test_plan.model_dump(), indent=2, default=str)
        )
        # Write test files
        tests_dir = run_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        for tc in test_plan.cases:
            (tests_dir / f"{tc.id}.in").write_text(tc.input)
            if tc.expected:
                (tests_dir / f"{tc.id}.exp").write_text(tc.expected)
    except TestGenError as e:
        state = state.model_copy(update={
            "known_weaknesses": state.known_weaknesses + (f"Test generation failed: {e}",),
        })

    # ── Stage 4: Solution Generation ──
    edge_cases = tuple(
        tc.get("why", "") for tc in state.test_plan_cases if tc.get("why")
    )
    try:
        solution_artifact = generate_solution(spec, edge_cases, run_dir)
        state = state.model_copy(update={
            "solution_cpp": solution_artifact.solution_cpp,
            "algorithm": solution_artifact.algorithm,
            "complexity_time": solution_artifact.complexity_time,
            "complexity_memory": solution_artifact.complexity_memory,
            "edge_cases": solution_artifact.edge_cases_addressed,
        })
        (run_dir / "solution.cpp").write_text(solution_artifact.solution_cpp)
        (run_dir / "solution.json").write_text(
            json.dumps(solution_artifact.model_dump(), indent=2)
        )
    except SolutionGenError as e:
        state = state.model_copy(update={
            "known_weaknesses": state.known_weaknesses + (f"Solution generation failed: {e}",),
        })
        return state

    # ── Stage 6: Compile ──
    compile_result = compile_with_repairs(
        spec=spec,
        solution_cpp=state.solution_cpp or "",
        driver_cpp=state.driver_cpp or "",
        run_dir=run_dir,
        max_attempts=max_compile_attempts,
        func_name=spec.function_signature.name,
        class_name=spec.function_signature.class_name,
    )
    state = state.model_copy(update={
        "compiled": compile_result.success,
        "binary_path": compile_result.binary_path,
        "compile_history": (compile_result.model_dump(),),
    })
    (run_dir / "compile_history.json").write_text(
        json.dumps(compile_result.model_dump(), indent=2, default=str)
    )

    if not compile_result.success:
        return state

    # ── Stage 7: Execute + Validate + Repair ──
    # Combine sample cases and edge test cases
    all_cases = []
    for s in spec.samples:
        all_cases.append({
            "id": s.id,
            "input": s.input,
            "expected": s.expected,
            "category": "sample",
        })
    for tc in state.test_plan_cases:
        if tc.get("expected"):  # Only include cases with expected output
            all_cases.append(tc)

    exec_result = execute_with_repairs(
        spec=spec,
        binary_path=state.binary_path,
        test_cases=all_cases,
        driver_cpp=state.driver_cpp or "",
        run_dir=run_dir,
        max_attempts=max_exec_attempts,
    )

    state = state.model_copy(update={
        "case_results": tuple(cr.model_dump() for cr in exec_result.case_results),
        "passed_samples": exec_result.passed,
        "failed_samples": exec_result.failed,
        "exec_history": (exec_result.model_dump(),),
    })
    (run_dir / "exec_history.json").write_text(
        json.dumps(exec_result.model_dump(), indent=2, default=str)
    )

    # ── Build Report ──
    report = build_report(state)
    state = state.model_copy(update={
        "report_md": report.report_md,
        "confidence": report.confidence,
        "known_weaknesses": state.known_weaknesses + tuple(report.known_weaknesses),
    })
    (run_dir / "report.md").write_text(report.report_md)

    return state
