"""Test executor failure classification."""

import pytest
from pipeline.executor import _validate_output, _classify_failure


def test_validate_output_exact():
    assert _validate_output("42", "42") is True


def test_validate_output_whitespace():
    assert _validate_output("  42  \n", "42\n") is True


def test_validate_output_wrong():
    assert _validate_output("42", "43") is False


def test_validate_output_multiline():
    assert _validate_output("1\n2\n3", "1\n2\n3") is True


def test_validate_output_multiline_wrong():
    assert _validate_output("1\n2\n3", "1\n3\n3") is False


def test_classify_tle():
    result = {"timed_out": True, "time_ms": 5000, "exit_code": -1, "stdout": "", "stderr": "Timed out"}
    fc = _classify_failure(result, "42", "")
    assert fc.kind == "tle"


def test_classify_sigsegv():
    result = {"timed_out": False, "time_ms": 10, "exit_code": 139, "stdout": "", "stderr": ""}
    fc = _classify_failure(result, "42", "")
    assert fc.kind == "sigsegv"


def test_classify_rte():
    result = {"timed_out": False, "time_ms": 10, "exit_code": 1, "stdout": "", "stderr": "runtime error"}
    fc = _classify_failure(result, "42", "")
    assert fc.kind == "rte"


def test_classify_wrong_answer():
    result = {"timed_out": False, "time_ms": 10, "exit_code": 0, "stdout": "43", "stderr": ""}
    fc = _classify_failure(result, "42", "43")
    assert fc.kind == "wrong_answer"
    assert "expected: 42" in fc.diff
    assert "actual:   43" in fc.diff
