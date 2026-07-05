"""DSA Judge pipeline — robust, LLM-driven, self-healing."""

from pipeline.parser import parse_problem, ParseError
from pipeline.intake import classify, apply_user_response
from pipeline.driver_gen import generate_driver, DriverGenError
from pipeline.solution_gen import generate_solution, SolutionGenError
from pipeline.test_gen import synthesize, TestGenError
from pipeline.compiler import compile_with_repairs, classify_compiler_errors
from pipeline.executor import execute_with_repairs
from pipeline.reporter import build_report
from pipeline.engine import run_pipeline
from pipeline.validator import detect_platform
from pipeline.llm import complete, complete_raw, LLMError, LLMJSONError

__all__ = [
    "parse_problem", "ParseError",
    "classify", "apply_user_response",
    "generate_driver", "DriverGenError",
    "generate_solution", "SolutionGenError",
    "synthesize", "TestGenError",
    "compile_with_repairs", "classify_compiler_errors",
    "execute_with_repairs",
    "build_report",
    "run_pipeline",
    "detect_platform",
    "complete", "complete_raw", "LLMError", "LLMJSONError",
]
