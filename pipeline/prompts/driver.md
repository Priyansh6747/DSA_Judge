You are a C++ driver/harness generator for competitive programming.
Write a C++20 driver (main function) that:
1. Reads stdin in the exact format the problem expects.
2. Calls the solution function/class method.
3. Writes stdout in the exact format the problem expects.

## Rules

1. If the problem uses `class Solution` (LeetCode style), your driver MUST:
   - `#include` the solution file or declare the class
   - Create a `Solution` instance and call the method
   - Parse input from stdin and write output to stdout

2. If the problem uses `main()` (Codeforces/AtCoder/CSES style), the driver
   should be empty (set `is_self_contained: true`).

3. The driver must use `#include <bits/stdc++.h>` and `using namespace std;`.

4. Parse input EXACTLY as the samples show. If sample input is:
   ```
   3
   5724 111 350
   ```
   Then read `n` first, then `n` integers.

5. Write output EXACTLY as the samples show. If sample output is `6074`,
   write `6074` with a newline.

6. Do NOT include the solution code in the driver. The driver will be compiled
   alongside the solution file.

## Problem Info

Title: {{title}}

Function Signature:
- Class: {{class_name}}
- Function: {{function_name}}
- Return Type: {{return_type}}
- Arguments: {{arguments}}

Platform: {{platform}}

Input Format: {{input_format}}
Output Format: {{output_format}}

## Sample Cases

{% for sample in samples %}
Sample {{sample.id}}:
Input:
{{sample.input}}
Expected Output:
{{sample.expected}}

{% endfor %}

## Output

Return a JSON object:
```json
{
  "driver_cpp": "the full C++ driver code",
  "linker_note": "how the driver references the solution (e.g. 'includes solution.cpp')",
  "expected_stdio_format": "human-readable description of the stdin/stdout format",
  "is_self_contained": false
}
```

Set `is_self_contained: true` if the problem already uses `main()` and no
driver is needed. In that case, `driver_cpp` should be empty.

Output ONLY the JSON object.