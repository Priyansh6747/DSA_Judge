"""Thin LLM client wrapper — no SDK dependency assumed.

Two backends (auto-detected):
  1. opencode-native  — shell-out to `opencode run` (primary)
  2. OpenAI-compatible HTTP — fallback for standalone testing
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import jinja2


PROMPTS_DIR = Path(__file__).parent / "prompts"

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
    undefined=jinja2.StrictUndefined,
)


class LLMError(Exception):
    pass


class LLMJSONError(LLMError):
    def __init__(self, raw: str, parse_errors: list[str]) -> None:
        self.raw = raw
        self.parse_errors = parse_errors
        super().__init__(
            f"LLM did not return valid JSON. Errors: {parse_errors}\nRaw: {raw[:500]}"
        )


# ── Prompt loading ─────────────────────────────────────────────────

def load_prompt(name: str, **vars: Any) -> str:
    """Load a Jinja2 template from pipeline/prompts/<name>.md and render it."""
    template = _jinja_env.get_template(f"{name}.md")
    return template.render(**vars)


# ── JSON extraction from LLM output ───────────────────────────────

def _extract_json(raw: str) -> dict[str, Any]:
    """Extract a JSON object from LLM output that may contain markdown fences."""
    stripped = raw.strip()
    # Remove ```json ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", stripped, re.S)
    if fence_match:
        stripped = fence_match.group(1).strip()
    # Find first { ... } block
    brace_match = re.search(r"\{.*\}", stripped, re.S)
    if not brace_match:
        raise LLMJSONError(raw, ["No JSON object found in output"])
    candidate = brace_match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise LLMJSONError(raw, [str(e)])


def _strip_fenced(raw: str) -> str:
    """Extract content from ```...``` fences, or return raw."""
    stripped = raw.strip()
    fence_match = re.search(r"```(?:\w+)?\s*\n?(.*?)\n?\s*```", stripped, re.S)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


# ── Backend dispatch ───────────────────────────────────────────────

def _call_opencode(prompt: str) -> str:
    """Shell-out to opencode CLI."""
    bin_path = os.environ.get("OPENCODE_BIN", "opencode")
    model = os.environ.get("OPENCODE_MODEL", "")
    cmd = [bin_path, "run"]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise LLMError(f"opencode failed (rc={result.returncode}): {result.stderr[:500]}")
    return result.stdout


def _call_http(prompt: str) -> str:
    """OpenAI-compatible HTTP fallback."""
    import urllib.request

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENCODE_MODEL", "gpt-4o-mini")

    url = f"{base_url.rstrip('/')}/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }).encode()

    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


# ── Public API ─────────────────────────────────────────────────────

def complete(prompt_path: str, vars: dict[str, Any], *, expect_json: bool = True) -> str | dict:
    """Load prompt, call LLM, optionally parse JSON response.

    Args:
        prompt_path: name without .md extension (e.g. "parse", "driver")
        vars: template variables
        expect_json: if True, parse and return dict; else return raw string

    Returns:
        parsed JSON dict (expect_json=True) or raw string (expect_json=False)

    Raises:
        LLMJSONError if expect_json=True and output is not valid JSON after retry
    """
    prompt = load_prompt(prompt_path, **vars)

    backend = os.environ.get("LLM_BACKEND", "auto")
    if backend == "auto":
        backend = "opencode" if os.environ.get("OPENCODE_BIN") else "http"

    if backend == "opencode":
        raw = _call_opencode(prompt)
    else:
        raw = _call_http(prompt)

    if expect_json:
        return _extract_json(raw)
    return _strip_fenced(raw)


def complete_raw(prompt: str) -> str:
    """Call the LLM with a raw prompt string (no template, no JSON parsing)."""
    backend = os.environ.get("LLM_BACKEND", "auto")
    if backend == "auto":
        backend = "opencode" if os.environ.get("OPENCODE_BIN") else "http"

    if backend == "opencode":
        return _call_opencode(prompt)
    return _call_http(prompt)
