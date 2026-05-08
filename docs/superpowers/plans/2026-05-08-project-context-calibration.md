# Project Context Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `audit-prompt-caching` audits project-aware, language-matched, and transparent about script execution before recommending cache changes.

**Architecture:** Keep the skill package shape unchanged. Add behavior guidance to `SKILL.md`, lock it with focused unittest assertions, and add eval pressure cases for project-specific severity calibration and script transparency.

**Tech Stack:** Markdown skill docs, JSON eval fixtures, Python stdlib `unittest`.

---

### Task 1: Guardrail Tests

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Add skill guidance assertions**

Add a unittest that reads `audit-prompt-caching/SKILL.md` and asserts the new guardrails are present:

```python
def test_skill_requires_project_context_language_and_script_transparency(self):
    skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

    for required in [
        "Project Context Gate",
        "Language Match Rule",
        "Script Transparency Rule",
        "Applicability Before Severity",
        "review hot paths, repeat cadence, prompt families, and cache applicability",
        "explain what each bundled script reads, writes, and whether it uses network",
    ]:
        self.assertIn(required, skill)
```

- [x] **Step 2: Add eval coverage assertions**

Add a unittest that requires eval prompts/expected output to cover Russian review, project-specific severity calibration, daily jobs, and script transparency:

```python
def test_evals_cover_project_context_and_script_transparency_feedback(self):
    evals = json.loads(
        (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
    )
    combined = "\n".join(
        item["prompt"] + "\n" + item["expected_output"] for item in evals["evals"]
    )

    for required in [
        "Сделай ревью на русском",
        "7 prompt families",
        "once per day",
        "Script Transparency Rule",
        "do not mark prefix-cache findings high severity",
    ]:
        self.assertIn(required, combined)
```

- [x] **Step 3: Run targeted tests for RED**

Run:

```bash
python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_skill_requires_project_context_language_and_script_transparency \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_evals_cover_project_context_and_script_transparency_feedback
```

Expected: FAIL because `SKILL.md` and `evals.json` do not yet contain the new feedback guardrails.

### Task 2: Skill Behavior Guidance

**Files:**
- Modify: `audit-prompt-caching/SKILL.md`

- [x] **Step 1: Add Project Context Gate**

Insert a section before `Applicability Gate` requiring the agent to identify project-specific prompt/cache topology before assigning severity:

```markdown
## Project Context Gate

Before assigning severity or recommending project changes, review hot paths, repeat cadence, prompt families, and cache applicability. Identify which LLM routes are frequent enough, long enough, repeated enough, and stable enough for prefix caching to matter.
```

- [x] **Step 2: Add Applicability Before Severity**

Extend severity guidance so findings are not `high` without hot path, cadence, token, telemetry, or cost/TTFT evidence.

- [x] **Step 3: Add Language Match Rule**

Require responses to use the user's language while preserving provider/API field names.

- [x] **Step 4: Add Script Transparency Rule**

Document that bundled scripts require a short pre-run explanation covering read scope, write scope, network behavior, expected runtime, and why the script is needed.

- [x] **Step 5: Add concise review shape**

Require compact review outputs to separate `confirmed findings`, `hypotheses`, and `not applicable` findings.

### Task 3: Eval Pressure Cases

**Files:**
- Modify: `audit-prompt-caching/evals/evals.json`

- [x] **Step 1: Add Russian project-context calibration eval**

Add an eval where the user asks in Russian for review of a narrow project with 7 prompt families and daily jobs. Expected output must answer in Russian, inspect project specifics first, lower severity when caching is not applicable, and keep telemetry findings separate from hypotheses.

- [x] **Step 2: Add script transparency eval**

Add an eval where the user is concerned about a long-running audit script. Expected output must explain read/write/network/runtime scope before running scripts, prefer targeted scans first, and avoid secret-scanning behavior unless explicitly needed and explained.

### Task 4: Verification

**Files:**
- No source modifications expected.

- [x] **Step 1: Run targeted tests**

```bash
python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_skill_requires_project_context_language_and_script_transparency \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_evals_cover_project_context_and_script_transparency_feedback
```

- [x] **Step 2: Run full script test suite**

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

- [x] **Step 3: Validate package and trigger eval**

```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

- [x] **Step 4: Check Python syntax**

```bash
python3 - <<'PY'
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'), *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')
PY
```

- [x] **Step 5: Check whitespace and generated bytecode**

```bash
git diff --check
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```
