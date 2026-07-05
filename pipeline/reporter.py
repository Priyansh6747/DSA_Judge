"""Final Report Builder — Stage 9.

Builds a markdown report from the RunState, covering all stages.
"""

from __future__ import annotations

from schemas.problem_spec import RunState
from schemas.report_spec import ReportJSON


def build_report(state: RunState) -> ReportJSON:
    """Build a structured report from the run state."""
    # Determine confidence
    confidence = _compute_confidence(state)

    # Build markdown report
    report_md = _build_markdown(state, confidence)

    return ReportJSON(
        mode=state.spec.mode,
        gate_status="open",
        compiled=state.compiled,
        compile_attempts=len(state.compile_history),
        algorithm=state.algorithm,
        complexity_time=state.complexity_time,
        complexity_memory=state.complexity_memory,
        edge_cases=state.edge_cases,
        passed=state.passed_samples,
        failed=state.failed_samples,
        case_results=state.case_results,
        platform=state.spec.platform,
        platform_confidence=state.spec.platform_confidence,
        confidence=confidence,
        known_weaknesses=state.known_weaknesses,
        report_md=report_md,
        driver_generated=state.driver_cpp is not None,
        driver_is_self_contained=state.driver_is_self_contained,
        edge_test_categories=tuple(
            tc.get("category", "") for tc in state.test_plan_cases if tc.get("category")
        ),
        edge_tests_dropped=0,
        oracle_used=state.brute_force_cpp is not None,
        compile_repair_attempts=sum(
            h.get("attempts", 1) for h in state.compile_history
        ),
        exec_repair_attempts=sum(
            h.get("attempts", 1) for h in state.exec_history
        ),
        regressions_caught=0,
    )


def _compute_confidence(state: RunState) -> str:
    """Compute overall confidence level."""
    if not state.compiled:
        return "LOW"
    if state.failed_samples > 0:
        return "LOW"
    if not state.spec.has_constraints():
        return "MEDIUM"
    if state.spec.parse_confidence < 0.5:
        return "MEDIUM"
    return "HIGH"


def _build_markdown(state: RunState, confidence: str) -> str:
    """Build the markdown report."""
    lines = [
        "# DSA Judge Report",
        "",
        f"## Mode: {state.spec.mode}",
        "",
        "## Requirement Check",
        f"  Gate: OPEN",
        f"  {'✅' if state.spec.description else '❌'} Description",
        f"  {'✅' if state.spec.has_samples() else '❌'} Samples ({len(state.spec.samples)})",
        f"  {'✅' if state.spec.has_constraints() else '⚠️'} Constraints",
        f"  {'✅' if state.spec.has_template() else '⚠️'} Template",
        f"  {'✅' if state.spec.has_function_signature() else '⚠️'} Function Signature",
        "",
        "## Compilation",
    ]

    if state.compiled:
        lines.append(f"  ✅ {len(state.compile_history)} attempt(s)")
    else:
        lines.append(f"  ❌ Failed after {len(state.compile_history)} attempt(s)")
        if state.compile_history:
            last = state.compile_history[-1]
            for err in last.get("errors", [])[:3]:
                lines.append(f"    Error: {err}")

    lines += [
        "",
        "## Algorithm",
        f"  {state.algorithm or 'Not specified'}",
        "",
        "## Complexity",
        f"  Time: {state.complexity_time or 'Not specified'}",
        f"  Memory: {state.complexity_memory or 'Not specified'}",
        "",
        "## Sample Results",
        "  | # | Input | Expected | Actual | Status | Time |",
        "  |---|-------|----------|--------|--------|------|",
    ]

    for cr in state.case_results:
        status = "✅" if cr.get("passed") else "❌"
        time_ms = cr.get("time_ms", 0)
        lines.append(
            f"  | {cr.get('case_id', '?')} | "
            f"{_truncate(cr.get('input', ''))} | "
            f"{_truncate(cr.get('expected', ''))} | "
            f"{_truncate(cr.get('actual', ''))} | "
            f"{status} | {time_ms:.1f}ms |"
        )

    lines += [
        "",
        "## Platform Confidence",
        f"  {state.spec.platform} ({state.spec.platform_confidence:.0%})",
        f"  Source: {state.spec.platform_source}",
        "",
        f"## Confidence: {confidence}",
    ]

    if state.known_weaknesses:
        lines.append("## Weaknesses")
        for w in state.known_weaknesses:
            lines.append(f"  - {w}")

    lines += [
        "",
        f"## Final Verdict",
        f"  {'✅ ALL TESTS PASSED' if state.failed_samples == 0 else '❌ SOME TESTS FAILED'}",
    ]

    return "\n".join(lines)


def _truncate(s: str, max_len: int = 30) -> str:
    """Truncate string for table display."""
    s = s.strip().replace("\n", " ")
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s
