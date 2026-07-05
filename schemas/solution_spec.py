"""SolutionArtifact — Stage 4 output schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SolutionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    solution_cpp: str
    algorithm: str = ""
    complexity_time: str = ""
    complexity_memory: str = ""
    edge_cases_addressed: tuple[str, ...] = ()
    self_review_notes: tuple[str, ...] = ()
