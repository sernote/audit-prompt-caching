# Prompt Cache Predeploy Checklist

Use for release, incident, deploy, or monitoring reviews.

## Blockers

- Volatile values before reusable content: time, request ID, user/tenant facts, git status, cwd, trace ID.
- Unsorted or dynamic tools, MCP schemas, structured-output schemas, or `response_format`.
- Prompt A/B flags or random few-shot examples before the stable prefix.
- Context compaction that rewrites the stable anchor.
- Provider wrapper or router changes without routed provider/model telemetry.
- Any vLLM/SGLang routing-policy rollout, cache-aware or cache-blind, without a matched-workload comparison, capacity at SLO, rewarm evidence, observability, rollback trigger and unchanged isolation boundary.
- The routing-policy rollout blocker does not block continued operation or emergency rollback of an unchanged/known policy by name; see `references/mechanics.md`.
- `max_model_len` or KV settings changed without p99 input/KV pressure review.
- Cache controls, `cachePoint`, `prompt_cache_key`, TTL, retention, or salts changed without provider-doc checks.
- vLLM retention flag/env is used without evidence that the deployed runtime supports the feature; an env name in a manifest is not enough.
- A positive interval is selected without sparse KV-group topology and effective `scheduler_block_size` evidence.
- An FS/OBJ/P2P sharing group uses different algorithms or different effective seeds.
- `PYTHONHASHSEED` is used as an isolation mechanism instead of retaining a separately reviewed `cache_salt` boundary.
- A rolling upgrade of a shared cache tier or prefix-reuse path mixes hash or retention semantics without canary evidence. This blocker does not apply automatically to a pure full-attention deployment with no shared reuse path.

## Minimum Release Evidence

- Rendered before/after prompt pair for each hot prompt family.
- Prefix/tool/schema hashes and first divergence location.
- Cache read/write fields by route/model/provider/region/replica.
- TTFT/prefill, final latency, output tokens, and tool timing.
- For routing-policy or replica/KV-topology changes: objective/SLO/rollback, matched-workload comparison, capacity at SLO, and rewarm; see `references/mechanics.md` and `references/observability.md`.
- Prompt version, deploy SHA, SDK/provider version, router settings.
- image digest/version/commit SHA, resolved cache config (including feature presence and retention source/value), concrete KV-group geometry, and redacted hash/seed compatibility status.
- Privacy or isolation decision for cache key/salt boundaries.

## Triage Order

1. Applicability Gate: hot, repeated, long stable prefix, safe reuse.
2. Prefix stability: static first, dynamic late, append-only history.
3. Provider correctness: fields, thresholds, breakpoint syntax, TTL/retention.
4. Routing/KV: KV capacity, eviction; use the `Routing Outcome Gate` in `references/mechanics.md`; use `references/observability.md` for fields.
5. Economics: output share and write premium before claiming savings.

Do not block on generic cache advice when the route is cold, unique, short, output-bound, or intentionally isolated.
