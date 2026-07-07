"""DSA Judge pipeline — deterministic tooling for agent-orchestrated solving.

The agent handles all LLM reasoning (parsing, code generation, repair).
This package provides only deterministic operations: compile, execute, diff, report.
"""

from pipeline.compiler import compile, classify_compiler_errors, has_malicious_calls
from pipeline.executor import execute, run_case
from pipeline.reporter import build_report
from pipeline.intake import classify, apply_user_response
from pipeline.validator import detect_platform

__all__ = [
    "compile",
    "classify_compiler_errors",
    "has_malicious_calls",
    "execute",
    "run_case",
    "build_report",
    "classify",
    "apply_user_response",
    "detect_platform",
]
