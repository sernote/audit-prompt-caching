# Install Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make first-run skill installation look simple while preserving the full multi-file package.

**Architecture:** Add a repository-root `install.sh` that installs the `audit-prompt-caching/` skill directory into Codex by default and supports Claude or custom target directories. Keep README Quick Start focused on the one-command path, with manual clone/copy as fallback.

**Tech Stack:** Bash for installer, Python `unittest` for verification, existing stdlib-only skill scripts.

---

### Task 1: Lock Install Contract With Tests

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py`

- [x] **Step 1: Add failing installer tests**

Add tests that assert:
- `install.sh --source-dir <repo> --dir <tmp> --force` copies `SKILL.md`, `references/`, `scripts/`, and `evals/`.
- existing installs are not overwritten unless `--force` is passed.
- README first screen contains `curl -fsSL https://raw.githubusercontent.com/sernote/audit-prompt-caching/main/install.sh | bash`.

- [x] **Step 2: Run tests to verify RED**

Run: `python3 -m unittest tests.test_prompt_cache_scripts.PromptCacheScriptsTest`

Expected: failure because `install.sh` and README contract are not implemented yet.

### Task 2: Implement Installer and README

**Files:**
- Create: `install.sh`
- Modify: `README.md`

- [x] **Step 1: Implement `install.sh`**

Installer behavior:
- default target: `${CODEX_HOME:-$HOME/.codex}/skills/audit-prompt-caching`
- `--agent codex`, `--agent claude`, `--agent both`
- `--dir <path>` custom skill parent directory
- `--source-dir <path>` local repo source for tests/offline install
- `--repo <git-url>` and `--ref <git-ref>` for GitHub installs
- `--force` explicit overwrite
- `--help` usage text
- validate copied package contains `SKILL.md`, `references`, `scripts`, `evals`

- [x] **Step 2: Update README**

Move the one-command installer into Quick Start:

```bash
curl -fsSL https://raw.githubusercontent.com/sernote/audit-prompt-caching/main/install.sh | bash
```

Keep local script demo and manual install as secondary sections.

- [x] **Step 3: Run tests to verify GREEN**

Run: `python3 -m unittest tests/test_prompt_cache_scripts.py`

Expected: all tests pass.

### Task 3: Full Verification

**Files:**
- Read-only verification

- [x] **Step 1: Validate package and trigger evals**

Run:
```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

- [x] **Step 2: Check syntax and whitespace**

Run:
```bash
bash -n install.sh
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

Expected: shell and Python syntax pass, no whitespace errors, no bytecode output.
