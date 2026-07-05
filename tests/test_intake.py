"""Test intake gate logic."""

import pytest
from schemas.problem_spec import ProblemSpecJSON, Sample, Constraints, ConstraintBound, FunctionSignature
from pipeline.intake import classify, apply_user_response


def test_gate_blocked_no_description():
    spec = ProblemSpecJSON(description="", samples=(Sample(id="01", input="a", expected="b"),))
    gate = classify(spec)
    assert gate.status == "blocked"
    assert "description" in gate.missing_required


def test_gate_blocked_no_samples():
    spec = ProblemSpecJSON(description="A problem", samples=())
    gate = classify(spec)
    assert gate.status == "blocked"
    assert "samples" in gate.missing_required


def test_gate_intake_no_template():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
        constraints=Constraints(bounds=(ConstraintBound(variable="n", min=1, max=10),)),
    )
    gate = classify(spec)
    assert gate.status == "intake"
    assert "template" in gate.missing_preferred


def test_gate_intake_no_constraints():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
        template="class Solution {};",
        function_signature=FunctionSignature(name="solve", return_type="int", arguments="()", class_name="Solution"),
    )
    gate = classify(spec)
    assert gate.status == "intake"
    assert "constraints" in gate.missing_preferred


def test_gate_open():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
        template="class Solution {};",
        function_signature=FunctionSignature(name="solve", return_type="int", arguments="()", class_name="Solution"),
        constraints=Constraints(bounds=(ConstraintBound(variable="n", min=1, max=10),)),
    )
    gate = classify(spec)
    assert gate.status == "open"
    assert gate.missing_required == ()
    assert gate.missing_preferred == ()


def test_gate_verify_no_code():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
        mode="verify",
    )
    gate = classify(spec)
    assert gate.status == "blocked"
    assert "user_solution" in gate.missing_required


def test_gate_repair_no_code():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
        mode="repair",
    )
    gate = classify(spec)
    assert gate.status == "blocked"
    assert "user_solution" in gate.missing_required


def test_apply_user_response_template_choice():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
    )
    updated = apply_user_response(spec, {"template_choice": "1"})
    assert updated.template == "class Solution { public: };"
    assert updated.function_signature.class_name == "Solution"


def test_apply_user_response_constraints():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
    )
    updated = apply_user_response(spec, {
        "constraints": Constraints(bounds=(ConstraintBound(variable="n", min=1, max=100),))
    })
    assert updated.has_constraints()


def test_gate_question_md_blocked():
    spec = ProblemSpecJSON(description="", samples=())
    gate = classify(spec)
    assert "BLOCKED" in gate.question_md


def test_gate_question_md_intake():
    spec = ProblemSpecJSON(
        description="A problem",
        samples=(Sample(id="01", input="a", expected="b"),),
    )
    gate = classify(spec)
    assert gate.question_md != ""
    assert "BLOCKED" not in gate.question_md
