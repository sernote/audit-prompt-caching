# Top-Tier Audit Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Upgrade `audit-prompt-caching` from a strong portable skill into a fixture-backed, machine-readable, CI-validated audit package.

**Architecture:** Keep the package dependency-free and Python stdlib-only. Evolve existing helpers where they already own the responsibility, add focused scripts only for report rendering and layout linting, and back every behavior change with unittest coverage and fixture files.

**Tech Stack:** Python 3 stdlib, `unittest`, JSON/JSONL fixtures, Markdown documentation, GitHub Actions YAML.

---

## File Structure

- Modify `tests/test_prompt_cache_scripts.py`: add RED/GREEN coverage for normalized usage events, report rendering, layout linting, fixtures, and CI/productization files.
- Modify `audit-prompt-caching/scripts/analyze_usage_logs.py`: add `--jsonl-normalized` output for canonical per-record usage events.
- Create `audit-prompt-caching/scripts/render_audit_report.py`: combine normalized usage summaries, static findings, and optional metadata into Markdown or JSON.
- Create `audit-prompt-caching/scripts/layout_linter.py`: inspect JSON request payloads for cache-hostile layout patterns.
- Create `audit-prompt-caching/references/rules.json`: machine-readable rule IDs, categories, severities, and validation hints.
- Create `fixtures/`: small redacted provider scenarios and expected report artifacts.
- Modify `README.md`: add a five-minute demo using the fixtures.
- Modify `audit-prompt-caching/SKILL.md`: reference new helper scripts and rule metadata without broad rewrites.
- Modify `audit-prompt-caching/references/report-template.md`: note the machine-readable JSON companion.
- Create `.github/workflows/ci.yml`: run validation, trigger eval, unittest suite, syntax checks, whitespace checks, and bytecode cleanup guard.
- Create `LICENSE` and `CONTRIBUTING.md` if absent, with concise package governance.

---

## Phase 1: Proof Loop MVP

### Task 1: Golden Fixtures

**Files:**
- Create: `fixtures/openai/repeated_prefix_usage.jsonl`
- Create: `fixtures/anthropic/cache_control_usage.jsonl`
- Create: `fixtures/bedrock/checkpoint_usage.jsonl`
- Create: `fixtures/openrouter/routing_usage.jsonl`
- Create: `fixtures/vllm/apc_deployment.json`
- Create: `fixtures/expected/usage_summary_openai.json`
- Create: `fixtures/expected/report_openai.md`
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Write failing fixture tests**

Add tests that assert the fixture files exist, are valid JSON/JSONL, and include expected provider-specific cache fields.

- [x] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_fixture_pack_is_valid -v`

Expected: FAIL because fixtures do not exist.

- [x] **Step 3: Add minimal fixtures**

Create small, redacted records that exercise cached-token, cache-read, cache-write, route, and self-hosted metadata fields.

- [x] **Step 4: Run GREEN**

Run: `python3 -m unittest tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_fixture_pack_is_valid -v`

Expected: PASS.

### Task 2: Normalized Usage Event Stream

**Files:**
- Modify: `audit-prompt-caching/scripts/analyze_usage_logs.py`
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Write failing normalizer test**

Add a test for `python3 analyze_usage_logs.py --jsonl-normalized fixtures/openai/repeated_prefix_usage.jsonl` that expects one canonical JSON object per input record with `provider`, `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cache_benefit_tokens`, `total_input_tokens`, `output_tokens`, `model`, and `route`.

- [x] **Step 2: Run RED**

Run the new test directly and confirm it fails because `--jsonl-normalized` is unknown.

- [x] **Step 3: Implement minimal normalizer mode**

Reuse `normalize_record()` and add source/provider inference helpers without changing the existing summary output.

- [x] **Step 4: Run GREEN**

Run the targeted test, then `python3 -m unittest tests/test_prompt_cache_scripts.py`.

### Task 3: Report Renderer

**Files:**
- Create: `audit-prompt-caching/scripts/render_audit_report.py`
- Modify: `tests/test_prompt_cache_scripts.py`
- Modify: `README.md`
- Modify: `audit-prompt-caching/SKILL.md`
- Modify: `audit-prompt-caching/references/report-template.md`

- [x] **Step 1: Write failing renderer tests**

Add tests for Markdown and JSON output from the OpenAI fixture. Expected Markdown includes `# Prompt Cache Audit`, `Executive Summary`, `Findings`, `Expected Impact`, and a usage-derived cache hit ratio.

- [x] **Step 2: Run RED**

Run the renderer tests and confirm failure because the script does not exist.

- [x] **Step 3: Implement minimal renderer**

Support `--usage-log`, `--provider`, `--engine`, `--finding`, `--json`, and default Markdown output. Keep findings simple one-line strings and compute summary via `analyze_usage_logs.summarize()`.

- [x] **Step 4: Document the five-minute demo**

Add README commands that run usage analysis and render the sample report from fixtures.

- [x] **Step 5: Run GREEN**

Run targeted renderer tests, package validator, trigger eval, and full unittest suite.

---

## Phase 2: Audit Intelligence

### Task 4: Machine-Readable Rules

**Files:**
- Create: `audit-prompt-caching/references/rules.json`
- Modify: `audit-prompt-caching/SKILL.md`
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Write failing rules test**

Assert that `rules.json` is valid JSON, contains `AP-1`, `AP-2`, `AP-7`, and each rule has `id`, `category`, `default_severity`, `summary`, and `validation`.

- [x] **Step 2: Run RED**

Run the targeted rules test and confirm it fails because the file is missing.

- [x] **Step 3: Add minimal rule metadata**

Encode existing anti-pattern IDs without rewriting provider references.

- [x] **Step 4: Run GREEN**

Run targeted rules test and validator.

### Task 5: Layout Linter

**Files:**
- Create: `audit-prompt-caching/scripts/layout_linter.py`
- Create: `fixtures/layout/bad_openai_request.json`
- Create: `fixtures/layout/good_openai_request.json`
- Modify: `tests/test_prompt_cache_scripts.py`
- Modify: `README.md`
- Modify: `audit-prompt-caching/SKILL.md`

- [x] **Step 1: Write failing linter tests**

Test that the bad fixture emits `AP-1` and `AP-2` findings with nonzero exit status, while the good fixture emits clean checks with exit status 0.

- [x] **Step 2: Run RED**

Run the linter tests and confirm failure because the script is missing.

- [x] **Step 3: Implement minimal linter**

Inspect JSON request payloads for volatile keys/values before stable content, unsorted tool names, and dynamic schema fields. Emit JSON with `status`, `findings`, and `clean_checks`.

- [x] **Step 4: Run GREEN**

Run linter tests, full unittest suite, validator, and trigger eval.

---

## Phase 3: Public Productization

### Task 6: CI and Governance

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Modify: `README.md`
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Write failing productization tests**

Assert CI workflow exists and includes unittest, validator, trigger eval, syntax compile, `git diff --check`, and bytecode guard commands. Assert license and contribution guide exist.

- [x] **Step 2: Run RED**

Run targeted test and confirm it fails because files are missing.

- [x] **Step 3: Add CI and docs**

Create a minimal GitHub Actions workflow and concise governance docs.

- [x] **Step 4: Run GREEN**

Run targeted test and full verification commands.

### Task 7: Final Verification

**Files:**
- All touched files.

- [x] **Step 1: Run unittest suite**

Run: `python3 -m unittest tests/test_prompt_cache_scripts.py`

Expected: all tests pass.

- [x] **Step 2: Validate skill package**

Run: `python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching`

Expected: `status` is `ok`.

- [x] **Step 3: Run trigger eval**

Run: `python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching`

Expected: `status` is `ok`.

- [x] **Step 4: Compile Python syntax**

Run the repository syntax compile command from `AGENTS.md`.

Expected: every script and test prints `ok`.

- [x] **Step 5: Whitespace and generated bytecode**

Run: `git diff --check`; remove `__pycache__`; confirm no `*.pyc` files remain.

Expected: no output from whitespace check or bytecode search.
