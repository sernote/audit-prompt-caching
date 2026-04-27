# Natural Trigger And Install Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the skill easier to adopt by documenting supported agent hosts and strengthening trigger evals for natural user phrasing without requiring `$audit-prompt-caching`.

**Architecture:** Keep this as a documentation/eval-only change. Add regression tests that fail if README compatibility/install docs disappear or if trigger evals rely only on explicit skill-name invocation.

**Tech Stack:** Markdown, JSON trigger evals, Python `unittest`.

---

## Task 1: Regression Tests

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] Add a test that README contains a `Works With` section for Claude Code, Cursor, Codex, and Continue.
- [x] Add a test that `trigger_eval.json` contains positive cases with no `$audit-prompt-caching`, no `audit-prompt-caching`, and no `Use $`.
- [x] Run targeted tests and confirm RED.

## Task 2: README Compatibility Docs

**Files:**
- Modify: `README.md`

- [x] Replace vague "Codex/agent skill" language with explicit portability wording.
- [x] Add `Works With` section with install/use steps for Codex, Claude Code, Cursor, and Continue.
- [x] Keep Codex as the primary supported target and mark non-Codex hosts as portable/manual skill-folder usage where appropriate.

## Task 3: Natural Trigger Eval Coverage

**Files:**
- Modify: `audit-prompt-caching/evals/trigger_eval.json`

- [x] Add natural positive trigger examples such as `cached_tokens у меня нулевой`, cache writes without reads, TTFT regression, dynamic tools, and vLLM routing.
- [x] Keep negative cases unchanged unless a new positive conflicts.

## Task 4: Verification And Install Sync

**Files:**
- Installed copy: `/Users/serno/.codex/skills/audit-prompt-caching`

- [x] Run unittest suite, package validator, trigger eval, syntax compile, whitespace check, and bytecode cleanup guard.
- [x] Sync the updated `audit-prompt-caching/` folder into `/Users/serno/.codex/skills/audit-prompt-caching`.
- [x] Validate the installed copy.
- [x] Commit and push the branch.
