# Plugin Eval Skill Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `audit-prompt-caching` using Plugin Eval findings, prioritizing budget failures while preserving prompt-cache audit behavior.

**Architecture:** Treat the Plugin Eval baseline as the RED signal: `trigger_cost_tokens`, `invoke_cost_tokens`, and `deferred_cost_tokens` are excessive. Keep `SKILL.md` as a compact router/workflow and rely on targeted references/scripts for details. Reduce deferred bundle size only where content is duplicated, overly verbose, or not needed for runtime package validation.

**Tech Stack:** Codex skill Markdown/YAML, Python stdlib scripts, JSON eval fixtures, Plugin Eval local Node CLI.

---

### Task 1: Establish Baseline

**Files:**
- Read: `audit-prompt-caching/SKILL.md`
- Read: `/tmp/audit-prompt-plugin-eval-before.json`
- Read: `/tmp/audit-prompt-skill-brief-before.json`

- [x] **Step 1: Pull latest remote changes**

Run: `git fetch origin && git pull --ff-only`

Expected: local `main` fast-forwards when remote is ahead.

- [x] **Step 2: Run Plugin Eval baseline**

Run:

```bash
node /Users/notevskii/.codex/plugins/cache/openai-curated-remote/plugin-eval/0.1.2/scripts/plugin-eval.js analyze audit-prompt-caching --brief-out /tmp/audit-prompt-skill-brief-before.json --format json --output /tmp/audit-prompt-plugin-eval-before.json
```

Expected: report identifies the current required fixes before implementation.

### Task 2: Compact Invocation Surface

**Files:**
- Modify: `audit-prompt-caching/SKILL.md`

- [x] **Step 1: Shorten frontmatter description**

Keep high-signal triggers: prompt/prefix cache misses, provider cache telemetry, request-shape drift, agent tool/history instability, and self-hosted KV/routing issues. Preserve local test substrings: `Use whenever the user mentions`, `LLM cost or speed regressed`, `repeated long prompts`, and `speeding up agents`.

- [x] **Step 2: Rewrite body as compact router**

Keep these sections because tests and behavior rely on them:

```text
When to use
When not to use
Project Context Gate
Applicability Gate
Language Match Rule
Agent-First Output Contracts
Explicit Review Default
Use-Case Map
Scenario References
Bundled Scripts
Script Transparency Rule
Freshness Gate
Provider Detection
Audit Flow
Audit Playbooks
Applicability Before Severity
Report Format
Agent-First Quality Bar
Verification
Advisory Questions
```

Collapse verbose examples and anti-pattern bodies into pointers to `references/rules.json`, `references/use-cases.md`, provider references, and scripts.

- [x] **Step 3: Verify compact SKILL still contains tested markers**

Run: `python3 -m unittest tests/test_prompt_cache_scripts.py`

Expected: existing SKILL content tests still pass or fail only on intentional markers that need equivalent compact wording.

### Task 3: Reduce Deferred Budget

**Files:**
- Modify if needed: `audit-prompt-caching/evals/evals.json`
- Modify if needed: `audit-prompt-caching/evals/trigger_eval.json`
- Modify if needed: `audit-prompt-caching/references/*.md`

- [x] **Step 1: Identify largest deferred components**

Run:

```bash
jq '.budgets.deferred_cost_tokens.components[] | {label, tokens}' /tmp/audit-prompt-plugin-eval-before.json
```

Expected: eval files and the longest provider/scenario references account for most deferred cost.

- [x] **Step 2: Trim only redundant text**

Keep provider-specific behavior and local test markers. Remove repeated scenario prose, oversized expected-output text, and duplicated reference explanations where another reference already covers the same procedure.

- [x] **Step 3: Validate eval JSON and trigger coverage**

Run:

```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

Expected: both return exit 0.

### Task 4: Compare Evaluation And Verify

**Files:**
- Read: `/tmp/audit-prompt-plugin-eval-after.json`
- Read: `/tmp/audit-prompt-plugin-eval-compare.json`

- [x] **Step 1: Re-run Plugin Eval after edits**

Run:

```bash
node /Users/notevskii/.codex/plugins/cache/openai-curated-remote/plugin-eval/0.1.2/scripts/plugin-eval.js analyze audit-prompt-caching --brief-out /tmp/audit-prompt-skill-brief-after.json --format json --output /tmp/audit-prompt-plugin-eval-after.json
```

Expected: budget failures improve or disappear, and score increases.

- [x] **Step 2: Compare before and after**

Run:

```bash
node /Users/notevskii/.codex/plugins/cache/openai-curated-remote/plugin-eval/0.1.2/scripts/plugin-eval.js compare /tmp/audit-prompt-plugin-eval-before.json /tmp/audit-prompt-plugin-eval-after.json --format json --output /tmp/audit-prompt-plugin-eval-compare.json
```

Expected: comparison shows reduced trigger/invoke/deferred token costs.

- [x] **Step 3: Run repository verification**

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

Expected: tests and validators pass, diff whitespace is clean, and no generated bytecode remains.
