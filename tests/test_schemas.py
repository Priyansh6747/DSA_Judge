"""Test schemas — round-trip JSON validation."""

import json
import pytest
from schemas.problem_spec import (
    Sample, ConstraintBound, Constraints, FunctionSignature,
    ProblemSpecJSON, RunState,
)
from schemas.driver_spec import DriverArtifact
from schemas.solution_spec import SolutionArtifact
from schemas.test_spec import TestCase, TestPlan
from schemas.repair_spec import (
    ErrorNode, CompileResult, CaseVerdict, FailureClassification,
    ExecResult, GateResult,
)
from schemas.report_spec import ReportJSON


def test_sample_valid():
    s = Sample(id="01", input="hello", expected="world")
    assert s.id == "01"
    assert s.input == "hello"


def test_sample_empty_input():
    with pytest.raises(Exception):
        Sample(id="01", input="", expected="world")


def test_sample_empty_expected():
    with pytest.raises(Exception):
        Sample(id="01", input="hello", expected="")


def test_constraint_bound():
    b = ConstraintBound(variable="n", min=1, max=100000, kind="int")
    assert b.variable == "n"
    assert b.min == 1


def test_constraints_empty():
    c = Constraints()
    assert c.bounds == ()
    assert c.guarantees == ()


def test_function_signature():
    sig = FunctionSignature(name="solve", return_type="int", arguments="(vector<int>& nums)", class_name="Solution")
    assert sig.name == "solve"
    assert sig.class_name == "Solution"


def test_problem_spec_json_roundtrip():
    spec = ProblemSpecJSON(
        run_id="test123",
        mode="solve",
        title="Two Sum",
        description="Given an array...",
        samples=(Sample(id="01", input="2 7 11 15\n9", expected="0 1"),),
        constraints=Constraints(bounds=(
            ConstraintBound(variable="n", min=2, max=10000, kind="int"),
        )),
        platform="leetcode",
        platform_confidence=0.8,
        platform_source="matched: class solution",
        function_signature=FunctionSignature(
            name="twoSum", return_type="vector<int>",
            arguments="(vector<int>& nums, int target)", class_name="Solution",
        ),
    )
    data = spec.model_dump(mode="json")
    json_str = json.dumps(data)
    restored = ProblemSpecJSON(**json.loads(json_str))
    assert restored.title == "Two Sum"
    assert len(restored.samples) == 1
    assert restored.constraints.bounds[0].variable == "n"


def test_problem_spec_extra_forbidden():
    with pytest.raises(Exception):
        ProblemSpecJSON(
            title="test",
            description="test",
            unknown_field="should fail",
        )


def test_driver_artifact():
    da = DriverArtifact(driver_cpp="#include <bits/stdc++.h>", linker_note="includes solution", expected_stdio_format="n nums", is_self_contained=False)
    assert da.driver_cpp.startswith("#include")


def test_solution_artifact():
    sa = SolutionArtifact(solution_cpp="int solve() { return 0; }", algorithm="brute force", complexity_time="O(n)")
    assert sa.algorithm == "brute force"


def test_test_case():
    tc = TestCase(id="edge_01", input="0", expected="0", category="zero", why="boundary", compute_via="provided")
    assert tc.id == "edge_01"


def test_test_plan():
    tp = TestPlan(cases=(
        TestCase(id="01", input="1", expected="1"),
    ))
    assert len(tp.cases) == 1


def test_error_node():
    en = ErrorNode(kind="syntax", file="solution.cpp", line=10, column=5, message="expected ';'")
    assert en.kind == "syntax"


def test_compile_result():
    cr = CompileResult(success=True, binary_path="/tmp/sol", attempts=1)
    assert cr.success


def test_case_verdict():
    cv = CaseVerdict(case_id="01", passed=True, actual="42", time_ms=1.5)
    assert cv.passed


def test_gate_result():
    gr = GateResult(status="open", missing_required=(), missing_preferred=(), question_md="")
    assert gr.status == "open"


def test_report_json():
    rj = ReportJSON(mode="solve", compiled=True, passed=2, failed=0, confidence="HIGH")
    assert rj.compiled


def test_problem_spec_new():
    spec = ProblemSpecJSON.new("Test problem description")
    assert spec.description == "Test problem description"
    assert len(spec.run_id) == 8
    assert spec.mode == "solve"


def test_problem_spec_methods():
    spec = ProblemSpecJSON(
        description="test",
        samples=(Sample(id="01", input="a", expected="b"),),
        constraints=Constraints(bounds=(ConstraintBound(variable="n", min=1, max=10),)),
        template="class Solution {};",
        function_signature=FunctionSignature(name="solve"),
    )
    assert spec.has_samples()
    assert spec.has_constraints()
    assert spec.has_template()
    assert spec.has_function_signature()


def test_problem_spec_no_samples():
    spec = ProblemSpecJSON(description="test")
    assert not spec.has_samples()
    assert not spec.has_constraints()
    assert not spec.has_template()
    assert not spec.has_function_signature()
