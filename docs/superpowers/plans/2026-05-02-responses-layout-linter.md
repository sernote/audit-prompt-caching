# Responses Layout Linter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `layout_linter.py` useful for OpenAI Responses-style request payloads, not only Chat-style `messages` payloads.

**Architecture:** Keep the linter dependency-free and backward-compatible. Add fixture-backed tests that prove volatile early content is detected in `input` arrays and strings, then normalize `messages` and `input` into one ordered text stream for AP-1 checks.

**Tech Stack:** Python stdlib, `unittest`, JSON fixtures.

---

### Task 1: Fixture-Backed Responses Payload Coverage

**Files:**
- Create: `fixtures/layout/bad_openai_responses_request.json`
- Create: `fixtures/layout/good_openai_responses_request.json`
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Write the failing tests**

Add tests asserting that the bad Responses fixture returns nonzero status with `AP-1`, while the good Responses fixture returns status `ok` and includes `AP-1` in `clean_checks`.

- [x] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_layout_linter_flags_bad_responses_prompt_layout \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_layout_linter_passes_good_responses_prompt_layout
```

Expected: FAIL before implementation because `layout_linter.py` does not inspect Responses `input`.

### Task 2: Responses Input Normalization

**Files:**
- Modify: `audit-prompt-caching/scripts/layout_linter.py`

- [x] **Step 1: Implement minimal input extraction**

Add helpers that produce ordered text segments from:
- Chat-style `messages[*].content`
- Responses-style `input` strings
- Responses-style `input` arrays containing message objects or content blocks

Preserve the existing AP-1, AP-2, and dynamic schema checks.

- [x] **Step 2: Run the targeted tests to verify GREEN**

Run the same targeted unittest command. Expected: PASS.

### Task 3: Documentation And Full Verification

**Files:**
- Modify: `README.md`
- Modify: `audit-prompt-caching/SKILL.md`

- [x] **Step 1: Document Responses payload support**

Update the linter descriptions so users know it handles Chat-style `messages` and Responses-style `input` payloads.

- [x] **Step 2: Run the repository verification gates**

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
python3 - <<'PY'
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'), *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')
PY
git diff --check
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```

Expected: all commands pass, and the final bytecode search prints nothing.
