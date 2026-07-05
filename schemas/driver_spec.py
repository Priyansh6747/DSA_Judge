"""DriverArtifact — Stage 3 output schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DriverArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    driver_cpp: str = ""
    linker_note: str = ""
    expected_stdio_format: str = ""
    is_self_contained: bool = False
