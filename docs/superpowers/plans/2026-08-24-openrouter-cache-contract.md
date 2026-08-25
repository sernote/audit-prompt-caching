# OpenRouter Cache Contract Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` when executing this plan; keep each task small and reviewable.

**Goal:** Update the OpenRouter audit reference so it reflects the current documented cache contract, while keeping provider claims evidence-bound and making response-cache, sticky routing, and route attribution distinguishable during an audit.

**Architecture:** Keep `openrouter.md` as the main OpenRouter audit entry point. Move detailed response-cache mechanics into a selectively loaded `openrouter-response-cache.md` reference. Add deterministic content/trigger guards to the existing stdlib test suite; no analyzer or script behavior changes are planned because the gap is documentation and eval coverage.

**Tech Stack:** Markdown references/evals, Python stdlib `unittest`, existing package validator and trigger evaluator, plugin-eval 0.1.2, git/gh.

## Task 1: Add failing content and trigger tests (TDD RED)

**Files:**
- Modify `tests/test_prompt_cache_scripts.py`.
- Modify `audit-prompt-caching/evals/trigger_eval.json`.

Add deterministic tests that load the OpenRouter references and assert the required contract is present: 10-minute inactivity for sticky routing, documented non-chat grouping-only behavior, provider-specific marker/TTL distinctions, provider-fallback/order caveats, route/provider/model attribution and generation metadata, response-cache separation and HIT/MISS evidence, response-cache TTL/clear-header semantics, batch `:batch` handling, ZDR/retention caveats, and all required official links. Add two positive trigger cases for OpenRouter response-cache and sticky/session routing, keeping the trigger fixture within its existing size budget.

Run first:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py -k openrouter
```

Expected result: RED because the current reference lacks the new assertions. Capture the failing output before changing the references.

## Task 2: Plan review checkpoint

Review this plan with exactly Claude Opus at xhigh effort, using `CLAUDE_EFFORT=xhigh` and `scripts/consilium review ask -a claude-opus --progress compact`. The review prompt must include the exact files, the approved behavioral spec at `docs/superpowers/specs/2026-08-24-openrouter-cache-contract-design.md`, official OpenRouter URLs, RED command, and the requested decision `APPROVE` or `REQUEST_CHANGES`. Resolve Critical/Important findings and repeat the review until approved.

## Task 3: Implement the smallest documentation change (GREEN)

**Files:**
- Modify `audit-prompt-caching/references/openrouter.md`.
- Add `audit-prompt-caching/references/openrouter-response-cache.md`.

Rewrite the main reference to give an evidence-first diagnostic flow and link the detailed response-cache reference. Add only claims supported by the official sources listed in the spec. Preserve provider-specific adapters and explicitly separate provider prompt caching from OpenRouter gateway response caching. Include the current sticky inactivity window, non-chat grouping-only limitation, provider selection/fallback uncertainty, `prompt_cache_key`/session evidence, route metadata/generation lookup, batch warm-up semantics, ZDR/retention limits, and route/provider/model attribution boundaries.

Implement the detailed response-cache reference with request/response headers, enablement precedence, TTL parsing and remaining-TTL behavior, 200-only and concurrent-MISS caveats, key inputs and normalization, replay/usage/provider-attribution limitations, ZDR asymmetry, and metadata absence on HIT. Keep it a reference, not a claim that response-cache headers prove provider prompt-cache activity.

Run the focused tests and trigger evaluator:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py -k openrouter
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

Expected result: GREEN. If a test exposes an imprecise claim, revise the reference to the official source boundary rather than broadening the claim.

## Task 4: Focused review and plugin evaluation

Request a code review from exactly Claude Opus xhigh after the substantive reference/test changes. Include `git diff -- audit-prompt-caching/references tests/test_prompt_cache_scripts.py audit-prompt-caching/evals/trigger_eval.json`, the focused test output, and the spec. Fix all Critical/Important findings and repeat the scoped review if needed.

Then run the user-requested local skill evaluation:

```bash
plugin-eval start audit-prompt-caching --request "Evaluate this skill." --format markdown
plugin-eval analyze audit-prompt-caching --format markdown
```

Record the reports outside the repository unless a finding requires a tracked fix. If evaluation identifies a real regression in trigger surface or reference usability, fix it and rerun the relevant review/evals.

## Task 5: Final verification and budget normalization

Run fresh repository verification with bytecode disabled where applicable:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'), *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')
PY
git diff --check
```

Run the repository secret scan/CI-equivalent commands available in the checkout, inspect `git diff --stat`, `git diff`, and `git status --short`, and remove generated bytecode. Recalculate the plugin-eval token ceiling from the final bundled references using the repository's authoritative `ceil(len(text)/4)` convention; update the existing test constant only if the measured value requires it. Verify the final main/detail split remains within the approved combined/detail limits and that any overflow goes through the specified review gate.

## Task 6: Finish the development branch

Use `superpowers:finishing-a-development-branch` after all checks pass. Confirm the branch is based on `origin/main`, commit only intended files with a focused message, push `codex/openrouter-cache-contract`, and create a PR targeting `main` in `sernote/audit-prompt-caching`. Read back the PR URL/state and report any remaining caveat. If push or PR creation is blocked, stop after local verification and report the exact blocker.

## Measured budget record

The final repository measure after the source-mapping edits is 232,217 deferred-reference characters, or `ceil(len(text) / 4) = 58,055` tokens. The previous clean-base measure was 217,226 characters / 54,307 repository-estimated tokens with a 54,350 ceiling. The final plugin-eval 0.1.2 static report independently measured 58,066 tokens; it is recorded separately rather than substituted for the repository measure. The final test ceiling is 58,105 (`58,055 + 50` explicit slack), and `PLUGIN_EVAL_SKILL_TOKEN_BASELINE = 6341` is unchanged. The split references measure 13,135 and 4,848 Python characters respectively, 17,983 combined; the authoritative test uses Python `len()` rather than UTF-8 byte size.
