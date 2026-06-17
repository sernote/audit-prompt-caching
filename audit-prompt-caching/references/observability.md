# Prompt Cache Observability

Use for dashboards, alerts, traces, release guardrails, and CI smoke tests.

## Minimum Telemetry Contract

- Provider fields: `cached_tokens`, `cache_read_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cache_write_tokens`, or provider equivalents.
- Token totals: input, output, cache read, cache write/create, total effective denominator.
- Latency: TTFT or prefill, final latency, output/decode time, tool time.
- Dimensions: route, prompt family, prompt version, model, provider, region, replica, SDK version, deploy SHA.
- Hashes: `prefix_hash`, `first_256_token_hash`, tool-name hash, schema hash, stable document hash.
- Router/KV: actual routed provider/model/replica, KV pressure, eviction, prefix hit/query metrics.

Do not log raw prompts. Use keyed hashes for tenant/user-derived or low-entropy prompt content.

## Dashboard

Show cache read ratio, write/read ratio, cached-token share, output-token share, TTFT/prefill by route, final latency, route/provider/replica split, prompt/schema/tool hash changes, deploy correlation, and top prefix families by cost.

## Alerts And CI

- Alert on sudden cache-read drop, write-without-read spike, TTFT regression, prefix hash churn, tool/schema hash churn, or route/replica imbalance.
- CI smoke test: render representative requests and fail when the cacheable prefix changes unexpectedly.
- Store before/after prompt snapshots in a privacy-safe location or store hashes plus first divergence metadata when raw prompts are sensitive.
