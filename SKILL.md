---
name: dsa-judge
description: "Solve, verify, repair, or explain DSA problems with compile-validate-report pipeline."
---

# DSA Judge

Four modes. No guessing. No silent assumptions. Missing information → ask the user.

## Modes

| Mode | Required inputs | Pipeline does |
|------|----------------|---------------|
| **Solve** | problem, template, samples | Parse → Intake → Plan → Generate → Compile → Execute → Validate → Report |
| **Verify** | problem, template, solution, samples | Parse → Intake → Compile → Execute → Validate → Report |
| **Repair** | problem, template, failing code, samples | Parse → Intake → Compile → Diagnose → Fix → Recompile → Validate → Report |
| **Explain** | problem, accepted code, samples | Parse → Intake → Plan → Explain approach and complexity |

## How to detect mode

- Problem only → **Solve**
- Problem + code snippet → **Verify**
- Problem + code + "doesn't work" / "fails" / error output → **Repair**
- Problem + code + "explain" / "how does this work" → **Explain**

## Pipeline

```
Problem
  │
  ▼
Parser
  │
  ▼
Interactive Intake  ←── Asks for missing fields, never guesses
  │
  ▼
Planner
  │
  ▼
Generator / Reviewer
  │
  ▼
Reviewer (pre-compile)
  │
  ▼
Compiler
  │
  ▼
Executor
  │
  ▼
Validator
  │
  ▼
Reporter
```

## Stage 1: Parse

Extract from the problem text:
- Title
- Sample test cases (Input/Output pairs)
- Constraints (ONLY if explicitly stated — never inferred)
- Input/output format
- Platform hints (with confidence score)
- Function signature (if visible in text)

Write to `ProblemSpec`.

Platform detection returns a confidence score:
```
Platform: LeetCode (68% confidence, source: matched "class solution", "example 1:")
```

## Stage 2: Interactive Intake

**This is a HARD GATE. The pipeline does not proceed until all fields are resolved.**

Show the status table:
```
────────────────────────────────────
  PROBLEM SPEC STATUS
────────────────────────────────────

  Required:
    ✅ Description
    ✅ Samples (2 provided)

  Preferred:
    ⚠️ Constraints
    ❌ Code Template
    ❌ Function Signature

  Optional:
    ⚠️ Existing Solution (missing)

────────────────────────────────────
  Gate: ✗ BLOCKED
  Info: ⚠ INCOMPLETE
────────────────────────────────────
```

If **BLOCKED** (required fields missing):
```
❌ BLOCKED — Missing required fields.

Please provide:
1. The problem statement (if missing)
2. At least one sample test case (if missing)
```

If **INCOMPLETE** (preferred fields missing):
```
I need a few things before I can generate code.

Reply with ONE of:

1 — LeetCode (class Solution, function signature provided)
2 — Codeforces (main function)
3 — AtCoder (main function)
4 — CSES (main function)
5 — Paste custom template with function signature

Also provide:
- Constraints (if you have them)
- Function name and signature
```

**NEVER:**
- Infer the template
- Guess the function name
- Assume the entry point
- Invent constraints

## Stage 3: Plan

Before writing code:
1. What algorithm? (specific approach name)
2. Why optimal? (justify against alternatives)
3. Time complexity: O(...) — consistent, no contradictions
4. Memory complexity: O(...)
5. Edge cases: (list them)

**Planner consistency rule:** If you say "single-pass", the code must be single-pass. If you say "two-pass", the code must be two-pass. Never say one thing and do another.

If constraints are missing, note:
```
Planning performed without explicit constraints.
Complexity estimate is approximate.
Confidence: MEDIUM (constraints unknown)
```

## Stage 4: Generate

Write C++20 solution using:
- The exact function signature from the template
- The exact class name from the template
- The exact entry point from the template

**Function name must match the problem/template.** If the problem says `maximumDigitRange`, the function must be called `maximumDigitRange`, not `sumOfDigits` or anything else.

Rules:
- Use `#include <bits/stdc++.h>` for competitive programming
- Use `long long` when sum/product could overflow `int`
- No unnecessary comments
- No debug output
- Handle all edge cases identified in Stage 3

## Stage 5: Reviewer (Pre-Compile)

Before compiling, check:
- Integer overflow risk?
- Off-by-one errors?
- Function signature matches template?
- Edge case handling?
- Complexity matches plan (consistently)?

If ANY issue found → fix before compiling.

## Stage 6: Compile

```bash
g++ -std=c++20 -O2 -Wall -Wextra -o solution solution.cpp
```

If fails → analyze errors → fix → retry (max 5 attempts).

## Stage 7: Execute

Run against EVERY sample:

```bash
echo "<input>" | ./solution
```

## Stage 8: Validate

Compare expected vs actual for each case. Show diffs on failure.

## Stage 9: Report

```
# DSA Judge Report

## Mode: Solve

## Requirement Check
  Gate: OPEN
  ✓ Description
  ✓ Samples (2)
  ✓ Constraints (explicit)
  ✓ Template (LeetCode class Solution)
  ✓ Function Signature (maximumDigitRange)

## Compilation
  ✅ 1 attempt, 0 warnings

## Algorithm
  <name and reasoning — consistent with code>

## Complexity
  Time: O(...)
  Memory: O(...)

## Sample Results
  | # | Input | Expected | Actual | Status | Time |
  |---|-------|----------|--------|--------|------|

## Platform Confidence
  LeetCode (68% confidence)
  Source: matched "class solution", "example 1:"

## Confidence: HIGH / MEDIUM / LOW
## Weaknesses
  - <concerns>

## Final Verdict
  ✅ / ❌
```

## Execute programmatically

```python
from pipeline.engine import parse_problem, run_pipeline
from pipeline.state import ProblemSpec, Mode

# Parse — extracts what it can, flags what's missing
spec = parse_problem(problem_text)
print(spec.status_table())

# Check gate
if spec.gate_status == "blocked":
    # Show missing required fields, wait for user
    for q in spec.questions_for_user:
        print(q)
elif spec.gate_status == "intake":
    # Show missing preferred fields, wait for user
    print(intake_summary(spec))
    # After user responds, update spec and re-validate
    spec = spec.updated(template="...", function_signature=...)
    spec = validate_requirements(spec)

# Agent does LLM work (plan, generate, verify)
spec = spec.updated(
    algorithm="...",
    solution_cpp="...",
    verification_passed=True,
)

# Run deterministic stages
spec = run_pipeline(spec)
print(spec.report_md)
```

## Confidence Scoring

Every inference gets a confidence score:

| Source | Confidence |
|--------|-----------|
| Explicit in text | 1.0 |
| Heuristic match | 0.6–0.8 |
| Platform guess | 0.3–0.6 |
| Pure guess | 0.0–0.3 |

Report shows:
```
Platform: LeetCode (68% confidence)
  Source: matched "class solution", "example 1:"

Constraints: not provided
  Planning will proceed without explicit constraints.
  Confidence reduced.
```

## Limitations (V1)

- Plain text problems only
- C++20 only
- Sample test cases only
- No stress testing
- No URL fetching
