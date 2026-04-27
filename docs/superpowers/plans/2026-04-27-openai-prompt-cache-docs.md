# OpenAI Prompt Cache Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the `audit-prompt-caching` skill so its OpenAI prompt-cache reference and detection helpers reflect the current OpenAI prompt caching documentation.

**Architecture:** Keep OpenAI provider facts in `audit-prompt-caching/references/openai.md`, add eval coverage for advisory behavior, and extend `extract_llm_calls.py` so repositories using `prompt_cache_retention` are routed to the OpenAI reference. Preserve provider separation: Azure OpenAI remains governed by `azure-openai.md`.

**Tech Stack:** Markdown references, JSON eval prompts, Python stdlib `unittest`, dependency-free script edits.

---

### Task 1: Add Regression Coverage

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Add failing detection test**

Add a test that writes a JSON config containing only `prompt_cache_retention` and expects `extract_llm_calls.py` to classify it as an OpenAI provider signal.

- [x] **Step 2: Add failing reference-content test**

Add a test that asserts `references/openai.md` mentions current OpenAI docs concepts: prefix-hash routing, `prompt_cache_key`, approximate overflow threshold, `prompt_cache_retention`, `in_memory`, `"24h"`, `gpt-5.5`, Zero Data Retention, Regional Inference, TPM rate limits, and GPU-local storage.

- [x] **Step 3: Verify RED**

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: FAIL because `prompt_cache_retention` is not detected by `extract_llm_calls.py` and the OpenAI reference lacks the full current retention/privacy/rate-limit details.

### Task 2: Update OpenAI Detection And Reference

**Files:**
- Modify: `audit-prompt-caching/scripts/extract_llm_calls.py`
- Modify: `audit-prompt-caching/SKILL.md`
- Modify: `audit-prompt-caching/references/openai.md`

- [x] **Step 1: Implement detection**

Add `prompt_cache_retention` to the OpenAI provider pattern list in `extract_llm_calls.py` and to the OpenAI signal row in `SKILL.md`.

- [x] **Step 2: Update current OpenAI mechanics**

Update `openai.md` with current docs details:
- automatic caching for supported recent models
- exact prefix match and static-first layout
- cache routing by initial prefix hash
- `prompt_cache_key` combined with the prefix hash
- approximate overflow risk around 15 requests per minute for the same prefix/key combination
- cache miss writes the prefix afterward on the selected machine

- [x] **Step 3: Add retention and policy guidance**

Document `prompt_cache_retention` values:
- `in_memory`
- `"24h"`
- default behavior by model family as documented
- extended retention up to 24 hours
- same prompt-cache pricing for both policies
- no extra write fee for OpenAI prompt caching
- cached prompt tokens still count toward TPM limits

- [x] **Step 4: Add privacy and residency guidance**

Document:
- caches are not shared between organizations
- in-memory retention does not write data to disk
- extended retention may temporarily store KV tensors on GPU-local storage
- extended retention can be used with ZDR, while other ZDR restrictions still apply
- Data Residency requires Regional Inference for extended retention locality

- [x] **Step 5: Verify GREEN**

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: PASS.

### Task 3: Add Evals

**Files:**
- Modify: `audit-prompt-caching/evals/evals.json`
- Modify: `audit-prompt-caching/evals/trigger_eval.json`

- [x] **Step 1: Add advisory eval cases**

Add cases covering:
- too-broad or too-hot `prompt_cache_key` causing cache overflow/routing fragmentation
- `prompt_cache_retention` model support/defaults for `gpt-5.5` and future models
- ZDR/Data Residency implications for extended retention
- cached prompt tokens still counting toward TPM rate limits

- [x] **Step 2: Add trigger prompts**

Add positive trigger prompts for `prompt_cache_retention`, 24-hour retention, prefix/key overflow, ZDR/Data Residency, and TPM rate limits.

### Task 4: Verify Package

**Files:**
- Read only after implementation

- [x] **Step 1: Run unit tests**

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

- [x] **Step 2: Validate package and trigger evals**

```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

- [x] **Step 3: Check syntax**

```bash
python3 - <<'PY'
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'), *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')
PY
```

- [x] **Step 4: Check whitespace and bytecode**

```bash
git diff --check
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```
