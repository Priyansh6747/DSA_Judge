"""Stage 1: Parse — natural language → structured JSON.

LLM-driven parser that emits a ProblemSpecJSON. The LLM is the extractor;
this module validates the output and retries once on schema failure.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from schemas.problem_spec import ProblemSpecJSON, Mode
from pipeline import llm as llm_mod


class ParseError(Exception):
    pass


def parse_problem(text: str, *, mode: Mode = "solve") -> ProblemSpecJSON:
    """Parse problem text into a validated ProblemSpecJSON.

    Calls the LLM with the parse prompt, validates against pydantic,
    retries once with error context on failure. Raises ParseError if
    both attempts fail.
    """
    # First attempt
    try:
        raw = llm_mod.complete("parse", {"input": text}, expect_json=True)
    except llm_mod.LLMJSONError as e:
        # Retry once with the parse errors appended
        raw = _retry_with_errors(text, e.parse_errors, e.raw)
        if raw is None:
            raise ParseError(
                "I couldn't parse your problem into structured JSON after 2 attempts. "
                "Please rephrase the problem statement."
            )

    # Validate with pydantic
    try:
        spec = ProblemSpecJSON(**raw)
    except ValidationError as e:
        # Retry once with the validation errors
        raw = _retry_with_errors(text, [str(e)[:500]], json.dumps(raw) if isinstance(raw, dict) else str(raw))
        if raw is None:
            raise ParseError(
                "Parsed JSON did not match expected schema after 2 attempts. "
                "Please rephrase the problem statement."
            )
        try:
            spec = ProblemSpecJSON(**raw)
        except ValidationError:
            raise ParseError(
                "Parsed JSON still does not match schema after 2 attempts. "
                "Please rephrase the problem statement."
            )

    # Ensure mode is set
    if spec.mode != mode:
        spec = spec.model_copy(update={"mode": mode})

    return spec


def _retry_with_errors(text: str, errors: list[str], raw_output: str) -> dict[str, Any] | None:
    """Retry parsing with error context appended. Returns dict or None."""
    retry_prompt = (
        f"The following problem text needs to be parsed into JSON.\n\n"
        f"## Problem Text\n{text}\n\n"
        f"## Previous Attempt Failed\n"
        f"Your previous output:\n{raw_output[:2000]}\n\n"
        f"Errors:\n" + "\n".join(f"- {e}" for e in errors) + "\n\n"
        f"Fix these errors and output ONLY the corrected JSON object."
    )
    try:
        raw = llm_mod.complete_raw(retry_prompt)
        return llm_mod._extract_json(raw)
    except (llm_mod.LLMJSONError, Exception):
        return None
