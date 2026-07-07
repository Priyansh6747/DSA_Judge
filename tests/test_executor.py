"""Test executor — run_case and execute functions."""

import json
import os
import tempfile
import pytest
from pipeline.executor import run_case, execute, _validate_output


@pytest.fixture
def simple_binary():
    """Create a simple echo binary for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "echo.cpp")
        binary = os.path.join(tmpdir, "echo")
        with open(src, "w") as f:
            f.write('#include <iostream>\nint main() { std::string s; std::getline(std::cin, s); std::cout << s << "\\n"; return 0; }\n')
        os.system(f"g++ -std=c++20 -o {binary} {src}")
        yield binary


def test_run_case_basic(simple_binary):
    result = run_case(simple_binary, "hello world")
    assert result["stdout"].strip() == "hello world"
    assert result["exit_code"] == 0
    assert not result["timed_out"]


def test_run_case_empty_input(simple_binary):
    result = run_case(simple_binary, "")
    assert result["exit_code"] == 0


def test_run_case_timeout():
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "infinite.cpp")
        binary = os.path.join(tmpdir, "infinite")
        with open(src, "w") as f:
            f.write('#include <iostream>\nint main() { while(true) {} return 0; }\n')
        os.system(f"g++ -std=c++20 -o {binary} {src}")
        result = run_case(binary, "", timeout_s=0.5)
        assert result["timed_out"]


def test_validate_output_exact():
    assert _validate_output("42", "42") is True


def test_validate_output_whitespace():
    assert _validate_output("42\n", "42") is True
    assert _validate_output(" 42 ", "42") is True


def test_validate_output_mismatch():
    assert _validate_output("42", "43") is False


def test_execute_all_pass(simple_binary):
    test_cases = [
        {"id": "t1", "input": "hello", "expected": "hello"},
        {"id": "t2", "input": "world", "expected": "world"},
    ]
    result = execute(simple_binary, test_cases)
    assert result.success is True
    assert result.passed == 2
    assert result.failed == 0


def test_execute_one_fail(simple_binary):
    test_cases = [
        {"id": "t1", "input": "hello", "expected": "hello"},
        {"id": "t2", "input": "world", "expected": "wrong"},
    ]
    result = execute(simple_binary, test_cases)
    assert result.success is False
    assert result.passed == 1
    assert result.failed == 1
    assert len(result.failures) == 1
    assert result.failures[0].kind == "wrong_answer"


def test_execute_empty_tests(simple_binary):
    result = execute(simple_binary, [])
    assert result.success is True
    assert result.passed == 0
