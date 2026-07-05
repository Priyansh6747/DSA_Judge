#!/usr/bin/env python3
"""End-to-end test for DSA Judge pipeline — v3 architecture.

Tests: Parser, Interactive Intake, Platform Confidence, Function Extraction,
       Gate Logic, Full Pipeline, Mode Requirements.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.engine import parse_problem, run_pipeline
from pipeline.state import ProblemSpec, Sample, Mode, Platform, Confidence, FunctionSignature, SolutionStatus
from pipeline.validator import (
    validate_requirements, can_proceed, is_blocked, needs_intake,
    detect_platform, extract_function_signature, intake_summary,
)


# ══════════════════════════════════════════════════════════════════
# Test Problems
# ══════════════════════════════════════════════════════════════════

PROBLEM_LC = """\
Sum of Integers with Maximum Digit Range

You are given an integer array nums.

The digit range of an integer is defined as the difference between its largest digit and smallest digit.

For example, the digit range of 5724 is 7 - 2 = 5.

Return the sum of all integers in nums whose digit range is equal to the maximum digit range among all integers in the array.

Example 1:
Input: nums = [5724,111,350]
Output: 6074

Example 2:
Input: nums = [90,900]
Output: 990
"""

PROBLEM_NO_SAMPLES = """\
Two Sum

Given an array of integers nums and an integer target.
"""

PROBLEM_WITH_CONSTRAINTS = """\
Two Sum

Given an array of integers nums and an integer target.

Constraints:
2 <= nums.length <= 10^4
-10^9 <= nums[i] <= 10^9
-10^9 <= target <= 10^9

Sample Input 1:
4
2 7 11 15
9

Sample Output 1:
0 1
"""

PROBLEM_CODEFORCES = """\
A. Watermelon

Input: one integer w (1 ≤ w ≤ 100)
Output: "YES" if w can be divided into two even parts, "NO" otherwise

Sample Input:
8

Sample Output:
YES
"""

SOLUTION = """\
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    int n;
    cin >> n;
    vector<int> nums(n);
    for (int i = 0; i < n; i++) cin >> nums[i];

    auto digitRange = [](int x) -> int {
        int lo = 9, hi = 0;
        while (x > 0) {
            int d = x % 10;
            lo = min(lo, d);
            hi = max(hi, d);
            x /= 10;
        }
        return hi - lo;
    };

    int maxRange = 0;
    for (int x : nums)
        maxRange = max(maxRange, digitRange(x));

    long long sum = 0;
    for (int x : nums)
        if (digitRange(x) == maxRange)
            sum += x;

    cout << sum << "\\n";
    return 0;
}
"""


# ══════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════

def test_parse_leetcode():
    print("=" * 60)
    print("TEST: Parse LeetCode Problem")
    print("=" * 60)

    spec = parse_problem(PROBLEM_LC)
    print(spec.status_table())
    print()

    assert spec.title, "Missing title"
    assert spec.has_samples(), "Missing samples"
    assert len(spec.samples) == 2, f"Expected 2 samples, got {len(spec.samples)}"

    # Platform detection
    assert spec.platform.value == Platform.LEETCODE, f"Expected LeetCode, got {spec.platform.value}"
    assert spec.platform_confidence > 0.5, f"Confidence too low: {spec.platform_confidence}"
    print(f"  Platform: {spec.platform}")
    print(f"  Confidence: {spec.platform_confidence}")

    # Template should be missing (not inferred)
    assert not spec.has_template(), "Template should NOT be inferred"
    assert "template" in spec.missing_preferred, "Template should be flagged as missing"
    print(f"  Template: missing (correct — not inferred)")

    # Gate should be intake (preferred missing) not blocked
    assert needs_intake(spec), f"Should need intake, got gate_status={spec.gate_status}"
    print(f"  Gate: {spec.gate_status} (correct)")

    print("  ✅ Parse OK\n")
    return spec


def test_parse_with_constraints():
    print("=" * 60)
    print("TEST: Parse with Explicit Constraints")
    print("=" * 60)

    spec = parse_problem(PROBLEM_WITH_CONSTRAINTS)
    assert spec.has_constraints(), "Should have extracted constraints"
    assert spec.constraint_confidence == 1.0, "Explicit constraints should have 1.0 confidence"
    print(f"  Constraints: {spec.constraints}")
    print(f"  Confidence: {spec.constraint_confidence}")
    print("  ✅ Constraints OK\n")


def test_parse_no_samples():
    print("=" * 60)
    print("TEST: Parse without Samples (BLOCKED)")
    print("=" * 60)

    spec = parse_problem(PROBLEM_NO_SAMPLES)
    assert is_blocked(spec), f"Should be blocked, got gate_status={spec.gate_status}"
    assert "samples" in spec.missing_required
    print(f"  Gate: {spec.gate_status}")
    print(f"  Missing required: {spec.missing_required}")
    print(f"  Question: {spec.questions_for_user[0][:60]}...")
    print("  ✅ Hard stop works\n")


def test_parse_codeforces():
    print("=" * 60)
    print("TEST: Parse Codeforces Problem")
    print("=" * 60)

    spec = parse_problem(PROBLEM_CODEFORCES)
    assert spec.platform.value == Platform.CODEFORCES, f"Expected Codeforces, got {spec.platform.value}"
    print(f"  Platform: {spec.platform}")
    print(f"  Samples: {len(spec.samples)}")
    print("  ✅ Codeforces detection OK\n")


def test_platform_confidence():
    print("=" * 60)
    print("TEST: Platform Detection with Confidence")
    print("=" * 60)

    # High confidence
    p, c, s = detect_platform("LeetCode problem class Solution")
    assert p == Platform.LEETCODE
    assert c > 0.5
    print(f"  LeetCode: {p} ({c:.0%})")

    # Low confidence
    p, c, s = detect_platform("Random problem text")
    assert p == Platform.UNKNOWN
    assert c == 0.0
    print(f"  Unknown: {p} ({c:.0%})")

    # Medium confidence
    p, c, s = detect_platform("Codeforces Round #123")
    assert p == Platform.CODEFORCES
    assert c > 0.2
    print(f"  Codeforces: {p} ({c:.0%})")

    print("  ✅ Platform confidence OK\n")


def test_function_extraction():
    print("=" * 60)
    print("TEST: Function Signature Extraction")
    print("=" * 60)

    # LeetCode style
    text = "class Solution { public: int maximumDigitRange(vector<int>& nums) {} }"
    name, ret, args, cls = extract_function_signature(text)
    assert name == "maximumDigitRange", f"Expected maximumDigitRange, got {name}"
    assert ret == "int"
    assert cls == "Solution"
    print(f"  LeetCode: {cls}::{name}({args}) -> {ret}")

    # Standalone function
    text2 = "int main() { return 0; }"
    name2, ret2, args2, cls2 = extract_function_signature(text2)
    assert name2 == "main"
    print(f"  Standalone: {ret2} {name2}({args2})")

    print("  ✅ Function extraction OK\n")


def test_gate_logic():
    print("=" * 60)
    print("TEST: Gate Logic")
    print("=" * 60)

    # Blocked: no samples
    spec1 = ProblemSpec.new("Problem text")
    spec1 = validate_requirements(spec1)
    assert is_blocked(spec1)
    print(f"  No samples: {spec1.gate_status} ✓")

    # Intake: has samples but no template
    spec2 = parse_problem(PROBLEM_LC)
    assert needs_intake(spec2)
    print(f"  No template: {spec2.gate_status} ✓")

    # Open: everything provided
    spec3 = parse_problem(PROBLEM_LC)
    spec3 = spec3.updated(
        template="class Solution { public: int func(vector<int>& nums) {} }",
        function_signature=FunctionSignature("func", "int", "vector<int>& nums", "Solution"),
        constraints={"n": "<= 10^4"},
    )
    spec3 = validate_requirements(spec3)
    assert can_proceed(spec3)
    print(f"  All provided: {spec3.gate_status} ✓")

    print("  ✅ Gate logic OK\n")


def test_mode_requirements():
    print("=" * 60)
    print("TEST: Mode-Specific Requirements")
    print("=" * 60)

    # Verify mode without code → blocked
    spec_v = ProblemSpec.new(PROBLEM_LC, mode=Mode.VERIFY)
    spec_v = spec_v.updated(description=PROBLEM_LC, samples=(Sample("01", "in", "out"),))
    spec_v = validate_requirements(spec_v)
    assert is_blocked(spec_v)
    assert "user_solution" in spec_v.missing_required
    print(f"  Verify (no code): {spec_v.gate_status} ✓")

    # Repair mode without code → blocked
    spec_r = ProblemSpec.new(PROBLEM_LC, mode=Mode.REPAIR)
    spec_r = spec_r.updated(description=PROBLEM_LC, samples=(Sample("01", "in", "out"),))
    spec_r = validate_requirements(spec_r)
    assert is_blocked(spec_r)
    print(f"  Repair (no code): {spec_r.gate_status} ✓")

    # Explain mode without code → blocked
    spec_e = ProblemSpec.new(PROBLEM_LC, mode=Mode.EXPLAIN)
    spec_e = spec_e.updated(description=PROBLEM_LC, samples=(Sample("01", "in", "out"),))
    spec_e = validate_requirements(spec_e)
    assert is_blocked(spec_e)
    print(f"  Explain (no code): {spec_e.gate_status} ✓")

    # Verify mode with code → intake (template missing)
    spec_v2 = spec_v.updated(user_solution="int main() { return 0; }")
    spec_v2 = validate_requirements(spec_v2)
    assert needs_intake(spec_v2)
    print(f"  Verify (with code): {spec_v2.gate_status} ✓")

    print("  ✅ Mode requirements OK\n")


def test_intake_summary():
    print("=" * 60)
    print("TEST: Intake Summary")
    print("=" * 60)

    spec = parse_problem(PROBLEM_LC)
    summary = intake_summary(spec)
    assert "REQUIRED INFORMATION" in summary
    assert "template" in summary.lower() or "Template" in summary
    print(summary[:200])
    print("  ✅ Intake summary OK\n")


def test_full_pipeline():
    print("=" * 60)
    print("TEST: Full Pipeline (with all fields provided)")
    print("=" * 60)

    spec = parse_problem(PROBLEM_LC)
    # Override samples with proper competitive programming format
    spec = spec.updated(
        samples=(
            Sample("01", "3\n5724 111 350", "6074"),
            Sample("02", "2\n90 900", "990"),
        ),
        template="int main() { ... }",
        function_signature=FunctionSignature("main", "int", "", ""),
        constraints={"n": "<= 10^4", "nums[i]": "<= 10^4"},
        algorithm="Linear scan with digit extraction",
        planning_reasoning="Three O(n) passes: compute ranges, find max, sum matches.",
        complexity_time="O(n * d) ≈ O(n)",
        complexity_memory="O(1)",
        edge_cases=("single element", "all same range", "numbers with 0"),
        solution_cpp=SOLUTION,
        verification_passed=True,
    )
    spec = validate_requirements(spec)
    assert can_proceed(spec), f"Should be open, got {spec.gate_status}"

    spec = run_pipeline(spec, workspace="/tmp/dsa-judge-test/runs")

    print(f"  Compiled: {spec.compiled} ({spec.compile_attempts} attempt(s))")
    print(f"  Cases: {spec.passed_samples}/{spec.passed_samples + spec.failed_samples} passed")
    for cr in spec.case_results:
        print(f"    {cr['case_id']}: {'✅' if cr['passed'] else '❌'} ({cr['time_ms']:.1f}ms)")
    assert spec.compiled, "Should compile"
    assert spec.failed_samples == 0, f"Should pass all samples, {spec.failed_samples} failed"
    print("  ✅ Full pipeline OK\n")


def test_confidence_scoring():
    print("=" * 60)
    print("TEST: Confidence Scoring")
    print("=" * 60)

    # Explicit
    c1 = Confidence("value", 1.0, "explicit")
    assert "value" in str(c1)
    print(f"  Explicit: {c1}")

    # Inferred
    c2 = Confidence("value", 0.7, "inferred")
    assert "70%" in str(c2)
    print(f"  Inferred: {c2}")

    # Low confidence
    c3 = Confidence("value", 0.3, "guessed")
    assert "30%" in str(c3)
    print(f"  Guessed: {c3}")

    print("  ✅ Confidence scoring OK\n")


def main():
    print("🧪 DSA Judge — Full Test Suite (v3)\n")

    test_parse_leetcode()
    test_parse_with_constraints()
    test_parse_no_samples()
    test_parse_codeforces()
    test_platform_confidence()
    test_function_extraction()
    test_gate_logic()
    test_mode_requirements()
    test_intake_summary()
    test_full_pipeline()
    test_confidence_scoring()

    print("=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
