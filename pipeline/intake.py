"""Stage 2: Intake Gate — deterministic completeness check with quick-cut.

Checks ProblemSpecJSON completeness. If required fields are missing, blocks.
If preferred fields are missing, asks the user structured questions.
"""

from __future__ import annotations

from typing import Any

from schemas.problem_spec import ProblemSpecJSON
from schemas.repair_spec import GateResult


def classify(spec: ProblemSpecJSON) -> GateResult:
    """Check completeness. Returns a GateResult with status + questions."""
    missing_required: list[str] = []
    missing_preferred: list[str] = []
    questions: list[str] = []

    # ── REQUIRED — pipeline BLOCKS if these are missing ──

    if not spec.description.strip():
        missing_required.append("description")
        questions.append("Please provide the problem statement.")

    if not spec.has_samples():
        missing_required.append("samples")
        questions.append(
            "No sample test cases provided.\n"
            "I cannot validate the solution without at least one sample.\n"
            "Please provide at least one sample input and expected output."
        )

    if spec.mode in ("verify", "repair", "explain") and not spec.user_solution:
        missing_required.append("user_solution")
        mode_instructions = {
            "verify": "Verify mode requires existing code to test.",
            "repair": "Repair mode requires the failing code.",
            "explain": "Explain mode requires accepted code.",
        }
        questions.append(f"{mode_instructions[spec.mode]} Please provide the code.")

    # ── PREFERRED — missing triggers intake questions ──

    if not spec.has_template() and spec.mode in ("solve", "repair"):
        missing_preferred.append("template")
        questions.append(
            "I cannot identify the required code template.\n"
            "I need to know the entry point before generating code.\n\n"
            "Reply with ONE of:\n"
            "1 — LeetCode (class Solution)\n"
            "2 — Codeforces (main)\n"
            "3 — AtCoder (main)\n"
            "4 — CSES (main)\n"
            "5 — Paste custom template"
        )

    if not spec.has_function_signature() and spec.mode in ("solve", "repair"):
        missing_preferred.append("function_signature")
        questions.append(
            "I need the function name and signature.\n"
            "What should the solution function be called?\n\n"
            "Examples:\n"
            "  int maximumDigitRange(vector<int>& nums)\n"
            "  int main()"
        )

    if not spec.has_constraints():
        missing_preferred.append("constraints")
        questions.append(
            "Constraints were not provided.\n"
            "I will plan and generate code without explicit constraints.\n"
            "Confidence will be reduced.\n\n"
            "Should I:\n"
            "1. Continue without constraints\n"
            "2. Wait for you to provide them"
        )

    # ── Determine gate status ──

    if missing_required:
        status: str = "blocked"
    elif missing_preferred:
        status = "intake"
    else:
        status = "open"

    # ── Build question markdown ──

    if status == "blocked":
        question_md = (
            "❌ BLOCKED — Missing required fields.\n\n"
            + "\n\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        )
    elif status == "intake":
        question_md = (
            "I need a few things before I can generate code.\n\n"
            + "\n\n".join(questions)
        )
    else:
        question_md = ""

    argv_options = None
    if not spec.has_template() and spec.mode in ("solve", "repair"):
        argv_options = (
            "LeetCode (class Solution)",
            "Codeforces (main)",
            "AtCoder (main)",
            "CSES (main)",
            "Custom template",
        )

    return GateResult(
        status=status,
        missing_required=tuple(missing_required),
        missing_preferred=tuple(missing_preferred),
        question_md=question_md,
        argv_options=argv_options,
    )


def apply_user_response(spec: ProblemSpecJSON, response: dict[str, Any]) -> ProblemSpecJSON:
    """Apply user answers to the spec and return an updated copy."""
    updates: dict[str, Any] = {}

    if "template_choice" in response:
        choice = response["template_choice"]
        templates = {
            "1": ("class Solution { public: };", ("Solution", "", "", "")),
            "2": ("int main() { return 0; }", ("", "int", "main", "")),
            "3": ("int main() { return 0; }", ("", "int", "main", "")),
            "4": ("int main() { return 0; }", ("", "int", "main", "")),
        }
        if choice in templates:
            tmpl, (cls, ret, name, args) = templates[choice]
            updates["template"] = tmpl
            updates["function_signature"] = spec.function_signature.model_copy(
                update={"class_name": cls, "return_type": ret, "name": name, "arguments": args}
            )

    if "template_raw" in response:
        updates["template"] = response["template_raw"]

    if "function_signature" in response:
        sig = response["function_signature"]
        if isinstance(sig, dict):
            updates["function_signature"] = spec.function_signature.model_copy(update=sig)

    if "constraints" in response:
        updates["constraints"] = response["constraints"]

    if "user_solution" in response:
        updates["user_solution"] = response["user_solution"]

    return spec.model_copy(update=updates)
