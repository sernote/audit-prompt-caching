# Cache Audit Evidence Contract and Clinic Summary

**Status:** Implemented and verified
**Date:** 2026-08-13
**Target:** `audit-prompt-caching` skill package

## Context

The skill already detects prompt-cache applicability, prefix instability, provider usage accounting, routing-locality problems, and cache ROI. Its scripts normalize several provider usage envelopes and render a decision-first report. The missing piece is a stable evidence contract that tells a reviewer:

1. which raw fields produced each normalized value;
2. whether the cache-hit denominator is valid, ambiguous, or contradicted by the evidence;
3. which cache planes are actually in scope;
4. which audit dimensions are confirmed, degraded, failed, or still unknown.

Without that contract, correct provider-specific adapters can still produce an apparently precise percentage whose provenance or denominator is unclear. Reports also risk collapsing response caching, provider prompt caching, engine KV reuse, external KV storage, and semantic response caching into one generic "cache" diagnosis.

## Decision

Extend the existing usage normalizer and report renderer with additive, backward-compatible fields. Do not introduce a second normalizer, a runtime integration layer, or an aggregate health score.

The implementation follows a small hexagonal boundary:

```text
Provider usage envelope
        |
        v
Provider adapter / anti-corruption layer
        |
        v
Canonical normalized usage event
        |
        +--------------------+
        |                    |
        v                    v
JSONL output          Aggregate summary
                             |
                             v
                  Markdown / JSON report adapter
```

The provider adapters own raw-field extraction and accounting semantics. The canonical event owns provider-neutral evidence. The report renderer consumes canonical summaries and explicit operator inputs; it must not reinterpret raw provider envelopes.

## Goals

- Make normalized usage values traceable to raw JSON paths without retaining prompt content or copying raw records.
- Make denominator quality explicit and deterministic.
- Represent the cache stack as independently selectable planes.
- Add a no-score Cache Clinic Summary with per-dimension statuses.
- Preserve all existing CLI commands and existing JSON keys.
- Keep scripts Python-stdlib-only and usable on exported files without network access.
- Keep the trigger surface below plugin-eval's current excessive band and avoid increasing the invoked `SKILL.md` budget.

## Non-goals

- A new standalone usage-normalization script.
- Direct provider, gateway, Grafana, or tracing API integrations.
- Active timing, concurrency, warm-up, or security probes.
- Automatic cache warm-up or cache invalidation.
- Logging raw prompts, tool outputs, credentials, or complete provider envelopes.
- A universal claim about hidden provider-side serialization order.
- A numeric or letter-grade score that hides missing evidence.
- A large package or directory refactor.
- Moving or duplicating the repository test suite to satisfy a package-local static heuristic.
- Broad provider-reference pruning without provider-specific regression evidence.

## Architectural boundaries

### Core domain

`normalize_record` and the aggregate summary define the provider-neutral domain contract. Domain values use canonical names such as `input_tokens`, `cache_read_input_tokens`, and `cache_write_input_tokens`.

The domain layer may depend on Python standard-library types. It must not depend on the report renderer, filesystem layout beyond the CLI boundary, or provider SDKs.

### Provider adapters

Each existing usage adapter remains an anti-corruption layer around one provider usage surface. It owns:

- recognized envelope shapes;
- canonical-field extraction;
- raw JSON-path provenance;
- inclusive, additive, or ambiguous accounting semantics;
- provider-specific invariants that can invalidate a denominator.

Adding a provider surface should require a new adapter or a narrow extension to an existing adapter, not provider conditionals in the report renderer.

Adapters return canonical values and provenance through small, named extraction helpers. Denominator validation is a separate helper from field extraction and aggregation. New behavior must not be folded into the existing long provider-policy branches or add a new high-complexity function.

### Driving and presentation adapters

The existing command-line interfaces are the driving adapters. JSONL and JSON are machine-facing presentation adapters; Markdown is the human-facing presentation adapter.

`render_audit_report.py` may consume the analyzer's canonical summary helpers. `analyze_usage_logs.py` must never import the renderer. This dependency direction is the only structural constraint required for the current package size.

## Canonical normalized usage event

Every event emitted by `analyze_usage_logs.py --jsonl-normalized` adds the following fields:

```json
{
  "schema_version": 1,
  "source_fields": {
    "input_tokens": "usage.prompt_tokens",
    "cached_tokens": "usage.prompt_tokens_details.cached_tokens",
    "cache_read_input_tokens": null,
    "cache_creation_input_tokens": null,
    "cache_write_tokens": null,
    "output_tokens": "usage.completion_tokens"
  },
  "accounting_semantics": "inclusive",
  "denominator_status": "valid",
  "warnings": []
}
```

Rules:

- `schema_version` identifies this event contract, not the raw provider schema.
- `source_fields` contains exactly the six directly extracted canonical usage field names: `input_tokens`, `cached_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cache_write_tokens`, and `output_tokens`. Values are raw JSON paths selected by the adapter, or `null` when the canonical value is absent or derived without a direct source field.
- Paths describe field locations only. They must never contain field values.
- Existing canonical numeric fields remain unchanged.
- Existing `warnings` remains the canonical list of normalization warnings; do not add a duplicate `normalization_warnings` key.
- Existing `accounting_semantics` remains `inclusive`, `additive`, or `ambiguous`.

### Denominator status

`denominator_status` is one of:

- `valid`: accounting semantics are known and all adapter invariants required for the cache-hit denominator pass;
- `ambiguous`: accounting semantics remain unresolved, normally for an unknown wrapper without an explicit override;
- `invalid`: a known adapter invariant is contradicted, for example cached input exceeds an inclusive total-input field.

The aggregate summary uses the worst observed status:

```text
invalid > ambiguous > valid
```

An empty input set has `denominator_status: ambiguous`, because no measured denominator exists.

The analyzer may still emit token totals for ambiguous or invalid records. Any cache-hit percentage derived from them must be treated as non-decision-grade evidence by the renderer and documented as such.

### Backward compatibility

- No existing normalized event key is removed or renamed.
- No existing summary key is removed or renamed.
- The default text output keeps its current structure unless a new section is explicitly required below.
- Existing consumers that ignore unknown JSON keys continue to work.

## Cache-plane taxonomy

The report supports a repeatable `--cache-plane` argument with these canonical values, rendered in this order regardless of input order:

1. `gateway_response` — exact or policy-based response reuse at a gateway or proxy;
2. `provider_prompt` — provider-managed prompt or prefix caching reported by provider usage telemetry;
3. `engine_kv` — reuse of attention KV state inside a self-hosted inference engine;
4. `external_kv` — KV blocks persisted or transferred outside the serving process;
5. `semantic_response` — similarity-based retrieval of a prior response.

The JSON report adds `cache_planes` as a deduplicated list. If no plane is supplied, the list is empty and Markdown renders `Cache planes: unknown`. The renderer must not infer a plane from a model name, route, or usage field.

This taxonomy is a stack, not a mutually exclusive classification: one audit may involve several planes. Findings and recommendations should name the affected plane whenever the evidence supports it.

## Cache Clinic Summary

The renderer adds `clinic_summary` to JSON and a `## Cache Clinic Summary` section to Markdown. It contains these dimensions:

- `applicability`
- `evidence_quality`
- `prefix_stability`
- `usage_accounting`
- `routing_locality`
- `economics`
- `isolation`

Each dimension has exactly one status:

- `pass`
- `warning`
- `fail`
- `unknown`
- `not_applicable`

All statuses default to `unknown`. The CLI accepts one optional argument per dimension, for example `--usage-accounting warning`. Invalid values fail through `argparse` with exit status 2.

The report never computes an aggregate score, rank, percentage, or traffic-light summary from these dimensions. A missing dimension remains visible as `unknown` instead of being excluded from a denominator.

For this increment, statuses are explicit operator conclusions. Automatic derivation is allowed only where an unambiguous invariant already exists:

- aggregate denominator `invalid` may force `usage_accounting: fail`;
- aggregate denominator `ambiguous` may force `usage_accounting: warning` only when the operator left it `unknown`;
- no other dimension is inferred from filenames, provider names, or report prose.

Explicit operator input cannot mark an ambiguous or invalid denominator as `pass`; contradictory input is rejected with a clear error.

`evidence_quality` remains explicit even though it is not automatically derived in this increment. It captures whether conclusions rest on rendered payloads, normalized telemetry, routing evidence, or only hypotheses. Leaving it `unknown` is preferable to silently excluding evidence quality from the summary.

## Prefix-plan evidence boundary

The skill may recommend a stable-prefix plan only from an observed rendered request or a clearly identified request-construction boundary. The plan should separate:

- stable instructions and tool definitions;
- bounded semi-stable context;
- request-specific history and user input.

It must describe ordering as an observed application payload property. It must not claim a universal provider-internal serialization order without cited provider evidence.

## Warm-up, concurrency, and isolation boundary

Existing cold-fanout and routing-locality checks remain diagnostic decision guidance. This change may surface their conclusions in the Cache Clinic Summary, but it does not add an active load generator, timing probe, cache warmer, or security scanner.

Isolation reporting is passive and evidence-based. It may document cache-key scope, tenant boundaries, credential boundaries, and redaction risks visible in configuration or traces. Active cross-tenant probes require separate authorization and are out of scope.

## Failure behavior

- Malformed JSON and unsupported record shapes retain current fail-fast behavior.
- Unknown provider wrappers remain `accounting_semantics: ambiguous` unless the existing accounting override resolves them.
- Known impossible inclusive accounting, including aggregate cache benefit/write totals above the inclusive input total, produces `denominator_status: invalid` and a stable warning code.
- Missing optional source fields use `null`; they do not cause invented paths.
- Reports with no normalized usage evidence show an ambiguous denominator, derive `usage_accounting: warning`, leave the other unproven clinic dimensions `unknown`, and qualify the numeric ratio as non-decision-grade.

## Security and privacy

- Store field paths, never raw usage envelopes, prompt text, tool payloads, API keys, headers, or response bodies.
- Keep normalized JSONL safe for offline review under the same handling policy as existing token telemetry.
- Do not turn on active provider calls or cross-tenant probes.
- Recommendations involving shared-cache isolation must distinguish confirmed configuration from hypotheses.

## Skill instruction budget

The skill entrypoint uses progressive disclosure:

- shorten the frontmatter description to at most 139 estimated plugin-eval tokens while retaining positive and negative trigger boundaries;
- do not increase the estimated token count of `SKILL.md` from the 5,852-token baseline;
- consolidate repeated workflow wording instead of appending a second audit workflow;
- put detailed usage provenance and report-field contracts into existing `references/observability.md` and `references/report-template.md`;
- do not add a new reference file unless those existing boundaries are insufficient.

The package's deferred-token total is tracked as a no-regression signal, not optimized by deleting provider references or duplicating tests. Static plugin-eval results must be labeled as estimates until observed benchmark traces are supplied.

## Acceptance criteria

### Analyzer contract

- OpenAI inclusive usage emits exact source paths and a valid denominator when cached input does not exceed prompt input.
- Anthropic additive usage emits exact read/write/input paths and a valid denominator.
- Bedrock raw lower-camel and Pascal-case usage surfaces preserve their actual source paths.
- Gemini Interactions and Generate Content surfaces preserve their distinct source paths.
- An unknown wrapper without an override is ambiguous; the existing accounting override can make it valid.
- A known inclusive component or aggregate contradiction is invalid and carries a stable warning.
- Aggregate denominator status follows `invalid > ambiguous > valid` and is ambiguous for no records.

### Report contract

- JSON and Markdown render selected cache planes deterministically and do not infer missing planes.
- JSON and Markdown render all seven clinic dimensions, including unknown values.
- Invalid clinic statuses fail through the CLI.
- Invalid accounting cannot be rendered as a passing usage-accounting dimension.
- Neither JSON nor Markdown contains an aggregate clinic score.
- Existing decision summary, usage, ROI, and finding contracts remain present.

### Skill behavior

- The skill explicitly distinguishes the five cache planes and asks which are in scope.
- The skill uses provenance and denominator status before treating a hit rate as decision-grade.
- The skill produces per-dimension statuses without an aggregate score.
- The skill preserves the existing decision-first workflow and provider-specific references.
- The shortened trigger still activates on prompt-cache telemetry, prefix-stability, request-shape, routing-locality, and self-hosted KV-reuse problems, and still excludes generic prompt writing and unrelated performance work.

### Verification

- Script behavior changes are implemented test-first with a witnessed RED state.
- `python3 -m unittest tests/test_prompt_cache_scripts.py` passes.
- Package validation and trigger evaluation pass.
- All Python files compile.
- `git diff --check` passes and no generated bytecode remains.
- Before/after plugin-eval JSON reports are compared; static budget deltas are reported separately from behavioral correctness.

## Rollout and compatibility risks

The change is additive but can expose previously hidden ambiguity. A report that formerly showed a percentage may now label its denominator ambiguous or invalid. That is an intentional evidence-quality correction, not a telemetry regression.

The primary compatibility risk is downstream strict-schema validation of normalized JSONL. `schema_version` and additive keys make the contract explicit, but strict consumers still need to allow new fields. No migration is required for consumers that ignore unknown keys.

## Resolved review questions

1. Version normalized events now. Add independent aggregate or report versions only when those contracts need a breaking migration.
2. Reject `usage_accounting: pass` for both ambiguous and invalid denominators.
3. Keep all seven clinic dimensions. `evidence_quality` is explicit and defaults to `unknown` until stronger derivation rules exist.
