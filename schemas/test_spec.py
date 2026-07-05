"""TestSpec — Stage 5 output schema."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class EdgeTestCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    input: str
    expected: Optional[str] = None
    category: str = ""
    why: str = ""
    compute_via: Literal["provided", "brute_force"] = "provided"


# Alias for backward compatibility
TestCase = EdgeTestCase


class TestPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: tuple[EdgeTestCase, ...] = ()
    brute_force_cpp: Optional[str] = None
