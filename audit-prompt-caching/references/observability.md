# Prompt Cache Observability

Use for dashboards, alerts, traces, release guardrails, and CI smoke tests.

## Minimum Telemetry Contract

- Provider fields: `cached_tokens`, `cache_read_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cache_write_tokens`, or provider equivalents.
- Token totals: input, output, cache read, cache write/create, total effective denominator.
- Latency: TTFT or prefill, final latency, output/decode time, tool time.
- Dimensions: route, prompt family, prompt version, model, provider, region, replica, SDK version, deploy SHA.
- Hashes: `prefix_hash`, `first_256_token_hash`, tool-name hash, schema hash, stable document hash.
- Router/KV: actual routed provider/model/replica, KV pressure, eviction, prefix hit/query metrics.
- Continuity: keyed hash and kind of cache/session/conversation handle (for example `prompt_cache_key`, `session_id`, `previous_interaction_id`, or `previous_response_id`), never the raw value.

Do not log raw prompts. Use keyed hashes for tenant/user-derived or low-entropy prompt content.

### Self-hosted vLLM dimensions

For engine KV, external KV, and shared-tier audits, add these dimensions to
events, traces, or deployment evidence as applicable:

```text
engine_version
engine_commit
image_digest
retention_feature_present
retention_effective_value
attention_geometry
scheduler_block_size
hash_algorithm
seed_compatibility_status
pythonhashseed_present
pythonhashseed_match_status
kv_tier_type
cache_salt_boundary_fingerprint
```

Raw seed is prohibited. `seed_compatibility_status` and `pythonhashseed_match_status` use safe values
such as `matched`, `mismatched`, and `unknown`; `pythonhashseed_present` is a
boolean. For `xxhash`/`xxhash_cbor`, the effective seed
is a protected secret, so expose only compatibility status, boolean presence,
or a keyed fingerprint. A fixed cryptographic default after the verified
upstream change is public and is not a secret, but runtime/handshake logs still
need a separate redaction review.

`cache_salt_boundary_fingerprint` is a keyed, non-reversible fingerprint. It
must not contain raw salt, tenant ID, or user identity, and it is primarily a
trace/log dimension. Metrics require bounded cardinality; never create an
unbounded metric cardinality label per tenant or salt. The
fingerprint records the isolation boundary and does not replace `cache_salt`.

## Usage Evidence Contract

`analyze_usage_logs.py --jsonl-normalized` emits one canonical event per record. Four fields decide whether a cache ratio is decision-grade:

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

- `schema_version` versions this normalized event contract, not the provider's raw schema.
- `source_fields` names which raw field produced each canonical value, or `null` when the value is absent or derived.
- `accounting_semantics` is `inclusive`, `additive`, or `ambiguous`.
- `denominator_status` is `valid`, `ambiguous` (unresolved wrapper semantics, or no measured input), or `invalid` (an adapter invariant is contradicted, for example cached input above an inclusive input total). The aggregate takes the worst observed status: `invalid > ambiguous > valid`.
- `warnings` carries the stable normalization warning codes; it is the only warning list.

Only a `valid` denominator supports a savings or hit-rate claim. Report `ambiguous` and `invalid` ratios as non-decision-grade evidence and fix accounting first.

## Provider aggregate evidence boundary

Provider aggregates are evidence objects, not request events. Record the source,
scope, granularity, filters, and definition status before calculating a ratio:

```text
evidence_source: provider_dashboard_aggregate | provider_usage_api_aggregate | request_level_provider_usage | gateway_or_replica_telemetry | rendered_prefix_evidence
provider:
time_window:
granularity:
filters:
displayed_metric:
displayed_value:
evidence_definition_status: provider_documented | unknown
evidence_denominator_status: provider_documented | unknown
evidence_accounting_semantics: inclusive | additive | provider_defined | unknown
request_correlation: present | absent
route_correlation: present | absent
```

Treat the Prompt Caching dashboard as `provider_dashboard_aggregate`. Unless
the provider documents the formula and denominator, its evidence definition,
denominator, and accounting statuses remain `unknown`. It can confirm a trend
but cannot establish a request-level or route-level cause.

Treat the documented Organization Usage API completion fields as
`provider_usage_api_aggregate`. Preserve its time buckets, grouping, filters,
and bucket boundaries. Its `input_tokens` is inclusive of cached and
cache-write tokens. Treat `input_uncached_tokens` as excluding cached and
cache-write components only when the provider documents that additive identity;
otherwise keep the provider field and infer no residual. The documented mixed
decomposition uses provider-defined accounting, not permission to sum fields.
For documented Usage API fields set `evidence_definition_status=provider_documented`,
`evidence_denominator_status=unknown` for any derived ratio unless its
denominator is explicitly defined and recorded, and
`evidence_accounting_semantics=provider_defined`. Optional or missing fields
remain absent/unknown; never zero. These semantics do not make a dashboard
ratio equivalent to a Usage API ratio.

Keep dashboard aggregate, Usage API aggregate, request-level provider usage,
and gateway/replica telemetry in separate series. Do not compute a dashboard
denominator, convert an aggregate into request events, or make a causal claim
without request and route correlation. Request/prefix/tool/schema hashes and
raw provider usage remain required for causal findings.

### Source Path Handling

`source_fields` values are human-readable dot paths for reviewers, not machine-resolvable JSONPath expressions. Unknown wrapper envelopes can place usage under dynamic map keys, so a path may not be reusable as a selector and can itself carry request- or tenant-derived identifiers. Treat normalized telemetry as sensitive and apply the same handling policy as the rest of your token telemetry. Paths never contain leaf values or raw envelopes.

### Backward Compatibility

Event, summary, and report changes are additive: no existing key is renamed or removed, and strict JSON consumers must allow new event, summary, and report fields rather than failing closed. Only normalized events are versioned today; aggregate and report schema versioning remains deferred until a breaking migration needs it.

## Dashboard

Show cache read ratio, write/read ratio, cached-token share, output-token share, TTFT/prefill by route, final latency, route/provider/replica split, prompt/schema/tool hash changes, deploy correlation, and top prefix families by cost.

Normalize provider accounting before charting: OpenAI/Gemini cached-token fields are commonly inclusive in prompt input, while Bedrock cache read/write fields are additive. A dashboard that sums all fields indiscriminately will fabricate an apparent usage regression.

Before charting any aggregate, attach its `evidence_source`, provider, time
window, granularity, filters, `evidence_definition_status`,
`evidence_denominator_status`, and `evidence_accounting_semantics`; do not
merge dashboard and Usage API ratios silently.

## Alerts And CI

- Alert on sudden cache-read drop, write-without-read spike, TTFT regression, prefix hash churn, tool/schema hash churn, or route/replica imbalance.
- CI smoke test: render representative requests and fail when the cacheable prefix changes unexpectedly.
- Store before/after prompt snapshots in a privacy-safe location or store hashes plus first divergence metadata when raw prompts are sensitive.
