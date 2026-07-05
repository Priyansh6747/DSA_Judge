# DSA Judge — Robust Skill Rewrite Plan

> Target runtime: **opencode** (the skill is consumed by opencode agents via `SKILL.md`).
> Goal: turn the brittle, regex-only skeleton into a robust, LLM-driven, self-healing
> pipeline that compensates for LLM mistakes with deterministic verification at every
> stage.

---

## 0. Diagnosis — Why the current implementation is poor

| Problem | Where | Impact |
|---|---|---|
| Parser is pure regex (`pipeline/engine.py:30-130`) | `parse_problem` | Fails on any non-LeetCode/CF phrasing; samples, constraints, signature regularly dropped |
| `extract_function_signature` (`pipeline/validator.py:208-242`) is broken (the `return_type` slice is nonsense) | template inference | Wrong signatures, silent corruption |
| No driver/harness generation | missing entirely | LeetCode `class Solution` problems can't be tested as stdin/stdout; the `SAMPLE` test in `test_pipeline.py` only works because the problem is jury-rigged into a `main()` form |
| No additional edge/stress test generation | missing entirely | Overflow / null / boundary bugs slip through samples |
| Compile-error loop has no LLM feedback path (`engine.py:244-254`) returns immediately on failure | no self-heal | Agent must babysit every compile failure |
| Test-failure loop is non-existent (`run_pipeline` validates once and returns) | no self-heal | No attempt to read diffs and patch |
| `ProblemSpec` mixes parser output, planner output, compile output, exec output (`state.py:75-164`) | god-object | Hard to extend, easy to corrupt |
| Mode gates are coarse (`validator.py:16-111`) | only blocks/intake/open | No "soft-missing" with structured JSON prompt for the LLM-driven intake |
| No structured-JSON contract between agent and engine | LLM steps ad-hoc | The agent is forced to do free-text parsing with no schema — the single biggest source of LLM error |
| No persistence of intermediate artifacts (plan, generated tests, repair attempts) | `run_pipeline` writes only `solution.cpp` + cases | Cannot feed compile errors back to the LLM in a structured way |
| `SKILL.md` describes 9 stages but the engine only implements 4 deterministic ones | mismatch | The agent improvises the missing 5 — inconsistently |

The fix is structural: **define a strict JSON contract at every stage boundary, make the
engine own every "verify/repair" loop, and let the LLM only ever produce/consume that
JSON.** The LLM is treated as an unreliable subroutine that is *always* checked by a
deterministic harness.

---

## 1. Target Architecture

```
                       ┌────────────────────────────────────────────┐
   User query ───────► │  Stage 1: PARSE        (LLM → JSON spec)   │
                       └─────────────┬──────────────────────────────┘
                                     │ ProblemSpecJSON
                                     ▼
                       ┌────────────────────────────────────────────┐
                       │  Stage 2: INTAKE GATE   (deterministic)     │
                       │  - required check → hard block w/ question   │
                       │  - preferred check → soft ask w/ options    │
                       └─────────────┬──────────────────────────────┘
                                     │ ProblemSpecJSON (complete)
                                     ▼
                       ┌────────────────────────────────────────────┐
                       │  Stage 3: DRIVER GEN   (LLM → harness.cpp)  │
                       │  + sample tests materialized as files        │
                       └─────────────┬──────────────────────────────┘
                                     │ harness.cpp + *.in/*.exp
                                     ▼
                       ┌────────────────────────────────────────────┐
                       │  Stage 4: SOLUTION GEN  (LLM → soln.cpp)     │
                       └─────────────┬──────────────────────────────┘
                                     │ solution.cpp
                                     ▼
                       ┌────────────────────────────────────────────┐
                       │  Stage 5: EDGE TEST GEN (LLM → tests.json)   │
                       │  + materialize overflow/null/large cases     │
                       └─────────────┬──────────────────────────────┘
                                     │ extra *.in/*.exp
                                     ▼
                       ┌────────────────────────────────────────────┐
                       │  Stage 6: COMPILE LOOP  (deterministic)      │
                       │  - g++ → on error: emit error JSON, ask LLM  │
                       │  - max N repair iterations                  │
                       └─────────────┬──────────────────────────────┘
                                     │ binary
                                     ▼
                       ┌────────────────────────────────────────────┐
                       │  Stage 7: EXEC + VALIDATE + REPAIR LOOP      │
                       │  - run all cases (sample + edge)            │
                       │  - on fail: emit diff JSON, ask LLM         │
                       │  - max N repair iterations                  │
                       └─────────────┬──────────────────────────────┘
                                     │
                                     ▼
                                Final Report
```

Every arrow is a **strict JSON schema** (versioned, validated by `pydantic`). The LLM
never sees free-text it has to re-parse. The engine never trusts LLM output without
running it.

---

## 2. New File Layout

```
dsa-judge/
├── SKILL.md                      # rewritten — concise, points agent at the scripts
├── opencode.jsonc                # unchanged (user config)
├── runner.py                     # rewritten — single entry, drives all 7 stages
├── plan.md                       # this file
├── schemas/
│   ├── __init__.py
│   ├── problem_spec.py           # pydantic ProblemSpecJSON + sub-models
│   ├── driver_spec.py            # harness generation request/response
│   ├── solution_spec.py          # solution generation request/response
│   ├── test_spec.py              # edge test spec (case + why + category)
│   ├── repair_spec.py            # compile/execution repair request/response
│   └── report_spec.py            # final report model
├── pipeline/
│   ├── __init__.py               # rewritten exports
│   ├── state.py                  # REMOVED — replaced by schemas/problem_spec.py
│   ├── engine.py                 # rewritten — orchestration only, no parsing logic
│   ├── validator.py              # rewritten — gate logic against pydantic model
│   ├── parser.py                 # NEW — LLM-driven parse stage (Stage 1)
│   ├── intake.py                 # NEW — Stage 2 gate + question building (Stage 2)
│   ├── driver_gen.py             # NEW — driver/harness generation (Stage 3)
│   ├── solution_gen.py           # NEW — solution generation (Stage 4)
│   ├── test_gen.py               # NEW — edge test generation (Stage 5)
│   ├── compiler.py               # NEW — compile + repair loop (Stage 6)
│   ├── executor.py               # NEW — execute + repair loop (Stage 7)
│   ├── reporter.py               # NEW — final report builder
│   ├── llm.py                    # NEW — thin LLM client wrapper (no SDK dep assumed)
│   ├── prompts/
│   │   ├── parse.md              # Stage 1 system prompt + JSON schema
│   │   ├── driver.md             # Stage 3 prompt
│   │   ├── solution.md           # Stage 4 prompt
│   │   ├── tests.md              # Stage 5 prompt
│   │   ├── compile_repair.md     # Stage 6 prompt
│   │   └── exec_repair.md        # Stage 7 prompt
│   └── templates/                # unused at runtime — kept for reference only
├── tests/
│   ├── __init__.py
│   ├── test_parse.py             # tests Stage 1 against golden JSON
│   ├── test_intake.py            # tests gate logic
│   ├── test_driver_gen.py        # tests harness materialization against templates
│   ├── test_compiler.py          # tests compile-repair loop with seeded bad code
│   ├── test_executor.py          # tests exec-repair loop with seeded wrong output
│   ├── test_schemas.py           # round-trip JSON validation tests
│   └── fixtures/
│       ├── leetcode_two_sum.txt
│       ├── codeforces_watermelon.txt
│       ├── cses_repetitions.txt
│       ├── atcoder_abc000_a.txt
│       └──stress_*.in / .exp
└── test_pipeline.py              # DELETED — replaced by tests/
```

---

## 3. Detailed Stage Design

### Stage 1 — Parse (natural language → structured JSON)

**New file:** `pipeline/parser.py`
**New schema:** `schemas/problem_spec.py`

##### Goal
Replace the regex parser with an **LLM-driven parser** that emits a strict JSON object
matching `ProblemSpecJSON`. The LLM is asked to:
1. Extract `title`, `description`, `input_format`, `output_format`.
2. Extract every sample as `{id, input, expected}` — preserving exact whitespace.
3. Extract constraints as structured entities:
   ```json
   "constraints": {
     "time_limit_ms": 1000,
     "memory_limit_mb": 256,
     "bounds": [
       {"variable": "n",    "min": 1,     "max": 100000, "kind": "int"},
       {"variable": "a[i]", "min": -1e9,  "max": 1e9,    "kind": "int"}
     ],
     "guarantees": ["array sorted ascending", "a[i] distinct"]
   }
   ```
4. Detect platform with a **confidence** in `[0,1]` and a `source` string.
5. Detect the function signature (class name, function name, return type, argument
   list) **only if it is literally present in the text** — otherwise leave empty and
   flag for intake.

##### Deterministic layer (around the LLM)
- `pipeline/parser.py:parse_problem(text)` calls `llm.complete(prompt=parse.md, input=text)`.
- It then validates the LLM's JSON string against `ProblemSpecJSON` (pydantic).
- On validation failure: feed the pydantic errors back to the LLM **once** (single
  retry with the error list appended). On second failure: raise `ParseError` and the
  runner surfaces "I couldn't parse your problem; please rephrase".
- It never *guesses* missing fields — they are left empty for Stage 2 to handle.

##### `schemas/problem_spec.py` (logic)
- `class Sample(BaseModel)`: `id: str`, `input: str`, `expected: str` — both required
  non-empty; validator rejects samples where `expected` is empty.
- `class ConstraintBound(BaseModel)`: `variable`, `min`, `max` (as `Decimal` to avoid
  float drift), `kind: Literal["int","float","str","array"]`.
- `class Constraints(BaseModel)`: `time_limit_ms?`, `memory_limit_mb?`, `bounds: list`,
  `guarantees: list[str]`.
- `class FunctionSignature(BaseModel)`: `name?`, `return_type?`, `arguments?`,
  `class_name?` — all optional, blank string acceptable.
- `class ProblemSpecJSON(BaseModel)`: the root model. Fields:
  `run_id`, `mode: Literal["solve","verify","repair","explain"]`,
  `title`, `description`, `samples: list[Sample]`, `constraints: Constraints`,
  `input_format`, `output_format`, `platform: Platform`, `platform_confidence: float`,
  `platform_source: str`, `function_signature: FunctionSignature`,
  `template: str`, `starter_code: str`, `user_solution: str`,
  `parse_confidence: float`, `parse_notes: list[str]`.
- `model_config = ConfigDict(extra="forbid")` so unexpected keys are rejected (forces
  LLM to follow the schema, not invent fields).
- A `to_run_state()` method returns a frozen `RunState` (see below) used by the rest
  of the pipeline.

##### Prompt (`pipeline/prompts/parse.md`)
- System role: "You are a strict JSON extractor. Output only JSON, no prose."
- Embedded JSON schema (so the model knows field names + types).
- Hard rules: don't invent samples; preserve whitespace verbatim; if a field is absent
  emit `null`/`""` not a guess; emit constraints exactly as written (translate `10^9`
  to `1e9`); platform confidence ≤ 0.3 if no platform signal.

---

### Stage 2 — Intake Gate (deterministic, with quick-cut)

**New file:** `pipeline/intake.py`
**Changed file:** `pipeline/validator.py` (rewrite against pydantic model)

##### Goal
A **hard gate** that prevents the pipeline from running with insufficient data, and a
**soft gate** that asks exactly one structured question to fill the most impactful
gaps. The "quick cut" the user requested lives here: if any of
`description / samples / template / constraints` is missing, we stop *immediately* and
ask the user — we never let the LLM paper over it.

##### Logic
```python
def classify(spec: ProblemSpecJSON) -> GateResult:
    missing_required = []   # blocks
    missing_preferred = []   # asks

    if not spec.description:        missing_required.append("description")
    if not spec.samples:            missing_required.append("samples")
    if mode in {REPAIR, VERIFY, EXPLAIN} and not spec.user_solution:
                                   missing_required.append("user_solution")

    if not spec.template and mode in {SOLVE, REPAIR}:
                                   missing_preferred.append("template")
    if not spec.function_signature.name and mode in {SOLVE, REPAIR}:
                                   missing_preferred.append("function_signature")
    if not spec.constraints.bounds and not spec.constraints.guarantees:
                                   missing_preferred.append("constraints")
    ...
```

##### Return shape
```python
class GateResult(BaseModel):
    status: Literal["open","intake","blocked"]
    missing_required: list[str]
    missing_preferred: list[str]
    question_md: str        # formatted prompt for the agent to show the user
    argv_options: Optional[list[str]]   # for menu-style preferences (LC/CF/AtCoder/CSES/custom)
```

##### Quick-cut behaviour
- `blocked` → runner exits with status `2` and prints `question_md`. The agent must
  wait for the user. No further stages run.
- `intake` → runner exits with status `3` and prints `question_md` (which contains a
  numbered menu for template + a field prompt for signature/constraints). The agent
  collects the reply, calls `intake.apply_user_response(spec, answers)` which returns
  a new `ProblemSpecJSON` and re-runs `classify`. Stage 3 only runs when `status == "open"`.
- `open` → proceed.

##### Removal from `validator.py`
The old `extract_function_signature` regex is **deleted** — Stage 1 owns signature
extraction. `detect_platform` is kept as a *hint* function that Stage 1's parser.py
can invoke to seed the LLM prompt, but the LLM's structured output is authoritative.

---

### Stage 3 — Driver Code Generation (harness)

**New file:** `pipeline/driver_gen.py`
**New prompt:** `pipeline/prompts/driver.md`

##### Why this stage exists (the current implementation skips this entirely)
Problems on LeetCode (and similar) expect a `class Solution { ... }` with a method;
samples in markdown (`Input: nums = [2,7,11,15], target = 9 → [0,1]`). To *execute*,
we need a `main()` that:
1. Reads stdin using the platform's expected format.
2. Calls `Solution().method(...)` (or the standalone `solve(...)`).
3. Writes stdout in the expected format.

##### Logic
- `driver_gen.generate_driver(spec) -> DriverArtifact` calls the LLM with:
  - the function signature,
  - the input/output format strings,
  - samples (as concrete examples of stdin→stdout),
  - platform (to pick parsing conventions — e.g. LeetCode arrays vs CF `n\nnums`).
- Returns:
  ```python
  class DriverArtifact(BaseModel):
      driver_cpp: str        # the harness with `#include "solution.h"`
      linker_note: str        # how the driver references the user's solution
      expected_stdio_format: str   # human description
  ```
- The driver is written to `workspace/<run_id>/driver.cpp`.
- The user-solution file location is fixed: `workspace/<run_id>/solution.cpp`. The
  driver references symbols from solution via an `#include "solution.cpp"` or a
  compile-unit concatenation strategy (chosen by platform — see `compiler.py`).
- If the platform is plain `main()`-style (CF/AtCoder/CSES), `driver_cpp` is empty
  and the runner notes `self_contained = True` — the solution itself is the entry
  point.

##### Deterministic guard
- `driver_gen` cannot finish until the LLM emits valid C++ that **parses as a
  translation unit in isolation** (we run `g++ -fsyntax-only` on driver+stub-solution).
  If syntax check fails: 1 retry with the syntax errors appended. Beyond that, raise
  `DriverGenFailed` and surface to the user.

---

### Stage 4 — Solution Generation

**New file:** `pipeline/solution_gen.py`
**New prompt:** `pipeline/prompts/solution.md`

##### Goal
LLM writes the C++20 solution. The model receives:
- the full `ProblemSpecJSON`,
- the planner block (algorithm + complexity) *(optional — see "planner" note below)*,
- the **exact** function signature / class name / entry point,
- the constraints (so it picks the right data types: `long long` if any bound ≥ 2e9),
- a list of named edge cases (derived from constraints by `test_gen.precompute_edges`
  — single element, all-equal, max-size, negatives, empty input where allowed).

##### Timeout / overflow policy
- If `max(n) * time_complexity_hint > 1e8`, the prompt explicitly warns "your solution
  must run in ≤ X ops; aim for O(...) not O(...)".
- If any bound exceeds `int` range, the prompt forces `long long` for that variable.

##### Output
```python
class SolutionArtifact(BaseModel):
    solution_cpp: str
    algorithm: str
    complexity_time: str
    complexity_memory: str
    edge_cases_addressed: list[str]
    self_review_notes: list[str]
```

##### Deterministic sanity check (no LLM)
1. `solution_cpp` must contain the function signature's exact name (regex). If not →
   reject, retry once with the warning "you renamed the function; signature must match
   exactly".
2. `solution_cpp` must not contain `cout << ... << endl` debug markers (sentinel
   strings `DEBUG`, `#ifdef DEBUG`) — strip or reject.
3. If a driver was generated in Stage 3, run `g++ -fsyntax-only` on the combined
   driver+solution. Syntax errors → retry once with the compiler stderr appended.

> **Planner note:** Stage 4 previously required an explicit "planner" stage producing
> algorithm/complexity. In the rewrite the LLM emits it as part of `SolutionArtifact`.
> The deterministic gate only enforces *internal consistency*: if the LLM says
> "single-pass O(n)" the prompt warns it that the compiler/executor will check timing
> on a max-size synthetic case (Stage 5 produces that case). No separate planner stage.

---

### Stage 5 — Additional Test Generation (edge & stress)

**New file:** `pipeline/test_gen.py`
**New prompt:** `pipeline/prompts/tests.md`

##### Goal
Generate *extra* test cases beyond the samples, targeted at the **constraints**.
The current implementation only ever validates against the samples provided — which
is exactly how overflow / null-input / boundary bugs slip through. This stage
synthesizes them.

##### Logic — deterministic category selection + LLM case authoring
`test_gen.synthesize(spec) -> TestPlan`:

For each constraint bound `{variable, min, max, kind}` produce a **deterministic**
list of categories (no LLM needed for the *which* — only the *what*):

| Category | Trigger | Example case |
|---|---|---|
| `min` | `min` is finite | input with `variable == min` |
| `max` | `max` is finite | input with `variable == max` |
| `max_plus_one` | integer | `variable == max+1` (expects handled / rejected cleanly) |
| `zero` | `min <= 0 <= max` | `variable == 0` |
| `empty` | variable is array/string and `min == 0` | empty array |
| `single` | `min <= 1` | size-1 array |
| `all_duplicates` | array var | all elements equal |
| `all_distinct` | array var | every element distinct |
| `negative_extreme` | `min < 0` | all values = min |
| `overflow_sum` | `max * max_count > INT_MAX` | sum could overflow `int` |
| `large_overlap` | graph/string | the worst-case overlap pattern |

The LLM is then asked to write **concrete input/expected pairs** for each selected
category, with each case annotated `category` + `why` (free text). Deterministic
post-checks:
- The generated `input` must respect every stated bound (`min <= x <= max`) — checked
  by `test_gen.validate_against_bounds`. Any out-of-bounds case is **dropped** and
  logged.
- For categories where the expected output is unknown (e.g. property tests), the LLM
  may mark `expected = null` and `compute_via = "brute_force"` — the engine will
  generate the brute-force reference by calling Stage 4 again with an explicit "write
  the simplest correct brute force, ignore performance" prompt and run that to obtain
  the expected output.

##### Output
```python
class TestCase(BaseModel):
    id: str
    input: str
    expected: Optional[str]
    category: str
    why: str
    compute_via: Literal["provided","brute_force"]

class TestPlan(BaseModel):
    cases: list[TestCase]
    brute_force_cpp: Optional[str]   # only if any case needs brute-force oracle
```

Files written:
- `workspace/<run_id>/tests/<case_id>.in`
- `workspace/<run_id>/tests/<case_id>.exp`   (may be empty; filled after oracle run)
- `workspace/<run_id>/tests/<case_id>.meta.json`

---

### Stage 6 — Compile (with LLM repair loop)

**New file:** `pipeline/compiler.py`
**New prompt:** `pipeline/prompts/compile_repair.md`

##### Logic
```python
def compile_with_repairs(spec, solution_cpp, driver_cpp, max_attempts=5) -> CompileResult:
    for attempt in range(max_attempts):
        write combined source
        result = g++ -std=c++20 -O2 -Wall -Wextra -fsyntax-only ... then full compile
        if result.success:
            return CompileResult(success=True, attempts=attempt+1, binary_path=...)
        # deterministic error classification (no LLM):
        errors = classify_compiler_errors(result.stderr)
        # ask LLM to patch:
        patched = llm.complete(compile_repair.md, {
            "solution_cpp": solution_cpp,
            "errors": errors,
            "attempt": attempt,
            "previous_attempts": [...]
        })
        # validate that the patched solution still satisfies signature check
        if not signature_ok(patched):  # don't trust LLM
            continue
        solution_cpp = patched
    return CompileResult(success=False, attempts=max_attempts, errors=...)
```

##### Deterministic error classifier
`compiler.classify_compiler_errors(stderr) -> list[ErrorNode]` parses g++ output into:
```python
class ErrorNode(BaseModel):
    kind: Literal["syntax","type","undeclared","template","linker","other"]
    file: str
    line: int
    column: int
    message: str
```
This structured form makes the LLM repair prompt much smaller and more reliable than
pasting raw stderr.

##### Repair loop invariants (checked every iteration, not trusted)
- The revised `solution_cpp` must still contain the exact required function name /
  class name — Stage 4's rule. Reject otherwise, retry.
- The revised solution must not introduce network/file/`system()` calls (sentinel
  regex). Reject otherwise.
- The compile attempt counter is the **only** thing that stops the loop — there is no
  "give up early" heuristic, because LLMs improve with one more shot.

---

### Stage 7 — Execute + Validate + Repair loop

**New file:** `pipeline/executor.py`
**New prompt:** `pipeline/prompts/exec_repair.md`

##### Logic
```python
def execute_with_repairs(spec, binary, cases, max_attempts=5) -> ExecResult:
    for attempt in range(max_attempts):
        results = [run_case(binary, c) for c in cases]   # all cases
        verdicts = [validate(c, r) for c, r in zip(cases, results)]
        if all(v.passed for v in verdicts):
            return ExecResult(success=True, attempts=attempt+1, results=...)
        # build structured diff JSON (no LLM):
        failures = [v for v in verdicts if not v.passed]
        classification = classify_failures(failures)   # wrong_answer / tle / rte / sigsegv
        # ask LLM to patch:
        patched = llm.complete(exec_repair.md, {
            "solution_cpp": current_solution,
            "failures": failures,           # structured diffs
            "classification": classification,
            "edge_case_hints": spec.edge_cases,
            "attempt": attempt
        })
        # Stage 6 is invoked *implicitly* on patched solution
        compiled = compile_with_repairs(spec, patched, driver_cpp, max_attempts=3)
        if not compiled.success:
            continue
        current_solution = patched
        binary = compiled.binary_path
    return ExecResult(success=False, attempts=max_attempts, ...)
```

##### Deterministic failure classifier
`executor.classify_failures(failures)`:
- `tle` if the process was killed by timeout.
- `rte` if exit code ≠ 0 and ≠ 124 (timeout).
- `sigsegv` / `sigfpe` if signal-based exit, surface the signal name.
- `wrong_answer` otherwise, with a unified diff (line-by-line, expected vs actual).

##### Repair-loop invariants
- After LLM patch:
  1. signature still matches (Stage 4 rule, re-validated).
  2. all **previously passing** cases still pass (regression gate). If a patch breaks
     a previously-passing case the patch is **rejected** and we retry with a stronger
     prompt listing "regression: case X used to pass".
  3. compile must succeed (Stage 6 sub-loop).
- The loop runs **all cases every time**, never just the failures — to catch
  regressions.

---

### Final Report

**New file:** `pipeline/reporter.py`
**New schema:** `schemas/report_spec.py`

Builds a markdown report identical to the format in the current `SKILL.md`'s "Stage 9"
table, plus new sections keyed to the new stages:
- Driver generation result (success / details).
- Edge test plan summary (categories generated, dropped, oracle-used).
- Compile repair history (attempts, errors per attempt).
- Exec repair history (attempts, regressions caught, final verdict).

---

## 4. Changes to Existing Files

### `SKILL.md` (rewrite — concise)
- Keep YAML frontmatter (`name`, `description`).
- Replace the 9-stage prose with a single *"How to use"* section pointing at `runner.py
  --problem-file <path>` and the JSON contract files under `schemas/`.
- Document the **exit codes** of `runner.py` so the opencode agent knows what to do:
  - `0` → success, report written to `workspace/<run_id>/report.md`.
  - `2` → blocked intake (agent must ask the user the question in `gate.json`).
  - `3` → soft intake (agent prompts user with `gate.json:question_md`, then re-runs).
  - `4` → compile failed after repairs.
  - `5` → exec/tests failed after repairs.
  - `6` → parser gave up (rephrase the problem).
- The agent-facing instructions become: "run `runner.py`; if exit ≠ 0, read
  `gate.json` / `repair.json` and respond; loop". This is the **only** contract the
  agent needs to learn — no prose pipeline description.

### `runner.py` (rewrite)
- Parse CLI args: `--problem-file`, `--problem`, `--stdin`, `--mode`,
  `--workspace`, `--resume <run_id>`, `--max-compile-attempts`, `--max-exec-attempts`.
- Calls `parser.parse_problem` → `intake.classify` → (if open) `driver_gen` →
  `solution_gen` → `test_gen` → `compiler.compile_with_repairs` →
  `executor.execute_with_repairs` → `reporter.build`.
- Writes intermediate JSON files under `workspace/<run_id>/` after **every** stage
  (`problem_spec.json`, `gate.json`, `driver.json`, `solution.json`, `tests.json`,
  `compile_history.json`, `exec_history.json`, `report.md`). These are the resume
  points the agent uses to answer user questions or to resume after intake.
- The current `runner.py:42-67` "agent must populate solution_cpp before calling" hack
  is removed — the runner is now self-sufficient.

### `pipeline/state.py` (delete)
- Replaced by `schemas/problem_spec.py` (pydantic) plus a thin `RunState` frozen
  dataclass that the engine passes between stages. `RunState` holds:
  `spec: ProblemSpecJSON`, `driver: Optional[DriverArtifact]`,
  `solution: Optional[SolutionArtifact]` (the *current* best solution),
  `tests: Optional[TestPlan]`, `compile_history: list`,
  `exec_history: list`, `run_dir: Path`, `run_id: str`.
- All `Confidence`/`Sample`/`FunctionSignature`/`SolutionStatus` enums move to
  `schemas/`. `Mode` becomes a `Literal` in the pydantic model.

### `pipeline/engine.py` (rewrite — thin orchestrator)
- `parse_problem(text)` → 1-line wrapper around `parser.parse_problem`.
- `run_pipeline(spec, workspace)` → orchestrates Stages 3-7. All parsing/helpers
  removed; the function just chains the new modules and persists intermediate JSON.

### `pipeline/validator.py` (rewrite against pydantic)
- `validate_requirements` → `intake.classify`.
- `detect_platform` kept as a static hint helper used by `parser.py`.
- `extract_function_signature` **deleted** (was broken).
- `intake_summary` removed (replaced by `GateResult.question_md`).

### `pipeline/__init__.py` (rewrite exports)
- Export: `parse_problem`, `classify_intake`, `generate_driver`, `generate_solution`,
  `synthesize_tests`, `compile_with_repairs`, `execute_with_repairs`, `build_report`.
- Drop the old free-floating helper exports.

### `test_pipeline.py` (delete)
- Replaced by `tests/` package using pytest-style functions; fixtures under
  `tests/fixtures/`. The current `PROBLEM_LC` etc. move into fixtures so multiple
  test files can share them.

---

## 5. LLM Client Design (`pipeline/llm.py`)

Because the runtime is opencode and the skill is invoked by an opencode agent, the
LLM-call mechanism must **not** assume a specific SDK. `llm.py` exposes:

```python
def complete(prompt_path: str, vars: dict, *, expect_json: bool = True) -> str: ...
```

Two backends are supported (auto-detected):

1. **opencode-native** — if the skill is being invoked by an opencode agent, calls
   are routed via a small shell-out to the opencode CLI (`opencode run --prompt ...`)
   configured by env var `OPENCODE_BIN`. This is the primary path.
2. **OpenAI-compatible HTTP** — fallback for standalone testing (`OPENAI_BASE_URL`,
   `OPENAI_API_KEY`, `OPENCODE_MODEL`). Lets the test suite run offline-ish against a
   local LLM.

`expect_json=True` strips fenced code blocks, extracts the first `{...}` JSON object,
and parses it; on parse failure it raises `LLMJSONError` carrying the raw text + the
pydantic errors so the caller can retry-with-context.

All prompts live under `pipeline/prompts/*.md` as Jinja2-style templates with
`{{var}}` placeholders — kept out of Python so they can be edited without touching
code. (Jinja2 is only required if not vendored; we can use a tiny `str.replace`-
based templater to avoid the dep — kept optional.)

---

## 6. Determinism / Safety Guarantees (the "cover up for LLM" part)

The whole skill is built around the principle that **every LLM output is re-checked**:

| LLM emits | Deterministic check that catches a wrong emit |
|---|---|
| ProblemSpecJSON | pydantic validation + bounds are plausible + sample `expected` matches the `output_format` regex if any |
| Driver C++ | syntax-only compile + driver references `Solution().method(...)` with the right name |
| Solution C++ | function-name regex present + no `system/network` calls + syntax-only compile |
| Edge tests | every case respects stated `min/max` bounds; dropped if not |
| Compile-repair patch | signature intact + file contains no syscall/network + sanity-compile passes |
| Exec-repair patch | stage-6 compile passes + **all previously-passing cases still pass** (regression gate) + signature intact |

If any check fails, the LLM is given the **structured** failure (never raw model
output) and another shot — up to the configured attempt cap. After the cap, the
runner stops with a non-zero exit code and a `repair.json` the agent can show the
user. We never silently accept wrong code.

---

## 7. Persistence / Resume Contract

Every stage writes its result as JSON to `workspace/<run_id>/`:

```
workspace/<run_id>/
├── problem_spec.json       # Stage 1 output
├── gate.json               # Stage 2 output (status + question_md)
├── driver.cpp              # Stage 3
├── driver.json             # Stage 3 metadata
├── solution.cpp            # Stage 4 (current best)
├── solution.json           # Stage 4 metadata
├── tests.json              # Stage 5 plan
├── tests/
│   ├── <case_id>.in
│   ├── <case_id>.exp
│   └── <case_id>.meta.json
├── compile_history.json    # Stage 6 attempts
├── binary                  # final binary (if any)
├── exec_history.json       # Stage 7 attempts
└── report.md               # final
```

`runner.py --resume <run_id>` re-reads `problem_spec.json` + `gate.json`, and if
the gate is now satisfied (agent wrote a `gate_response.json`), continues from
the next stage. This is what makes the skill usable as a *single opencode agent
loop*: the agent runs runner, sees exit code 3, asks the user, writes
`gate_response.json`, re-runs `runner.py --resume`.

---

## 8. Implementation Order (suggested PR slicing)

1. **`schemas/`** — pure pydantic, no deps. Get `test_schemas.py` green.
2. **`pipeline/llm.py`** + `pipeline/prompts/parse.md` — Stage 1. Get
   `test_parse.py` green against fixtures.
3. **`pipeline/intake.py`** — Stage 2 gate. Get `test_intake.py` green.
4. **`pipeline/compiler.py` + `pipeline/executor.py`** — Stages 6 + 7 with seeded
   bad solution (no LLM calls in tests; mock `llm.complete`).
5. **`pipeline/driver_gen.py` + `pipeline/solution_gen.py`** — Stages 3 + 4. Mock LLM
   in tests, real LLM only for manual fixtures.
6. **`pipeline/test_gen.py`** — Stage 5 + bounds validator.
7. **`pipeline/reporter.py` + `runner.py` rewrite** — wire everything.
8. **`SKILL.md` rewrite** — last, so it reflects what shipped.

---

## 9. Out of Scope (explicit, V2)

- Multi-language targets (only C++20 in v1).
- URL fetching of problem statements (the agent may paste them).
- Long-running stress tests (we generate representative cases, not millions).
- GUI / progress streaming (runner prints stage transitions to stdout).
- Distributed execution / containerisation (the runner assumes local `g++` + POSIX).

---

## 10. Acceptance Criteria for the Skill

The rewrite is "done" when **all** of the following hold:

1. `python runner.py --problem-file tests/fixtures/leetcode_two_sum.txt` with all
   fields present exits `0` and produces a passing report with at least 5 generated
   edge cases.
2. Same invocation against `codeforces_watermelon.txt` exits `0` and self-repairs at
   least one deliberately injected compile error seeded in the prompt fixture.
3. Removing constraints from a fixture makes `runner` exit `3` with a `gate.json`
   whose `question_md` mentions "Constraints" specifically.
4. Removing every sample makes `runner` exit `2` with a `gate.json` mentioning
   "samples".
5. A fixture with an intentionally-overflowing expected `int` sum is caught by Stage 5's
   `overflow_sum` category and the LLM fix loop, or reported as a confidence weakness
   in `report.md`.
6. `pytest tests/` is fully green with mocked LLM; the fixtures are deterministic.