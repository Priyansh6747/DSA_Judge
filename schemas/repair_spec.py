"""RepairSpec — compile/execution result schemas."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class ErrorNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["syntax", "type", "undeclared", "template", "linker", "other"] = "other"
    file: str = ""
    line: int = 0
    column: int = 0
    message: str = ""


class CompileResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = False
    binary_path: str = ""
    attempts: int = 0
    errors: tuple[ErrorNode, ...] = ()
    warnings: tuple[str, ...] = ()


class CaseVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = ""
    passed: bool = False
    actual: str = ""
    time_ms: float = 0.0
    memory_kb: int = 0
    error: str = ""


class FailureClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["wrong_answer", "tle", "rte", "sigsegv", "sigfpe", "other"] = "other"
    case_id: str = ""
    diff: str = ""
    signal: str = ""
    exit_code: int = 0


class ExecResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = False
    attempts: int = 0
    case_results: tuple[CaseVerdict, ...] = ()
    failures: tuple[FailureClassification, ...] = ()
    passed: int = 0
    failed: int = 0


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["open", "intake", "blocked"] = "open"
    missing_required: tuple[str, ...] = ()
    missing_preferred: tuple[str, ...] = ()
    question_md: str = ""
    argv_options: Optional[tuple[str, ...]] = None
