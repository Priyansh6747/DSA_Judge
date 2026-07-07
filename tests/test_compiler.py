"""Test compiler error classification and compile function."""

import pytest
from pipeline.compiler import classify_compiler_errors, _classify_error_kind, has_malicious_calls


def test_classify_syntax_error():
    stderr = "solution.cpp:10:5: error: expected ';' before '}' token"
    errors = classify_compiler_errors(stderr)
    assert len(errors) == 1
    assert errors[0].kind == "syntax"
    assert errors[0].line == 10


def test_classify_type_error():
    stderr = "solution.cpp:5:12: error: cannot convert 'int' to 'std::string'"
    errors = classify_compiler_errors(stderr)
    assert len(errors) == 1
    assert errors[0].kind == "type"


def test_classify_undeclared_error():
    stderr = "solution.cpp:8:5: error: 'foo' was not declared in this scope"
    errors = classify_compiler_errors(stderr)
    assert len(errors) == 1
    assert errors[0].kind == "undeclared"


def test_classify_multiple_errors():
    stderr = (
        "solution.cpp:10:5: error: expected ';' before '}' token\n"
        "solution.cpp:15:1: error: 'bar' was not declared in this scope\n"
    )
    errors = classify_compiler_errors(stderr)
    assert len(errors) == 2
    assert errors[0].kind == "syntax"
    assert errors[1].kind == "undeclared"


def test_classify_generic_error():
    stderr = "compilation failed with some unknown error"
    errors = classify_compiler_errors(stderr)
    assert len(errors) == 1
    assert errors[0].kind == "other"


def test_classify_warning_skipped():
    stderr = "solution.cpp:5:10: warning: unused variable 'x'"
    errors = classify_compiler_errors(stderr)
    assert len(errors) == 0


def test_error_kind_syntax():
    assert _classify_error_kind("expected ';' before '}'") == "syntax"
    assert _classify_error_kind("unterminated string literal") == "syntax"


def test_error_kind_type():
    assert _classify_error_kind("cannot convert 'int' to 'string'") == "type"
    assert _classify_error_kind("invalid conversion from 'int' to 'char'") == "type"


def test_error_kind_undeclared():
    assert _classify_error_kind("'foo' was not declared in this scope") == "undeclared"
    assert _classify_error_kind("'bar' is not a member of 'std'") == "undeclared"


def test_error_kind_template():
    assert _classify_error_kind("template argument deduction failed") == "template"


def test_error_kind_linker():
    assert _classify_error_kind("undefined reference to 'main'") == "linker"
    assert _classify_error_kind("multiple definition of 'foo'") == "linker"


def test_malicious_system():
    assert has_malicious_calls('system("rm -rf /")') is True


def test_malicious_fopen():
    assert has_malicious_calls('fopen("/etc/passwd", "r")') is True


def test_malicious_clean():
    assert has_malicious_calls('int solve(vector<int>& nums) { return 0; }') is False


def test_malicious_include_curl():
    assert has_malicious_calls('#include <curl/curl.h>') is True
