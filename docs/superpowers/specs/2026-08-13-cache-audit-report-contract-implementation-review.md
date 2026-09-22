# Cache Audit Evidence Contract: Implementation Review

**Date:** 2026-08-13
**Branch:** `codex/cache-audit-report-contract`
**Baseline:** `origin/main` at `6346ac9`

## Outcome

Implemented and verified. The vertical slice adds field-level usage provenance, denominator trust status, explicit cache-plane selection, and a seven-dimension Cache Clinic Summary without a roll-up score. Existing CLI arguments and existing JSON keys remain available.

## Delivered behavior

- Provider adapters emit exact `source_fields` paths for OpenAI, Anthropic, Bedrock, Gemini, and unknown wrappers.
- Normalized events carry `schema_version: 1`; summaries and events carry `denominator_status`.
- Inclusive accounting validates individual and aggregate cache benefit/write totals. Ambiguous or invalid evidence is never presented as a decision-grade hit ratio.
- `render_audit_report.py` accepts repeatable cache planes, all seven clinic statuses, and the existing inclusive/additive accounting override.
- Markdown qualifies hit ratio and both cost lines when usage evidence is ambiguous or invalid. Operator-supplied ROI remains visible but cannot silently launder the usage ratio.
- Skill instructions separate five cache planes, require observed-payload evidence for prefix plans, keep isolation review passive, and leave unproven clinic dimensions visible as `unknown`.

## Review loop

Claude Opus agents implemented the analyzer, renderer, and skill-contract increments through the local Consilium. Independent Claude reviews found and drove fixes for:

1. evidence-free records incorrectly marked valid;
2. unqualified invalid hit ratios and ROI short-circuiting;
3. missing renderer accounting override and unqualified cost-summary lines;
4. removed trigger anchors after instruction compression;
5. aggregate inclusive aliases producing a decision-grade ratio above 100%.

The final post-fix review confirmed the earlier integration gaps were closed. Its remaining blocking aggregate-invariant finding was fixed in `fa91919` and covered by analyzer and renderer tests.

## Plugin-eval comparison

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Score | 54 | 68 | +14 |
| Grade | F | D | +1 band |
| Trigger tokens | 170 | 135 | -35 |
| Invoke tokens | 5,852 | 5,850 | -2 |
| Deferred tokens | 37,740 | 41,238 | +3,498 |

One budget failure was removed and no new failure was introduced. The deferred increase is the cost of new production code, provider-pressure tests, and detailed existing-reference contracts. It is reported as a trade-off, not hidden.

The remaining static warnings are not release blockers for this vertical slice:

- package-local test discovery misses the repository's root `tests/` suite;
- complexity is dominated by existing script paths and is not a new provider-contract defect;
- no observed runtime usage benchmark was supplied, so token conclusions remain static estimates.

## Verification evidence

- Unit suite: 131 tests pass.
- Package validator: `status: ok`.
- Trigger eval inventory: 24 cases, 16 positive and 8 negative, `status: ok`.
- Official plugin-eval comparison: score +14, no new failures.
- Python syntax compilation: pass.
- `git diff --check`: pass.
- Generated `__pycache__` and `.pyc`: none remain after final cleanup.

## Deferred follow-ups

- Run an observed-usage benchmark on representative audit prompts before claiming runtime token or latency savings.
- Consider a future pre-computed summary input for the renderer to reduce analyzer/presentation coupling.
- Treat broader scanner redaction and malformed-input hardening as separate security work; neither is required to deliver this evidence-contract increment.
