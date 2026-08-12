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

### Source Path Handling

`source_fields` values are human-readable dot paths for reviewers, not machine-resolvable JSONPath expressions. Unknown wrapper envelopes can place usage under dynamic map keys, so a path may not be reusable as a selector and can itself carry request- or tenant-derived identifiers. Treat normalized telemetry as sensitive and apply the same handling policy as the rest of your token telemetry. Paths never contain leaf values or raw envelopes.

### Backward Compatibility

Event, summary, and report changes are additive: no existing key is renamed or removed, and strict JSON consumers must allow new event, summary, and report fields rather than failing closed. Only normalized events are versioned today; aggregate and report schema versioning remains deferred until a breaking migration needs it.

## Dashboard

Show cache read ratio, write/read ratio, cached-token share, output-token share, TTFT/prefill by route, final latency, route/provider/replica split, prompt/schema/tool hash changes, deploy correlation, and top prefix families by cost.

Normalize provider accounting before charting: OpenAI/Gemini cached-token fields are commonly inclusive in prompt input, while Bedrock cache read/write fields are additive. A dashboard that sums all fields indiscriminately will fabricate an apparent usage regression.

## Alerts And CI

- Alert on sudden cache-read drop, write-without-read spike, TTFT regression, prefix hash churn, tool/schema hash churn, or route/replica imbalance.
- CI smoke test: render representative requests and fail when the cacheable prefix changes unexpectedly.
- Store before/after prompt snapshots in a privacy-safe location or store hashes plus first divergence metadata when raw prompts are sensitive.
