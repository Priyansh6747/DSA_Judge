---
name: dsa-judge
description: "Solve, verify, repair, or explain DSA problems with a robust compile-validate-repair pipeline."
---

# DSA Judge

A self-healing DSA problem solver. Compensates for LLM mistakes with
deterministic verification at every stage.

## Modes

| Mode | Required inputs | Pipeline does |
|------|----------------|---------------|
| **Solve** | problem, template, samples | Parse → Intake → Driver → Solution → Tests → Compile → Execute → Report |
| **Verify** | problem, template, solution, samples | Parse → Intake → Compile → Execute → Report |
| **Repair** | problem, template, failing code, samples | Parse → Intake → Compile → Diagnose → Fix → Recompile → Report |
| **Explain** | problem, accepted code, samples | Parse → Intake → Plan → Explain approach and complexity |

## How to detect mode

- Problem only → **Solve**
- Problem + code snippet → **Verify**
- Problem + code + "doesn't work" / "fails" / error output → **Repair**
- Problem + code + "explain" / "how does this work" → **Explain**

## How to use

### Step 1: Run the runner

```bash
python3 runner.py --problem-file <path>
python3 runner.py --problem "problem text"
echo "problem text" | python3 runner.py --stdin
```

### Step 2: Handle exit codes

| Exit | Meaning | Action |
|------|---------|--------|
| `0` | Success | Read `workspace/<run_id>/report.md` for the answer |
| `2` | Blocked intake | Read `workspace/<run_id>/gate.json` → ask user → write `gate_response.json` → re-run with `--resume <run_id>` |
| `3` | Soft intake | Read `workspace/<run_id>/gate.json` → ask user → write `gate_response.json` → re-run with `--resume <run_id>` |
| `4` | Compile failed | Read `workspace/<run_id>/compile_history.json` for errors |
| `5` | Tests failed | Read `workspace/<run_id>/exec_history.json` for failures |
| `6` | Parse failed | Ask user to rephrase the problem |

### Step 3: Resume after intake

```bash
# Write user answers to gate_response.json
echo '{"template_choice": "1"}' > workspace/<run_id>/gate_response.json
python3 runner.py --resume <run_id>
```

## Pipeline stages

```
Problem text
  │
  ▼
Stage 1: PARSE        (LLM → ProblemSpecJSON)
  │                    Validates JSON against pydantic schema
  ▼
Stage 2: INTAKE GATE  (deterministic)
  │                    Checks required + preferred fields
  │                    Blocks or asks user if missing
  ▼
Stage 3: DRIVER GEN   (LLM → driver.cpp)
  │                    Generates main() harness for testing
  │                    Syntax-checks driver+stub
  ▼
Stage 4: SOLUTION GEN (LLM → solution.cpp)
  │                    Generates C++20 solution
  │                    Validates function name, no debug, syntax
  ▼
Stage 5: EDGE TESTS   (deterministic categories + LLM cases)
  │                    Generates overflow/null/boundary test cases
  │                    Validates inputs against stated bounds
  ▼
Stage 6: COMPILE LOOP (deterministic + LLM repair)
  │                    g++ compile → on error: classify → LLM fix → retry
  │                    Max N attempts, signature check each iteration
  ▼
Stage 7: EXEC LOOP    (deterministic + LLM repair)
  │                    Run all cases → on fail: diff → LLM fix → retry
  │                    Regression gate: previously-passing must stay passing
  ▼
Final Report
```

## Safety guarantees

Every LLM output is re-checked:

| LLM emits | Deterministic check |
|---|---|
| ProblemSpecJSON | pydantic validation + bounds plausibility |
| Driver C++ | syntax-only compile + correct function references |
| Solution C++ | function name present + no debug/syscalls + syntax check |
| Edge test inputs | respect stated min/max bounds |
| Compile-repair patch | signature intact + no malicious calls + compiles |
| Exec-repair patch | all previously-passing cases still pass + signature intact |

## Exit codes

- `0` — success
- `2` — blocked intake (required fields missing)
- `3` — soft intake (preferred fields missing)
- `4` — compile failed after repair attempts
- `5` — tests failed after repair attempts
- `6` — parse failed (rephrase needed)

## Workspace layout

```
workspace/<run_id>/
├── problem_spec.json       # Stage 1 output
├── gate.json               # Stage 2 output
├── gate_response.json      # User answers (written by agent)
├── driver.cpp              # Stage 3
├── driver.json             # Stage 3 metadata
├── solution.cpp            # Stage 4 (current best)
├── solution.json           # Stage 4 metadata
├── tests.json              # Stage 5 plan
├── tests/
│   ├── <case_id>.in
│   └── <case_id>.exp
├── compile_history.json    # Stage 6 attempts
├── binary                  # final binary
├── exec_history.json       # Stage 7 attempts
└── report.md               # final report
```

## Limitations

- C++20 only
- Requires local g++ and POSIX (for resource limits)
- Sample test cases only (no stress testing beyond generated edge cases)
- No URL fetching
