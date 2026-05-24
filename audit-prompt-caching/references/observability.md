# Minimum Telemetry Contract

Last reviewed: 2026-05-25.

Use this reference when designing dashboards, traces, release checks, or incident logs for prompt/prefix/KV cache behavior. Observability should prove whether caching is the right lever before prompt or routing changes are made.

## Per-Request Fields

Capture these fields when available:

| Field | Purpose |
|---|---|
| `request_id` | join logs and traces; keep it outside the cacheable prefix |
| `route` or prompt family | group comparable requests |
| `tenant_boundary` or safe segment | reason about isolation without logging raw tenant data |
| `provider`, `model`, `api_surface`, `region` | explain separate cache buckets |
| `cache_read_tokens` | tokens served from provider/KV cache |
| `cache_write_tokens` | tokens written or created in cache |
| `input_tokens_uncached` | new prompt tokens billed or processed at miss price |
| `output_tokens` | detect output-dominated cost or latency |
| `ttft_ms` or `prefill_ms` | isolate prompt processing from decoding |
| `total_latency_ms` | distinguish user-visible latency from TTFT |
| `prompt_version` | correlate deploys and prompt edits |
| `prefix_hash` | stable cacheable prefix fingerprint |
| `system_prompt_hash` | detect system prompt drift |
| `tools_hash` | detect tool definition or ordering drift |
| `schema_hash` | detect structured output drift |
| `first_256_token_hash` | approximate OpenAI routing-prefix drift where useful |
| `compaction_event` | explain agent-loop cache resets |
| `replica` or routed worker | debug self-hosted and gateway locality |

Normalize provider fields into `cache_read_tokens` and `cache_write_tokens`, but keep raw usage fields for auditability. For Anthropic-style records, total cacheable input for hit-rate math includes cache reads, cache creation, and uncached input. For OpenAI-style records, use the documented cached-token field for the API surface in use.

## Derived Metrics

Prefer route- and prompt-family-level metrics over global averages:

```text
cache_hit_ratio = cache_read_tokens / max(1, cache_read_tokens + cache_write_tokens + input_tokens_uncached)
input_cost_share = input_cost / max(1, input_cost + output_cost)
write_to_read_ratio = cache_write_tokens / max(1, cache_read_tokens)
prefix_family_cardinality = count_distinct(prefix_hash) by route and prompt_version
```

For latency, chart TTFT or prefill separately from final response latency. Prompt caching can improve prefill while output decoding, tools, network latency, or rate limits still dominate total latency.

## Dashboards

Build dashboards around these panels:

- cache hit ratio by route, prompt family, provider, model, region, and routed worker
- cache read/write/new input token split over time
- output-token share and total cost by route
- p50/p95 TTFT or prefill latency versus total latency
- distinct `prefix_hash`, `system_prompt_hash`, `tools_hash`, and `schema_hash` by deploy
- request rate per prefix/key family when routing locality depends on a cache key
- cache behavior before and after compaction, mode switches, tool registry changes, or provider failover
- self-hosted prefix-cache hit/query ratio, KV block pressure, eviction indicators, and replica routing

## Alerts

Create each alert around evidence-bearing symptoms, not one raw token field in isolation:

- `cache_read_tokens` stays zero for repeated long-prefix traffic after warm-up
- `cache_write_tokens` remains high while reads stay low for the same route
- `prefix_hash` cardinality jumps after a deploy without a planned prompt version change
- `tools_hash` or `schema_hash` changes inside a long agent trajectory
- TTFT regresses while output length and tool timing are stable
- cache hit ratio drops after scaling replicas or changing gateway routing
- explicit caches approach stale storage windows or unexpectedly high storage cost

## Privacy And Storage

Do not log raw prompts, raw tool schemas, retrieved documents, or user content just to debug cache behavior. Log hashes and short stable labels instead. Use HMAC or keyed hashes when plain hashes could reveal membership in a small set of sensitive prompts.

Keep salts, cache keys, tenant segments, and route labels out of the prompt unless the provider requires them in the request body. Security boundaries are product decisions: measure the efficiency cost of stricter isolation, but do not weaken a required trust boundary for cache hit rate.

## Release Guardrail

For CI or pre-deploy checks:

1. Render a known request payload for each hot prompt family.
2. Fingerprint the stable prefix, tools, and schema.
3. Fail or require review when the fingerprint changes without an intentional prompt version bump.
4. Run a small prefix-stability comparison on before/after payloads.
5. Pair static checks with production telemetry because cache support and routing are provider/runtime behavior.
