# Prompt Cache Predeploy Checklist

Use for release, incident, deploy, or monitoring reviews.

## Blockers

- Volatile values before reusable content: time, request ID, user/tenant facts, git status, cwd, trace ID.
- Unsorted or dynamic tools, MCP schemas, structured-output schemas, or `response_format`.
- Prompt A/B flags or random few-shot examples before the stable prefix.
- Context compaction that rewrites the stable anchor.
- Provider wrapper or router changes without routed provider/model telemetry.
- vLLM/SGLang scale-out behind round robin without prefix-aware routing.
- `max_model_len` or KV settings changed without p99 input/KV pressure review.
- Cache controls, `cachePoint`, `prompt_cache_key`, TTL, retention, or salts changed without provider-doc checks.

## Minimum Release Evidence

- Rendered before/after prompt pair for each hot prompt family.
- Prefix/tool/schema hashes and first divergence location.
- Cache read/write fields by route/model/provider/region/replica.
- TTFT or prefill, final latency, output tokens, and tool timing.
- Prompt version, deploy SHA, SDK/provider version, router settings.
- Privacy or isolation decision for cache key/salt boundaries.

## Triage Order

1. Applicability Gate: hot, repeated, long stable prefix, safe reuse.
2. Prefix stability: static first, dynamic late, append-only history.
3. Provider correctness: fields, thresholds, breakpoint syntax, TTL/retention.
4. Routing/KV: sticky or prefix-aware route, KV capacity, eviction.
5. Economics: output share and write premium before claiming savings.

Do not block on generic cache advice when the route is cold, unique, short, output-bound, or intentionally isolated.
