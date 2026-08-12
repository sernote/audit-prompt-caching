# Usage Surface Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize Bedrock and both Gemini API-surface usage contracts through small adapters without changing the CLI output contract.

**Architecture:** Keep `analyze_usage_logs.py` as one dependency-free module. Ordered adapters translate wire-format records into one canonical token row; generic accounting stays outside adapters, so inclusive/additive math is not duplicated.

**Tech Stack:** Python 3 standard library, `unittest`, JSON, Markdown.

---

## File and Change Map

- `audit-prompt-caching/scripts/analyze_usage_logs.py`: surface adapters,
  envelope selection, and adapter-driven normalization.
- `tests/test_prompt_cache_scripts.py`: TDD fixtures for each public wire
  contract and existing-output regression coverage.
- `docs/superpowers/specs/2026-08-12-usage-surface-adapters-design.md`:
  approved architecture boundary.

### Task 1: Prove current Gemini Interactions failures

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`

- [ ] Add a normal Interactions response with `total_input_tokens`,
  `total_output_tokens`, and `total_cached_tokens`; assert inclusive input and
  cache ratio.
- [ ] Add a no-hit Interactions response with `total_cached_tokens: 0`; assert
  it does not emit an ambiguous-wrapper warning.
- [ ] Add a final streaming event with `metadata.total_usage`; assert it emits
  the same canonical values as the non-streaming response.
- [ ] Run the three tests and confirm RED because the current parser reads
  legacy Generate Content names or the top-level record.

### Task 2: Isolate surface adapters

**Files:**
- Modify: `audit-prompt-caching/scripts/analyze_usage_logs.py`
- Test: `tests/test_prompt_cache_scripts.py`

- [ ] Create a minimal adapter protocol/base with `matches(record)` and
  `extract(record)` returning the current canonical row plus explicit
  accounting semantics.
- [ ] Implement Bedrock, Gemini Interactions, Gemini Generate Content, and
  unknown-wrapper adapters. Preserve OpenAI and Anthropic behavior through
  dedicated adapters or existing extraction functions behind the same resolver.
- [ ] Select `usage`, `usage_metadata`/`usageMetadata`, and
  `metadata.total_usage`/`metadata.totalUsage` only in the adapter that owns
  that wire contract.
- [ ] Run the focused tests and confirm GREEN, then run the full unittest
  suite.

### Task 3: Preserve legacy behavior and verify

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`
- Modify: `audit-prompt-caching/scripts/analyze_usage_logs.py`

- [ ] Add a Generate Content fixture using `prompt_token_count`,
  `cached_content_token_count`, and `candidates_token_count` so Interactions
  support cannot regress legacy usage.
- [ ] Add a normalized-JSONL assertion for a streaming Interactions record.
- [ ] Run the focused tests and confirm GREEN.
- [ ] Run the full repository verification commands from `AGENTS.md`.
- [ ] Commit only the spec, plan, normalizer, and tests.
