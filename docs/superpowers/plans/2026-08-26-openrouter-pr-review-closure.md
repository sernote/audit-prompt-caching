# OpenRouter PR Review Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three current P2 review findings on PR #20 without changing provider claims or production behavior.

**Architecture:** Keep the OpenRouter locator passive and path-only. The shell snippet derives positive inventory globs from the existing `SAFE_GLOBS`, reuses the consumed `OR_LIST` temporary file, accumulates every incomplete-search/precondition state, and exits `2` through its existing `EXIT` trap. The Python extractor always emits its JSON result and exits `2` when skipped symlinks or read errors make coverage incomplete.

**Tech Stack:** Bash 3-compatible shell snippets, Python 3 stdlib, `unittest`, `git`, `gh`, agents-consilium, plugin-eval 0.1.2.

**Spec:** `docs/superpowers/specs/2026-08-24-openrouter-cache-contract-design.md`

## Global Constraints

- Work only in the existing linked worktree on `codex/openrouter-cache-contract`; do not touch `/Users/notevskii/develop/audit-prompt` or the detached dirty checkout.
- Keep scripts dependency-free and Python stdlib-only.
- Preserve JSON output on incomplete extractor coverage; use exit status `2` to distinguish unresolved coverage from a clean scan.
- List excluded credential/config paths only; never print their contents or secret values.
- Preserve partial discovery/control lists and all existing redaction, NUL-safety, legacy-Bash, trap-isolation, and vendor-skip behavior.
- Do not change OpenRouter provider facts, routing recommendations, production settings, or the response-cache contract.
- Budget baseline at `59ce9a4`: `openrouter.md = 22,989`, detail `= 4,008`, combined `= 26,997`, deferred package `= 242,320` characters / repository estimate `60,580` tokens, ceiling `60,630`.
- Reviewed follow-up limits: main `<=24,500`, detail `<=5,000`, combined `<=28,500`; set `PLUGIN_EVAL_DEFERRED_TOKEN_CEILING` to the measured final `ceil(chars / 4) + 50`, with final deferred package `<=245,000` characters and ceiling `<=61,300` in this change.
- The deferred package ceiling includes `extract_llm_calls.py`; moving text between main/detail cannot relieve it. Record final before/after characters, repository-estimated tokens, 50-token slack, plugin-eval's independent tokenizer result, and that result's distance above prior `heavyMax = 26,574` in this plan and the existing design before push.

---

### Task 1: Add regression tests and prove RED

**Files:**
- Modify: `tests/test_prompt_cache_scripts.py:2484-2538`
- Modify: `tests/test_prompt_cache_scripts.py:5473-5831`

**Interfaces:**
- Consumes: `run_script("extract_llm_calls.py", root)`, the two Bash fences from `references/openrouter.md`, and the existing deterministic `rg` stub.
- Produces: process-level assertions for incomplete extractor coverage, aggregate search failures, and path-only excluded-config inventory.

- [x] **Step 1: Add a process-level extractor regression**

Add a test named `test_openrouter_extractor_returns_nonzero_for_incomplete_coverage`. Create a readable source plus a symlink under a temporary auditee root, invoke `run_script`, parse stdout as JSON, and assert:

```python
self.assertEqual(result.returncode, 2, result.stderr)
self.assertEqual(output["symlinks_skipped"], 1)
self.assertEqual(output["read_errors"], 0)
```

This test catches a `main()` implementation that reports incomplete coverage but still returns `0`.

Add a second branch that calls the real `main()` with `Path.read_text` forced to raise `OSError`, captures stdout, and asserts status `2`, valid JSON, and `read_errors == 1`. This catches a fix wired only to `symlinks_skipped`.

Add an empty readable repository branch that runs the CLI and asserts status `0`, valid JSON, and `files_scanned == 0`; this locks the documented status-0-but-evidence-unresolved asymmetry.

- [x] **Step 2: Strengthen the shell partial-error regression**

In `test_openrouter_discovery_reports_partial_search_failures`, retain the existing output assertions and add:

```python
self.assertEqual(result.returncode, 2, result.stderr)
```

Use deterministic stub modes to prove all of these statuses: discovery/control/inventory/body-key/credential-precheck `rg >=2`, the testable control/inventory/pre-check `cd` guards, and body-key `mktemp` failure each produce final status `2`; every search returning no-match `1` produces final status `0`. Test the `cd` guards with controlled root removal: delete the auditee root during the preceding OR/control search, let the absolute-path body-key stub recreate it, and then exercise the downstream pre-check separately by deleting during body-key search. Test the body-list allocation branch with a PATH-prepended counting `mktemp` shim that succeeds for `OR_LIST` and `CONTROL_LIST`, fails on the third invocation, and records that the body-list path — rather than initial allocation — was reached. The discovery `cd || exit 2` guard is fail-closed by construction but not claimed as a deterministic raced-path test.

- [x] **Step 3: Add excluded path-only inventory fixtures**

Extend `test_openrouter_discovery_snippet_runs_on_legacy_bash` with `.env.cache`, `routing.tfvars`, and `openrouter-credentials.yaml` files containing only `cache_enabled: true`. Extend the local `rg` stub to support `rg --files` and to honor both the positive inventory globs and `SKIP_GLOBS`; it must not list every file. Assert each sensitive path appears with an `EXCLUDED ` prefix while `cache_enabled: true` never appears in stdout, and assert an ordinary `openrouter.ts` source is absent from the `EXCLUDED` section. Assert the existing newline-bearing credential path is shell-quoted in the same inventory, and assert an empty inventory prints an explicit `unresolved, not evidence that controls are absent` line.

Execute the second mechanics fence by passing its text on stdin to `/bin/bash --norc -i` (for example, `subprocess.run(["/bin/bash", "--norc", "-i"], input=fence_text, ...)`), not as an argv script file or only with `-c`. Bash 3 leaves `histexpand` off for an argv script even with `-i`, while `-i -c` reports it on but does not process the command string through interactive history expansion; either delivery would make this regression vacuous. Set `HISTFILE=/dev/null` and `BASH_SILENCE_DEPRECATION_WARNING=1` in the shared harness environment, and include `bash --version` in failure diagnostics. Assert stderr contains no `event not found`, the inventory is bounded, and the ordinary source remains absent from `EXCLUDED`.

In the same test, run a minimal positive-control fence containing the old `${g#!}` expression through the identical stdin-interactive harness and assert stderr does produce `event not found`. This proves the harness has history expansion enabled and will catch a regression in the documented interactive-paste workflow.

Add `test_openrouter_excluded_inventory_runs_with_real_rg`, guarded by `@unittest.skipUnless(shutil.which("rg"), "requires real ripgrep")`. Run the real snippet on hidden, Terraform, credential-named, `.git`, `node_modules`, and vendored fixtures; assert intended paths are included, skipped-tree paths are excluded, no values are printed, and `rg --version` is recorded in the test failure message.

- [x] **Step 4: Run focused tests and capture the expected RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py -k openrouter
```

Expected: failures showing extractor `returncode 0 != 2`, mechanics-snippet `returncode 0 != 2`, and missing `EXCLUDED` path output. The existing size-cap tests remain green during RED because no implementation text exists yet. Do not edit implementation files until these failures are observed.

### Task 2: Implement minimal incomplete-coverage signaling

**Files:**
- Modify: `audit-prompt-caching/scripts/extract_llm_calls.py:325-333`
- Modify: `audit-prompt-caching/references/openrouter.md:25-67`
- Modify: `README.md:181-209`
- Modify: `tests/test_prompt_cache_scripts.py:32-38,5467-5471`
- Modify: `docs/superpowers/specs/2026-08-24-openrouter-cache-contract-design.md:162-181`
- Modify: `docs/superpowers/plans/2026-08-26-openrouter-pr-review-closure.md`
- Test: `tests/test_prompt_cache_scripts.py`

**Interfaces:**
- Consumes: `find_matches(root) -> dict` with integer `symlinks_skipped` and `read_errors` fields.
- Produces: JSON on stdout plus process status `0` for complete scans and `2` for incomplete scans; the shell snippet follows the same `0`/`2` contract.

- [x] **Step 1: Return `2` from the extractor only for incomplete traversal**

Store `find_matches(root)` in `result`, print it unchanged, and return `2` when either counter is nonzero:

```python
result = find_matches(root)
print(json.dumps(result, ensure_ascii=False, indent=2))
return 2 if result["symlinks_skipped"] or result["read_errors"] else 0
```

Do not make an empty but complete repository fatal. Extend the extractor module docstring, argparse description shown by `--help`, shared README contract, and adjacent OpenRouter prose to state: status `2` with JSON means incomplete traversal, argparse/preflight status `2` without JSON means no result, and status `0` means only that traversal had no symlink/read errors — it does not turn empty results or `files_scanned: 0` into resolved evidence. README is outside the deferred package budget and makes the provider-agnostic CLI change discoverable outside OpenRouter audits.

- [x] **Step 2: Add path-only inventory for excluded names**

Derive positive, case-insensitive filename globs from the suffix of `SAFE_GLOBS` after `${#SKIP_GLOBS[@]}` so a later exclusion cannot silently lose inventory parity:

```bash
EXCLUDED_GLOBS=()
for g in "${SAFE_GLOBS[@]:${#SKIP_GLOBS[@]}}"; do
  case "$g" in --iglob) ;; '!'*) EXCLUDED_GLOBS+=(--iglob "${g:1}");; esac
done
```

Reuse the already-created and consumed `OR_LIST` file for `rg --files -0 --hidden --no-ignore "${EXCLUDED_GLOBS[@]}" "${SKIP_GLOBS[@]}" .`, parse NUL-delimited paths, and print only shell-quoted absolute paths under:

```text
== excluded config/credential paths: approval required before opening ==
EXCLUDED /srv/app/.env.cache
```

Treat `rg --files` status `2` or higher as unresolved coverage; status `1` is a clean no-match.

Before running `rg --files`, require `EXCLUDED_GLOBS` to be non-empty. If derivation yields zero globs, print `excluded-path inventory unresolved: derived glob set is empty`, set `SEARCH_STATUS=2`, and skip the inventory command so it cannot degenerate into a whole-tree listing. For a non-empty glob set with no matches, print `no excluded config/credential paths discovered: inventory unresolved, not evidence that controls are absent`. A non-empty banner must say that controls remain unresolved until approved inspection. Do not add a fifth temp file or alter the existing trap contract.

- [x] **Step 3: Preserve aggregate search failure through cleanup**

Initialize `SEARCH_STATUS=0`. Guard each search subshell with `cd -- "$AUDITEE_REPO" || exit 2` so a vanished/unreadable root cannot become no-match status `1`. Set status `2` after any discovery, control, excluded-path inventory, body-key, or credential pre-check command returns `2` or higher, and directly in the body-key `mktemp` failure branch. The initial list and pre-check `mktemp` failures already exit `2`; preserve them. Keep existing partial output, rely on the existing `EXIT` trap for cleanup, and finish the subshell with:

```bash
exit "$SEARCH_STATUS"
```

- [x] **Step 4: Measure and record the reviewed budget exception**

Measure `len(openrouter.md)`, detail, combined, and every non-hidden deferred package file with the same Python logic as the test. Update the main/combined assertions within `24,500`/`28,500`, update `PLUGIN_EVAL_DEFERRED_TOKEN_CEILING` to exactly `ceil(final_chars / 4) + 50`, and append the measured before/after record to this plan. Add a new amendment to `docs/superpowers/specs/2026-08-24-openrouter-cache-contract-design.md` that explicitly supersedes every earlier `23,000`/`27,000` current-exception statement and updates criterion 10 at line 140 to the measured final caps and permitted-file list. The amended list must include `README.md`, state that README is outside the deferred package budget, and justify it as the provider-agnostic `0`/`2` CLI contract surface. Record plugin-eval's independent token result and its distance above `heavyMax = 26,574`; do not compute that distance from repository `ceil(chars / 4)`. If main exceeds `24,500`, combined exceeds `28,500`, or deferred chars exceed `245,000`, stop and return to plan review instead of deleting safety prose.

- [x] **Step 5: Run the full suite and confirm GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: all repository tests pass with no warnings or errors, including extractor regressions and the deferred-reference ceiling.

### Task 3: Independent Claude Opus xhigh review

**Files:**
- Review: `audit-prompt-caching/references/openrouter.md`
- Review: `audit-prompt-caching/scripts/extract_llm_calls.py`
- Review: `README.md`
- Review: `tests/test_prompt_cache_scripts.py`
- Review: `docs/superpowers/plans/2026-08-26-openrouter-pr-review-closure.md`
- Review: `docs/superpowers/specs/2026-08-24-openrouter-cache-contract-design.md`

**Interfaces:**
- Consumes: working-tree diff, RED/GREEN output, three GitHub review URLs, existing OpenRouter spec.
- Produces: `APPROVE` or actionable Critical/Important findings.

- [x] **Step 1: Run the required review**

Use exactly the `claude-opus` profile with `CLAUDE_EFFORT=xhigh` and `scripts/consilium review ask -a claude-opus --progress compact`. Include the exact files, current PR HEAD, review claims/URLs, and request a decision on correctness, redaction safety, Bash 3 portability, exit semantics, and test adequacy.

- [x] **Step 2: Resolve findings**

For each valid Critical or Important finding, add a failing regression, observe RED, make the minimum fix, and rerun the full suite. Repeat the same Opus review until approved or report the exact external blocker.

### Task 4: Fresh verification and package evaluation

**Files:**
- Verify: all intentional branch changes.

**Interfaces:**
- Consumes: reviewed implementation at the final working-tree state.
- Produces: fresh local verification, package-evaluation report, and a clean intentional diff.

- [x] **Step 1: Run repository verification**

Run:

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

- [x] **Step 2: Run safety and repository-state checks**

Run this list-only high-signal scan so values are never printed:

```bash
command -v rg
rg -l -i --hidden --no-ignore --glob '!.git/**' --glob '!**/__pycache__/**' -- '(api[_-]?key|authorization|bearer|password|passwd|client[_-]?secret|BEGIN [A-Z ]*PRIVATE KEY|github_pat_|xox[baprs]-|AKIA[0-9A-Z]{16})' audit-prompt-caching docs tests
```

Classify every returned path as an intentional redacted fixture/documentation example or a blocker. Verify no `__pycache__`/`.pyc` remains, inspect `git diff --stat`, full `git diff`, and `git status --short`, and confirm only the plan, design, README, test, extractor, and OpenRouter reference changed.

- [x] **Step 3: Re-run evaluate-skill**

Run:

```bash
plugin-eval start audit-prompt-caching --request "Evaluate this skill." --format markdown
plugin-eval analyze audit-prompt-caching --format markdown
```

Record the score and distinguish package-wide findings from regressions introduced by this fix.

**Execution evidence (2026-08-26):** The pre-implementation focused run failed with the intended extractor status, shell status, and missing-inventory regressions (12 failures and two missing-section errors). After implementation, the focused 9-test run and full 182-test suite passed. Claude Opus xhigh found one Important vacuous read-error branch; a symlink-only predicate mutant then produced RED (`status 0 != 2`), the symlink-free regression passed after restoration, and the repeat review returned `APPROVE`. Final size measurements are main 24,349, detail 4,008, combined 28,357, deferred package 244,295 characters, repository estimate 61,074 tokens, and ceiling 61,124. Plugin-eval 0.1.2 independently reports 61,086 deferred tokens, 34,512 above `heavyMax = 26,574`, and score 63/100. The score debt is package-wide (static budget plus existing complexity/test-discovery heuristics); this focused review closure neither claims nor attempts a package-wide score improvement.

### Task 5: Publish fixes and close review threads

**Files:**
- Commit: only the follow-up plan, superseding design amendment, README contract, tests, extractor, and OpenRouter reference changes.

**Interfaces:**
- Consumes: verified commit SHA and GitHub comment/thread IDs `3855318710`, `3855376380`, `3855376388`.
- Produces: updated PR #20 with replies in the original inline threads and all three threads resolved after readback.

- [ ] **Step 1: Commit and push**

Create one focused commit, push `codex/openrouter-cache-contract` without force, and verify remote HEAD equals local HEAD.

- [ ] **Step 2: Reply in each original thread**

After verification, use the three exact endpoints below. The bodies name only behavior proven by the final tests and pushed SHA:

```bash
FIX_SHA=$(git rev-parse --short HEAD)
gh api repos/sernote/audit-prompt-caching/pulls/20/comments/3855318710/replies -f body="Fixed in ${FIX_SHA}: discovery/control/inventory/body/precheck rg errors, body-list allocation failure, and the deterministically exercised control/inventory/pre-check cd guards preserve unresolved diagnostics and return exit 2 through trap cleanup; the discovery cd guard is fail-closed by construction. Full suite passes."
gh api repos/sernote/audit-prompt-caching/pulls/20/comments/3855376380/replies -f body="Fixed in ${FIX_SHA}: the extractor still prints JSON but returns exit 2 for both skipped symlinks and read errors; the symlink path is subprocess-tested, the read-error branch is exercised in-process, and the exit-0 empty-scan asymmetry is documented in --help and README."
gh api repos/sernote/audit-prompt-caching/pulls/20/comments/3855376388/replies -f body="Fixed in ${FIX_SHA}: positive inventory globs are derived from SAFE_GLOBS and list excluded config/credential paths without reading values; deterministic and real-rg regressions cover hidden, tfvars, credential, newline, and skipped-tree paths."
```

- [ ] **Step 3: Resolve and read back**

Resolve thread IDs `PRRT_kwDOSK9Kac6cKi-7`, `PRRT_kwDOSK9Kac6cKsMY`, and `PRRT_kwDOSK9Kac6cKsMb` only after their fixes are pushed. Re-fetch GraphQL review threads, PR checks, merge state, and head SHA. If new comments appear, treat them as new review work rather than declaring closure.
