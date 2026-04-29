# Project Audit Positioning Documentation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make it clear that `audit-prompt-caching` is primarily an agent skill for auditing project code and configuration, with logs and rendered requests used as supporting evidence.

**Architecture:** Keep the skill dependency-free and unchanged at runtime. Update user-facing documentation in `README.md` and agent-facing guidance in `audit-prompt-caching/SKILL.md`.

**Tech Stack:** Markdown documentation, existing Python package validators.

---

### Task 1: Clarify Project Audit Versus Evidence Artifacts

**Files:**
- Modify: `README.md`
- Modify: `audit-prompt-caching/SKILL.md`
- Modify: `audit-prompt-caching/agents/openai.yaml`

- [x] **Step 1: Add README guidance**

Add a "Primary Workflow: Audit A Project" section that says the main use case is an agent inspecting source code, prompt builders, SDK calls, tools/schemas, history management, routing, environment config, and deployment manifests.

- [x] **Step 2: Add skill guidance**

Add a "Default Project Audit Workflow" section to `SKILL.md` so agents start from repo code and configs when available. Reframe logs and rendered requests as evidence artifacts rather than the primary operating mode.

- [x] **Step 3: Address review packaging feedback**

Move the repo-audit prompt to the first README example and update `agents/openai.yaml` so skill discovery/default prompt also frames the skill as a project code/config audit.

- [x] **Step 4: Validate package**

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
git diff --check
```

Expected: all commands pass.
