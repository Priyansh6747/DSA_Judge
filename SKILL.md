---
name: dsa-judge
description: "Deterministic C++ compile/execute tooling for agent-orchestrated DSA solving."
---

# DSA Judge

Deterministic tooling for DSA problem solving. The agent (LLM) handles all
reasoning — parsing, code generation, repair. This skill provides only
deterministic operations: compile, execute, diff, report.

## Architecture

```
Agent (Finrel)                    Deterministic Pipeline
─────────────                     ─────────────────────
Parse problem text         →      ProblemSpecJSON (schema)
Generate solution.cpp      →      source code (text)
Generate driver.cpp        →      test harness (text)
Generate test cases        →      test cases (JSON)
                                   │
                                   ▼
                              compile(source, driver)
                                   │
                                   ▼
                              execute(binary, tests)
                                   │
                                   ▼
                              report(results)
```

**The agent does the thinking. The pipeline does the verifying.**

## CLI Usage

### Compile

```bash
python3 runner.py compile --source solution.cpp --driver driver.cpp --out-dir workspace/run1
python3 runner.py compile --source solution.cpp --func-name solve --out-dir workspace/run1
```

Output: JSON with `success`, `binary_path`, `errors`, `warnings`

### Execute

```bash
# From file
python3 runner.py execute --binary workspace/run1/solution --tests tests.json

# From stdin
echo '[{"id":"t1","input":"1 2","expected":"3"}]' | python3 runner.py execute --binary workspace/run1/solution --stdin
```

Output: JSON with `success`, `case_results`, `passed`, `failed`, `failures`

### Run (compile + execute)

```bash
python3 runner.py run --source solution.cpp --driver driver.cpp --tests tests.json --out-dir workspace/run1
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (compilation OK or all tests passed) |
| 1 | Compilation failed |
| 2 | One or more tests failed (wrong answer) |
| 3 | Runtime error / TLE |

## Test Case Format

```json
[
  {"id": "t1", "input": "2 7 11 15\n9", "expected": "0 1"},
  {"id": "t2", "input": "3 3\n6", "expected": "0 1"}
]
```

Fields: `id` (required), `input` (required), `expected` (required), `category` (optional)

## How to Solve a Problem

1. **Parse** the problem text — extract title, description, constraints, samples, function signature
2. **Generate** a C++ solution with `#include <bits/stdc++.h>`, matching the function signature exactly
3. **Generate** a test harness driver (main function that reads input, calls solution, prints output)
4. **Compile**: `python3 runner.py compile --source solution.cpp --driver driver.cpp --func-name <name> --out-dir workspace/<run_id>`
5. **If compile fails**: read the errors from JSON output, fix the code, retry (max 3-5 attempts)
6. **Execute**: `python3 runner.py execute --binary workspace/<run_id>/solution --tests tests.json`
7. **If tests fail**: read the failure diffs, fix the solution, recompile, re-execute
8. **Report**: summarize results with algorithm, complexity, and edge cases

## Compile Repair Loop (Agent-Orchestrated)

```
generate solution.cpp
  → compile --source solution.cpp --func-name solve
  → if failed:
      read errors from JSON
      fix code (address each error)
      retry compile (max 5 attempts)
  → if func_name missing:
      fix: ensure function signature matches exactly
```

## Execute Repair Loop (Agent-Orchestrated)

```
execute --binary solution --tests tests.json
  → if wrong_answer:
      read failure.diff for each failing case
      fix algorithm / edge cases
      recompile + re-execute
  → if TLE:
      optimize algorithm
      recompile + re-execute
  → if RTE/sigsegv:
      check for off-by-one, null deref, overflow
      fix + recompile + re-execute
  → regression gate: previously-passing cases must still pass
```

## Safety Guarantees

| Check | How |
|-------|-----|
| Function name matches | post-compile: `func_name in source` |
| No malicious calls | `has_malicious_calls()` — blocks system(), fopen(), curl |
| No debug output | agent must not emit cout << "DEBUG" |
| Test inputs respect bounds | agent generates within stated constraints |
| Regression gate | agent tracks previously-passing cases across repair iterations |

## Schemas (for agent use)

Import from `schemas/`:

```python
from schemas.problem_spec import ProblemSpecJSON, Sample, Constraints, ConstraintBound, FunctionSignature
from schemas.repair_spec import CompileResult, ExecResult, CaseVerdict, FailureClassification
from schemas.test_spec import TestCase, TestPlan
from schemas.report_spec import ReportJSON
```

## Workspace Layout

```
workspace/<run_id>/
├── solution.cpp          # agent-generated solution
├── driver.cpp            # agent-generated test harness
├── solution              # compiled binary
├── tests.json            # test cases
├── compile.json          # compile result (from runner output)
├── execute.json          # execute result (from runner output)
└── report.md             # final report (agent-built)
```

## Limitations

- C++20 only
- Requires g++ and POSIX (for resource limits on execution)
- Agent handles all reasoning — this skill is just the deterministic tooling
- No URL fetching, no stress testing beyond generated edge cases
