"""ReportJSON — final report schema."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReportJSON(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = ""
    gate_status: str = ""
    compiled: bool = False
    compile_attempts: int = 0
    algorithm: str = ""
    complexity_time: str = ""
    complexity_memory: str = ""
    edge_cases: tuple[str, ...] = ()
    passed: int = 0
    failed: int = 0
    case_results: tuple[dict, ...] = ()
    platform: str = ""
    platform_confidence: float = 0.0
    confidence: str = "unknown"
    known_weaknesses: tuple[str, ...] = ()
    report_md: str = ""
    driver_generated: bool = False
    driver_is_self_contained: bool = False
    edge_test_categories: tuple[str, ...] = ()
    edge_tests_dropped: int = 0
    oracle_used: bool = False
    compile_repair_attempts: int = 0
    exec_repair_attempts: int = 0
    regressions_caught: int = 0
