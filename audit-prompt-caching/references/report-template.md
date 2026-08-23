# Prompt Cache Audit Report Template

Use for reusable handoff artifacts or when findings need more structure than chat.

## Output Contract Selector

- Quick triage: likely blocker, missing evidence, safe next command.
- Code audit: decision summary, findings, clean checks, verification.
- Provider migration risk: source/target semantics, layout, fields, routing, cost.
- Agent Loop Audit: stable tools, early messages, prefix hashes, cache fields, output tokens, compaction.
- Deployment Audit: version/commit/image, capability evidence, KV geometry,
  retention source/value, scheduler block size, hash compatibility, tier, and
  `cache_salt` isolation boundary.
- Not Worth Caching: why cache is not the lever and what evidence would reopen it.

## Header

```text
Provider/engine:
Mode:
Provider facts: verified on YYYY-MM-DD / unverified
Engine version/commit/image:
Capability evidence:
Attention/KV geometry:
Effective retention and source:
Scheduler block size:
Hash algorithm:
Seed compatibility status:
KV tier:
Isolation/cache_salt boundary:
Measurement change:
Prompt behavior change:
Provider/routing change:
Confidence:
Do first:
Do not do yet:
```

## Findings

```text
source | severity | provider/engine | issue | evidence | evidence_type | confidence | impact_condition | cache impact | safe_first_action | fix | validation | do_not_do_yet
```

## Cache Planes

Name every plane the audit actually covers. `render_audit_report.py --cache-plane` is repeatable and renders in this fixed order regardless of input order:

1. `gateway_response` — response reuse at a gateway or proxy.
2. `provider_prompt` — provider-managed prompt/prefix caching in provider usage telemetry.
3. `engine_kv` — attention KV reuse inside a self-hosted engine.
4. `external_kv` — KV blocks persisted or transferred outside the serving process.
5. `semantic_response` — similarity-based reuse of a prior response.

With no `--cache-plane`, the JSON list is empty and Markdown renders `Cache planes: unknown`. The renderer never infers a plane from a provider, model, or route name.

## Cache Clinic Summary

Report seven dimensions, each with exactly one status of `pass/warning/fail/unknown/not_applicable`:

| Dimension | CLI flag | Question |
|---|---|---|
| `applicability` | `--applicability` | Is caching the right lever for this route? |
| `evidence_quality` | `--evidence-quality` | Do conclusions rest on rendered payloads, telemetry, or hypotheses? |
| `prefix_stability` | `--prefix-stability` | Is the cacheable prefix byte/token stable? |
| `usage_accounting` | `--usage-accounting` | Is the cache-hit denominator trustworthy? |
| `routing_locality` | `--routing-locality` | Do repeated prefixes land on the same cache? |
| `economics` | `--economics` | Does the read/write price shape justify the change? |
| `isolation` | `--isolation` | Is cache-key and tenant scope safe? |

Every dimension defaults to `unknown`. Leave missing evidence visible as `unknown` instead of excluding it, and emit no aggregate score, grade, rank, or traffic-light roll-up across dimensions.

An `ambiguous` or `invalid` usage denominator can never be reported as `usage_accounting: pass`; the renderer rejects that combination, forces `warning`/`fail`, and marks the hit ratio non-decision-grade.

`routing_locality: pass` proves locality only; it cannot by itself prove routing-policy success or approve a routing-policy rollout. Routing Outcome Gate: references/mechanics.md.

## Evidence Needed Next

List rendered prompt pair, usage fields, route/model/provider, prefix/tool/schema hashes, TTFT/prefill, output tokens, and deployment/router/KV metrics needed to raise or lower severity. For a Deployment Audit, include image digest/version/commit, capability and resolved config evidence, concrete KV spec classes and attention geometry, effective retention plus source, scheduler block size, hash algorithm, redacted seed compatibility status, KV tier, and the `cache_salt` boundary fingerprint policy.

For provider aggregates, record each source separately from request-level usage
and route telemetry:

```text
evidence_source: provider_dashboard_aggregate | provider_usage_api_aggregate | request_level_provider_usage | gateway_or_replica_telemetry | rendered_prefix_evidence
provider: <provider>
time_window: <UTC interval>
granularity: <bucket or request>
filters: <grouping and filters>
displayed_metric: <metric>
displayed_value: <value>
evidence_definition_status: provider_documented | unknown
evidence_denominator_status: provider_documented | unknown
evidence_accounting_semantics: inclusive | additive | provider_defined | unknown
request_correlation: present | absent
route_correlation: present | absent
```

Label Dashboard aggregate and Usage API aggregate explicitly. Do not combine
their ratios or claim a causal finding until request-level usage and
route/replica correlation are present.

For the OpenAI Organization Usage API, `input_uncached_tokens` is uncached input
excluding cache-write tokens; it is neither cache reads nor writes. The OpenAI
prompt-caching guide documents a request-level read/write/neither partition.

For documented OpenAI Organization Usage API fields, set `evidence_definition_status:
provider_documented`, `evidence_denominator_status: unknown` unless the
provider documents the denominator, and
`evidence_accounting_semantics: provider_defined`. This is a documented mixed
decomposition, not permission to sum fields; preserve field-level
inclusive/decomposition semantics. For the OpenAI Organization Usage API, do not
add breakdowns onto inclusive `input_tokens` or manufacture a denominator/residual
from missing optional fields or mismatched bucket/group/filter scope. An
auditor-defined ratio is not
provider-documented or decision-grade aggregate evidence without scope proof.
Optional/missing fields: absent/unknown, never zero. Dashboard statuses remain
unknown unless the provider documents the relevant definition, denominator, and
accounting.

For an additive provider aggregate, such as an Anthropic or Bedrock reference,
use the documented component sum only when the provider reference documents
additive fields and the full total/denominator at matching bucket/group/filter
scopes. That documented sum is the provider-defined denominator: record
`evidence_accounting_semantics=additive` and
`evidence_denominator_status=provider_documented`. If the provider does not
document the full denominator or mismatched bucket/group/filter scopes occur,
keep the denominator unknown. Do not apply this additive rule to OpenAI's
inclusive `input_tokens`.

## Clean Checks

Record anti-patterns that were inspected and ruled out, for example volatile prefix data, tool/schema order, routing locality, TTL/cadence, output-token dominance, or privacy-driven isolation.
