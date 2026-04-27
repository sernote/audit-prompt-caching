# Anthropic Prompt Cache Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the portable `audit-prompt-caching` skill so its Anthropic guidance reflects the current Claude prompt caching documentation.

**Architecture:** Keep provider-specific facts in `audit-prompt-caching/references/anthropic.md`, and use tests plus eval prompts to prevent regressions in key Anthropic semantics. Runtime helper scripts stay unchanged unless verification shows they mis-handle existing usage fields.

**Tech Stack:** Markdown skill references, JSON eval files, Python stdlib `unittest` package checks.

---

### Task 1: Add Anthropic Reference Regression Coverage

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Write the failing test**

Add a unittest method that reads `audit-prompt-caching/references/anthropic.md` and asserts it contains the new current-doc concepts:

```python
    def test_anthropic_reference_covers_current_prompt_cache_semantics(self):
        reference = (
            ROOT / "audit-prompt-caching" / "references" / "anthropic.md"
        ).read_text()

        for required in [
            "Automatic caching",
            "top-level",
            "Explicit cache breakpoints",
            "20-block lookback",
            "dynamic suffix",
            'ttl": "1h"',
            "longer TTL",
            "thinking blocks",
            "workspace-level isolation",
        ]:
            self.assertIn(required, reference)
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: FAIL because the existing Anthropic reference does not describe automatic caching, 20-block lookback, mixed TTL ordering, and workspace-level isolation.

### Task 2: Update Anthropic Provider Reference

**Files:**
- Modify: `audit-prompt-caching/references/anthropic.md`

- [x] **Step 1: Replace stale mechanics with current mechanics**

Update the reference to distinguish:
- top-level automatic `cache_control`
- explicit block-level breakpoints
- the `tools -> system -> messages` prefix hierarchy
- writes happening only at breakpoints
- cache reads walking backward over a 20-block lookback window

- [x] **Step 2: Add provider checks for current traps**

Add sections for:
- choosing automatic caching for append-only multi-turn conversations
- choosing explicit breakpoints for static prefix plus dynamic suffix
- adding multiple breakpoints when long conversations move more than 20 blocks from a prior write
- respecting the four-breakpoint limit
- placing longer TTL entries before shorter TTL entries
- monitoring `usage.cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` when present

- [x] **Step 3: Add eligibility, invalidation, and isolation notes**

Document:
- silent minimum-length failures where both read and creation fields are zero
- thinking blocks cannot be directly marked with `cache_control`
- empty text blocks and sub-content blocks are not direct cache targets
- tool/web-search/citations/speed/images/thinking changes can invalidate different cache levels
- workspace-level isolation for Claude API and Azure AI Foundry preview, with Bedrock and Vertex remaining different provider surfaces

- [x] **Step 4: Run test to verify it passes**

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: PASS.

### Task 3: Update Evals For New Anthropic Scenarios

**Files:**
- Modify: `audit-prompt-caching/evals/evals.json`
- Modify: `audit-prompt-caching/evals/trigger_eval.json`

- [x] **Step 1: Update existing Claude missing-cache eval**

Revise the expected output for the existing “forgot cache_control” eval so it mentions automatic top-level `cache_control` for multi-turn conversations and explicit block breakpoints for static prefixes.

- [x] **Step 2: Add eval cases**

Add cases that require the skill to discuss:
- automatic caching writing at a changing final user block and not producing reads
- a growing conversation exceeding the 20-block lookback window
- mixed 1-hour and 5-minute TTL ordering
- thinking-block cache behavior and invalidation with non-tool-result user content

- [x] **Step 3: Add trigger prompts**

Add positive trigger prompts for automatic caching, 20-block lookback, mixed TTL, and thinking blocks.

### Task 4: Verify Package

**Files:**
- Read only after implementation

- [x] **Step 1: Run unit tests**

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

- [x] **Step 2: Validate package**

```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

- [x] **Step 3: Check Python syntax**

```bash
python3 - <<'PY'
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'), *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')
PY
```

- [x] **Step 4: Check whitespace and generated bytecode**

```bash
git diff --check
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```

Expected: all commands pass and no generated bytecode remains.
