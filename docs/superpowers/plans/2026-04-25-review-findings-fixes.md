# Review Findings Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix the five prompt-cache skill review findings with regression tests and verified CLI behavior.

**Architecture:** Keep all helper scripts dependency-free and stdlib-only. Add behavior-focused unittest coverage in `tests/test_prompt_cache_scripts.py`, then make minimal changes to the existing scripts. Preserve JSON output contracts while making failed validator sections explicit.

**Tech Stack:** Python 3 stdlib, `unittest`, local CLI scripts under `audit-prompt-caching/scripts/`, Markdown documentation.

---

## File Structure

- Modify `tests/test_prompt_cache_scripts.py`: add regression tests for Dockerfile scanning, CLI flag matching, validator section status, raw JSON prefix comparison, canonical JSON opt-in, and Anthropic denominator.
- Modify `audit-prompt-caching/scripts/extract_llm_calls.py`: add filename allowlist for no-extension deployment files and fix dash-prefixed CLI flag regexes.
- Modify `audit-prompt-caching/scripts/validate_skill_package.py`: record per-section `error` status when that section contributes errors.
- Confirm `audit-prompt-caching/scripts/prefix_stability_check.py` already compares raw bytes by default and keeps `--canonical-json` as opt-in; adjust only if regression tests fail.
- Confirm `audit-prompt-caching/scripts/analyze_usage_logs.py` already computes `total_input_tokens` and Anthropic-style ratio correctly; adjust only if regression tests fail.

### Task 1: Extractor Deployment Signals

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`
- Modify: `audit-prompt-caching/scripts/extract_llm_calls.py`

- [x] **Step 1: Write failing tests**

Add tests equivalent to:

```python
def test_extract_llm_calls_scans_dockerfile_for_vllm_flags(self):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "Dockerfile").write_text(
            'CMD ["vllm", "serve", "model", "--enable-prefix-caching"]\n'
        )

        result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["files_scanned"], 1)
        self.assertEqual(output["providers"]["vllm"], 2)
        self.assertEqual(output["findings"][0]["path"], "Dockerfile")

def test_extract_llm_calls_matches_sglang_dash_flags(self):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        compose = tmp_path / "compose.yaml"
        compose.write_text("command: python -m sglang.launch_server --disable-radix-cache\n")

        result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertGreaterEqual(output["providers"]["sglang"], 2)
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_extract_llm_calls_scans_dockerfile_for_vllm_flags tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_extract_llm_calls_matches_sglang_dash_flags
```

Expected: FAIL because `Dockerfile` is not scanned and `--enable-prefix-caching` / `--disable-radix-cache` do not match.

- [x] **Step 3: Implement minimal extractor fix**

Change `extract_llm_calls.py` to:

```python
SOURCE_FILENAMES = {
    "Dockerfile",
    "Containerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

def should_scan(path):
    return (
        path.is_file()
        and (
            path.suffix.lower() in SOURCE_SUFFIXES
            or path.name in SOURCE_FILENAMES
        )
    )
```

Change dash-prefixed flag regexes to:

```python
r"(^|\\s)--enable-prefix-caching(\\s|$)",
r"(^|\\s)--disable-radix-cache(\\s|$)",
```

- [x] **Step 4: Run tests to verify pass**

Run the same unittest command from Step 2.

Expected: PASS.

### Task 2: Validator Section Status

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`
- Modify: `audit-prompt-caching/scripts/validate_skill_package.py`

- [x] **Step 1: Write failing test**

Extend `test_validate_skill_package_reports_missing_references`:

```python
self.assertEqual(output["checks"]["references"], "error")
```

Add invalid eval and invalid script section tests:

```python
def test_validate_skill_package_marks_eval_and_script_checks_as_error(self):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        skill_dir = tmp_path / "bad-skill"
        (skill_dir / "evals").mkdir(parents=True)
        (skill_dir / "scripts").mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: bad-skill\ndescription: Use when testing bad package\n---\n"
        )
        (skill_dir / "evals" / "broken.json").write_text("{")
        (skill_dir / "scripts" / "broken.py").write_text("def nope(:\n")

        result = run_script("validate_skill_package.py", skill_dir)

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output["checks"]["evals"], "error")
        self.assertEqual(output["checks"]["scripts"], "error")
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_validate_skill_package_reports_missing_references tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_validate_skill_package_marks_eval_and_script_checks_as_error
```

Expected: FAIL because failed sections currently report `ok`.

- [x] **Step 3: Implement section status tracking**

In `validate_skill_package.py`, record `len(errors)` before each section and set:

```python
checks["references"] = "error" if len(errors) > before else "ok"
checks["evals"] = "error" if len(errors) > before else "ok"
checks["scripts"] = "error" if len(errors) > before else "ok"
```

- [x] **Step 4: Run tests to verify pass**

Run the same unittest command from Step 2.

Expected: PASS.

### Task 3: Existing Prefix And Usage Regressions

**Files:**
- Verify: `tests/test_prompt_cache_scripts.py`
- Verify: `audit-prompt-caching/scripts/prefix_stability_check.py`
- Verify: `audit-prompt-caching/scripts/analyze_usage_logs.py`

- [x] **Step 1: Confirm regression tests exist**

Check that `tests/test_prompt_cache_scripts.py` includes:

```python
test_prefix_stability_check_preserves_raw_json_key_order_by_default
test_prefix_stability_check_can_canonicalize_json_when_requested
test_analyze_usage_logs_uses_full_anthropic_denominator
```

- [x] **Step 2: Run those tests**

Run:

```bash
python3 -m unittest tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_prefix_stability_check_preserves_raw_json_key_order_by_default tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_prefix_stability_check_can_canonicalize_json_when_requested tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_analyze_usage_logs_uses_full_anthropic_denominator
```

Expected: PASS. If any test fails, fix the corresponding script minimally:

```python
# prefix_stability_check.py raw default
parser.add_argument("--canonical-json", action="store_true")

# analyze_usage_logs.py Anthropic denominator
total_input = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
cache_hit_ratio = cache_read_input_tokens / total_input
```

### Task 4: Full Verification And Commit

**Files:**
- Verify all changed files.

- [x] **Step 1: Run full unittest suite**

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: 15+ tests, OK.

- [x] **Step 2: Run package validators**

Run:

```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

Expected: both return 0 with `"status": "ok"`.

- [x] **Step 3: Run syntax and whitespace checks**

Run:

```bash
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

Expected: compile prints each Python file, `git diff --check` returns 0, final `find` prints nothing.

- [x] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/plans/2026-04-25-review-findings-fixes.md tests/test_prompt_cache_scripts.py audit-prompt-caching/scripts/extract_llm_calls.py audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching/scripts/prefix_stability_check.py audit-prompt-caching/scripts/analyze_usage_logs.py
git commit -m "fix: address prompt cache tooling review findings"
```

Expected: commit succeeds on branch `codex/fix-review-findings`.

## Self-Review

- Spec coverage: all five review findings map to Tasks 1-3.
- Placeholder scan: no TBD/TODO/later placeholders.
- Type consistency: scripts keep existing JSON dictionaries and stdlib-only CLI contracts.
