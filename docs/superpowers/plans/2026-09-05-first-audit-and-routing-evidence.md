# First audit and routing evidence implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. Complete each task with fresh verification and independent review.

**Goal:** Ship a runnable first audit and a bounded offline path from routing observations to an evidence-qualified report.

**Architecture:** Reuse the current stdlib helpers for the introductory example. Add a separate optional JSONL routing helper only for a documented evidence format; it must preserve missing data, request/attempt identity, and the distinction between a configuration signal and measured outcomes. The existing Routing Outcome Gate remains authoritative and unchanged.

**Tech stack:** Python 3.10+ stdlib, unittest, Markdown, JSON/JSONL, existing GitHub Actions.

**Base:** `b3ebd2512dacc6d791f87cd856d5bc915ecd7c69`, current public main on 5 September. Existing checkout changes are preserved in their original directory. Baseline: 169 unit tests pass.

## Task 1 — A first audit with a visible correction

Files: `README.md`, `examples/first-audit/README.md`, four small rendered prompt fixtures in that directory. Use text files to avoid implying that JSON transport serialization is the exact model-rendered prefix.

- [x] Create two synthetic before prompts with an early varying timestamp, and two after prompts with identical task instructions first and variable request context at the end. Keep the same information in before/after; do not drop runtime context to manufacture stability.
- [x] Run the existing helper for each pair:

```bash
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json examples/first-audit/before-a.txt examples/first-audit/before-b.txt
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json examples/first-audit/after-a.txt examples/first-audit/after-b.txt
```

Both commands should return exit 1 because the requests intentionally differ. After should have a longer `stable_prefix_bytes`, with the first difference in late dynamic context. State those exact observed values in the walkthrough. Raw text byte length is not token length, engine KV hit, provider billing, or proof of savings. This small example does not establish provider eligibility thresholds.

- [x] Rework the README first screen around the actual first result, the existing installation command and this example. Move the newsletter link below the first usable path. Replace the old hero finding that treats a cold first request as a defect. Keep relevant technical sections and supported installation options; do not broaden claims about agent compatibility.
- [x] Include the prompt a reader can use with the skill on their own project, the minimal artifacts to supply, and the legitimate outcome that no change is needed. Link the verified public site project page and public Telegram channel.
- [x] Check the example using the documented commands. No new script or implementation-mirroring tests are needed for these data/docs-only changes.
- [x] Independent spec review, then quality review; resolve findings before committing. Spec passed; quality approved after removing a repeated clone command and separating prefix divergence from replica-locality loss.

## Task 2 — Establish a small honest routing input contract

Files: `audit-prompt-caching/scripts/analyze_routing_logs.py`, `audit-prompt-caching/references/routing-evidence.md`, `fixtures/routing/`, `tests/test_routing_logs.py`. Decide exact raw-event mapping from the pinned vllm-router source before implementing. If native logs lack needed fields, document the custom export explicitly and report the gaps instead of advertising a native adapter.

- [x] Specify versioned JSONL records, joining separate decision and outcome records by request/attempt identity, with router/pool/model/worker identity and source provenance. Missing/unknown data remains null, never zero. The [v1 spec](../specs/2026-09-05-routing-evidence-export.md) preserves prediction-target identity separately from the selected worker, and defines client timing and terminal completion.
- [x] Start with deterministic observations: matching coverage; separate prediction and actual reuse; queue/TTFT/E2E coverage; request versus attempt counts; terminal outcomes and load scope. V1 retains predictions without comparison arithmetic and counts additional attempts without inferring retries. Its explicit limit assesses per-attempt client TTFT, not percentile SLOs, rollout approval or system health.
- [x] Write failing tests for ordinary joins, missing counterpart, conflicting/duplicate identity, multiple attempts, null versus zero, high reuse with excessive TTFT, no outcome data, malformed JSON/types/non-finite numbers, CLI JSON/exit consistency. Use real inputs and stdlib subprocess/imports.
- [x] Run the focused test file and verify expected failures before implementation. Initial RED: 34 test methods, 220 failing subcases because the analyzer was absent; CLI output was not the required JSON.
- [x] Implement only the documented schema and assertions. Do not parse arbitrary logs heuristically, infer per-request evidence from aggregate metrics, guess causal explanations, or add dependencies. Focused GREEN: 36 tests. A separate RED/GREEN correction keeps assessment unknown when a limit exists but no TTFT is supplied.
- [x] Add synthetic fixtures with declared provenance for normal, slow despite reuse, and insufficient-evidence paths. Document production export mapping and capabilities that remain unavailable.
- [x] Add one selective reference/script hook in the skill and CI discovery for the new tests. Preserve the existing evidence contract, provider behavior and practical context budget. Any budget adjustment must be measured and justified, not silently enlarged; exact values are below.
- [x] Independent spec review and code-quality review, then one blind task using the helper and relevant skill context. Spec: PASS; quality: APPROVE. A fresh agent audited a synthetic three-record export from a separate installed package without reading tests/specs/plans or an expected answer. It distinguished the other-worker character prediction from selected-worker token reuse, reported 1200 ms versus a 500 ms per-attempt target, preserved the second unknown outcome and rejected a production migration conclusion. This is one behavioral check, not a model benchmark or vllm-router performance evidence.

## Task 3 — Make the result reviewable

- [x] Add a short optional Markdown issue template for first-audit feedback: version/agent, task, completed finding/no-change/missing-evidence/failure, a minimal shareable example and optional discovery source. This is manual feedback, with no telemetry or automatic messages.
- [x] Run the full test suite, skill validator, trigger dataset checks, Python syntax and whitespace checks. Check both successful and invalid CLI paths and rerun the first-audit walkthrough. Fresh integrated result: 205 tests pass on Python 3.14.3; 31 trigger dataset entries validate (22 positive / 9 negative, not a behavioral pass rate). The routing helper parses with Python 3.10 grammar. A separate temporary installation runs all three fixtures and invalid-options JSON/exit 2. Prefix results remain 43 / 254 bytes with expected exit 1.
- [x] Verify all relative links and final diff. Preserve unrelated local changes, generated exports and private source material outside the public change. Package/backticked and new relative Markdown links resolve; staged whitespace is clean and generated bytecode is absent.
- [x] Commit the tested changes on the isolated `codex/` branch and prepare a draft pull request with the concrete example, supported input contract, limitations and test results. Implementation commit: `4cfa54dfdaade4db139671578c73799ad766f410`; [draft PR #21](https://github.com/sernote/audit-prompt-caching/pull/21) on `codex/cache-first-audit`. The PR exposes the current CI status. No merge or release was performed.
- [x] Record what remains for the broader program: native production trace integration where unavailable, site/editorial publication, external pilots and GPU comparisons. These require their own real outcomes and must not be marked achieved by unit tests.

## Measured package budget

The repository guard uses `ceil(characters / 4)`, a static estimate rather than
actual model token usage. The trigger description is unchanged at its 147
ceiling. SKILL.md is 25,573 characters / 6,394 estimated tokens, up 53 from
6,341 for the selective helper/reference hook and the narrower estimate wording.
The existing provider guidance and Routing Outcome Gate remain intact.

The deferred corpus is 237,707 characters / 59,427 estimated tokens. This
guard counts all deferred package files, including executable source: the new
script is 14,666 characters and its optional reference is 5,786 characters.
Those files are not unconditionally inserted into the skill context. The two
old budget checks failed on the measured growth before their ceilings were
updated to these measured values; no unrelated content was compressed to fit.

## Remaining adoption work

- Validate an exporter against one actual deployed router/worker/client trace.
  Preserve genuine attempt IDs and timing boundaries; missing native fields
  require instrumentation or an explicit unknown, not heuristic joins.
- Apply the skill to a real project task and verify one conclusion. Readers can
  share useful findings or friction through the optional feedback template;
  participant quotas are not a publication or release requirement.
- Publish the prepared editorial series and connect site articles, talks and
  project entry points to the runnable audit. This code change does not publish
  a site, Habr article or Telegram post.
- Evaluate routing policies, event recovery and offload on a controlled serving
  workload when real measurements are available. Synthetic fixtures do not rank
  vllm-router, Dynamo or a storage connector.
