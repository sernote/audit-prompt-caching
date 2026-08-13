# Plugin-eval Review: Cache Audit Evidence Contract

**Date:** 2026-08-13
**Target revision:** draft `2026-08-13-cache-audit-report-contract-design.md`
**Evaluator:** plugin-eval 0.1.2, static analysis only

## Outcome

Proceed with the evidence-contract vertical slice, but constrain its instruction and code footprint. The functional proposal addresses gaps that plugin-eval does not score directly; plugin-eval mainly exposed existing budget and maintainability pressure that the implementation must not amplify.

Baseline result: **54/100, grade F, high risk**.

## Confirmed findings

| Finding | Evidence | Decision for this change |
|---|---|---|
| Trigger text is excessive | 170 estimated trigger tokens; plugin-eval heavy ceiling is 164 and moderate ceiling is 139 | Shorten frontmatter description to at most 139 estimated tokens while retaining positive and negative trigger boundaries |
| Invoked skill text is heavy | 5,852 estimated tokens in `SKILL.md` | Add no long workflow section; consolidate existing repeated guidance and route detailed contracts to existing references |
| Deferred package text is excessive | 37,740 estimated tokens across references, scripts, and evals | Do not add a new reference unless an existing reference cannot hold the contract; avoid broad provider-reference pruning in this feature because it could change provider behavior without dedicated verification |
| Existing Python complexity is high | maximum static cyclomatic complexity 99 and maximum function length 118 | Keep new normalization and report logic in small helpers; do not refactor unrelated GPT-5.6 lint logic inside this vertical slice |
| No observed usage supplied | static estimates only | Treat token conclusions as estimates; define a later benchmark path instead of claiming runtime savings |

## Tooling limitations and rejected score-chasing

Plugin-eval reported zero Python test files because the evaluation target is `audit-prompt-caching/`, while the repository intentionally keeps its unittest suite at `tests/test_prompt_cache_scripts.py`. Baseline verification ran 81 passing tests. Moving or duplicating that suite under the package solely to satisfy the evaluator would create two sources of truth and conflicts with the repository layout, so this warning is documented but not implemented.

The deferred-token score counts executable scripts, fixtures, evals, and provider references as one static budget. Those files are selectively loaded or executed by the skill. A broad deletion could improve the score while reducing provider correctness. This feature therefore applies a no-regression guardrail and leaves provider-reference consolidation to a separately benchmarked change.

The supplied `improve-skill` workflow points to `/Users/benlesh/.codex/skills/skill-creator/SKILL.md`, which is not available in this environment. The local `superpowers:writing-skills` instructions are used as the equivalent skill-authoring gate: concise trigger surface, progressive disclosure, pressure scenarios, and RED/GREEN verification.

## Specification changes required

1. Add explicit static-budget guardrails for the frontmatter and main `SKILL.md`.
2. Require small extraction/validation helpers so provenance work does not expand existing complex functions.
3. Keep the event schema version local to normalized events; defer independent aggregate/report versioning until a breaking change needs it.
4. Reject `usage_accounting: pass` for both ambiguous and invalid denominators.
5. Keep `evidence_quality` as an explicit dimension because it prevents a technically successful cache signal from hiding weak evidence; default it to `unknown`.
6. Add before/after plugin-eval comparison to verification, while stating that it remains static unless a benchmark supplies observed traces.

## Rewrite brief

Implement the vertical slice without creating a parallel normalization path. Provider adapters return canonical values plus exact source paths and accounting semantics. A small denominator validator assigns `valid`, `ambiguous`, or `invalid`. The report renderer accepts explicit cache planes and seven clinic statuses, derives only the usage-accounting guardrail from denominator evidence, and never computes an aggregate score.

Keep the skill entrypoint compact: shorten the trigger description, consolidate repeated diagnostic wording, and put detailed telemetry contracts into the existing observability/report references. Add pressure scenarios that prove the skill asks which cache plane is in scope, refuses decision-grade hit rates with ambiguous denominators, and leaves unknown clinic dimensions visible.

## Measurement plan

- Static: compare plugin-eval before/after JSON reports and inspect trigger, invocation, and deferred token deltas.
- Behavioral: run the package trigger eval and repository unit suite.
- Outcome: use pressure scenarios for cache-plane separation, denominator trust, and no-score reporting.
- Runtime follow-up: benchmark representative audit prompts with observed usage only in a separate authorized run; no live provider usage is available in this review.
