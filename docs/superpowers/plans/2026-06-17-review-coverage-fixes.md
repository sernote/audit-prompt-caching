# Review Coverage Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix review findings from the Plugin Eval budget rewrite without reintroducing Plugin Eval budget failures.

**Architecture:** Add regression tests that preserve scenario coverage, trigger negative coverage, and actionable anti-pattern detail. Restore compact but provider-specific eval and reference content. Keep `SKILL.md` as the router, but ensure always-loaded trigger text includes narrow exclusions.

**Tech Stack:** Python `unittest`, JSON eval fixtures, Markdown references, Plugin Eval Node CLI.

---

### Task 1: RED Tests

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Add eval scenario coverage test**

Assert `evals/evals.json` includes compact pressure cases for OpenAI volatile prefix/schema/tool order, dynamic agent tools, vLLM routing/KV capacity, Qwen/DashScope usage fields, Anthropic migration/layout, OpenRouter routing, Bedrock cachePoint, and Anthropic automatic caching.

- [x] **Step 2: Add trigger negative coverage test**

Assert `evals/trigger_eval.json` keeps negative examples for generic prompt writing, generic RAG, token counting, JSON schema review, non-LLM routing/Kubernetes, and generic OpenRouter routing basics.

- [x] **Step 3: Add anti-pattern detail test**

Assert every `references/rules.json` rule has concise `search`, `fix`, and `avoid` fields so `SKILL.md` can safely defer anti-pattern details.

- [x] **Step 4: Verify RED**

Run the new tests and confirm they fail on the current compacted artifacts.

### Task 2: GREEN Content

**Files:**
- Modify: `audit-prompt-caching/evals/evals.json`
- Modify: `audit-prompt-caching/evals/trigger_eval.json`
- Modify: `audit-prompt-caching/references/rules.json`
- Modify if needed: `audit-prompt-caching/SKILL.md`
- Modify if needed: compact provider references to offset budget growth

- [x] **Step 1: Restore compact scenario evals**

Add short, high-signal eval cases instead of the previous long prose. Preserve provider-specific expected behavior without restoring the full token-heavy text.

- [x] **Step 2: Restore trigger negatives**

Add concise negative trigger cases for non-cache tasks so the always-loaded description and trigger evals both discourage over-triggering.

- [x] **Step 3: Make rules actionable**

Add `search`, `fix`, and `avoid` fields to each anti-pattern rule. Keep each field short.

- [x] **Step 4: Keep Plugin Eval budget below fail**

Run Plugin Eval and, if deferred cost crosses back into failure, trim redundant wording in lower-risk references while preserving tested behavior.

### Task 3: Verification

**Files:**
- Read: `/tmp/audit-prompt-plugin-eval-after-review-fixes.json`

- [x] **Step 1: Run unit tests**

Run `python3 -m unittest tests/test_prompt_cache_scripts.py`.

- [x] **Step 2: Run package validators**

Run `validate_skill_package.py` and `run_trigger_eval.py`.

- [x] **Step 3: Run Plugin Eval compare**

Run Plugin Eval analyze and compare against the original baseline. Confirm no failing checks return.

- [x] **Step 4: Run syntax, whitespace, and bytecode checks**

Run Python compile check, `git diff --check`, remove `__pycache__`, and verify no bytecode remains.
