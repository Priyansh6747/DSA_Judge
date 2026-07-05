"""Test platform detection (validator.py)."""

import pytest
from pipeline.validator import detect_platform


def test_leetcode_explicit():
    p, c, s = detect_platform("LeetCode problem class Solution")
    assert p == "leetcode"
    assert c > 0.5


def test_codeforces_explicit():
    p, c, s = detect_platform("Codeforces Round #123")
    assert p == "codeforces"
    assert c > 0.2


def test_unknown():
    p, c, s = detect_platform("Random problem text with no signals")
    assert p == "unknown"
    assert c == 0.0


def test_leetcode_heuristic():
    p, c, s = detect_platform("Example 1: nums = [1,2,3]")
    assert p == "leetcode"
    assert c > 0.5


def test_atcoder():
    p, c, s = detect_platform("AtCoder Beginner Contest 100")
    assert p == "atcoder"


def test_cses():
    p, c, s = detect_platform("CSES Problem Set")
    assert p == "cses"


def test_geeksforgeeks():
    p, c, s = detect_platform("GeeksforGeeks practice problem")
    assert p == "geeksforgeeks"
