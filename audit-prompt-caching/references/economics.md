# Prompt Cache Economics

Use this reference for provider comparison, migration planning, unexplained bills, or "high hit rate but no savings" cases. Verify current provider prices, model names, TTLs, cache discounts, and storage/write premiums before exact calculations. For latency or throughput symptoms, also load `references/mechanics.md`.

## Effective Cost Variables

Model the request by shape, not by price-list input cost alone:

- `S`: stable input tokens that can be reused across requests
- `D`: dynamic input tokens that are unique per request
- `O`: output tokens
- `h`: cache hit rate for the stable prefix, from `0` to `1`
- `P_miss`: uncached input price or compute cost
- `P_hit`: cached-read input price or compute cost
- `P_write`: cache-write input price or compute cost, if separate
- `P_out`: output price

Basic effective-cost shape:

```text
C = S * ((1 - h) * P_miss + h * P_hit) + D * P_miss + O * P_out
```

For explicit-cache providers, prefer raw usage fields over averaged assumptions:

```text
C = input_uncached * P_miss
  + cache_read_tokens * P_hit
  + cache_write_tokens * P_write
  + output_tokens * P_out
  + storage_or_ttl_cost
```

Do not assume one provider's cache math applies to another provider. If output tokens dominate cost, prompt caching can be technically correct and financially underwhelming.

## Usage Fields To Collect

Ask for a sample of real usage records, not averages from memory.

Collect when available:
- total input tokens
- cached-read tokens, such as `cached_tokens` or `cache_read_input_tokens`
- cache-creation/write tokens, such as `cache_creation_input_tokens`
- Bedrock-style read/write fields, such as `CacheReadInputTokens` and `CacheWriteInputTokens`
- dynamic uncached input tokens
- output tokens
- model, region, route, prompt version, cache key or prefix family
- timestamps to compare traffic cadence with TTL

For Anthropic-style usage, total input for hit-rate math must include cache reads, cache creation, and uncached input. Counting only `input_tokens` can overstate hit rate.

## Diagnosis Patterns

### High Hit Rate, Bill Did Not Drop

Check output share before changing models. If output tokens dominate cost, input-cache savings may be real but financially small.

Audit steps:
- calculate cost share from input misses, cache reads/writes, and output
- compare p50/p95 output tokens by route
- check whether a flagship model's output price dominates the workload
- consider output length, response compression, or model choice only after confirming quality requirements

### Cache Hit, Latency Did Not Drop Enough

Prompt caching mainly reduces prefill/input-processing work. If total response latency stays high, split TTFT from decode/output time:
- first-token latency or prefill time
- final-token latency
- output tokens
- tool execution time
- provider streaming overhead

Do not treat a long final response as a prompt-cache failure unless TTFT or prefill also regressed.

### Price List Says Cheaper, Effective Cost Says No

Compare providers with the real workload shape:
- static token count
- dynamic token count
- output token count
- real or conservative hit rate
- cache write/storage premium
- minimum cacheable tokens and TTL

For migration planning, compute both:
- current effective cost using observed hit rate
- target effective cost with conservative hit rate until the prompt layout is proven on the new provider
- target latency using conservative prefill savings and unchanged output/decode cost

### Explicit Cache Write Premium

Explicit caching can be profitable with high reuse and harmful with sparse traffic.

Check:
- how often the same stable prefix is reused before TTL expires
- whether cache writes are paid again after idle windows
- whether long TTL adds storage or higher write cost
- whether cache creation is visible separately from cache reads

If `cache_creation_input_tokens` is high and cache reads stay low, diagnose prefix mismatch, TTL, model/region support, route changes, or explicit-cache object lifecycle before recommending larger TTL.

### Hidden Migration Tax

Do not copy a 90% hit rate from the old provider into the new provider's cost model.

Common migration breaks:
- exact-prefix providers cannot reuse a static RAG block placed after dynamic user text
- explicit cache breakpoints do not map to implicit prefix caching
- different minimum token thresholds or TTLs change which routes are cacheable
- implicit caching may be best-effort rather than guaranteed
- usage field names differ, hiding write-without-read failures

### Isolation Trade-Off

Per-user or per-request cache isolation can be a correct security choice and still reduce reuse. Treat it as a policy decision:
- identify the trust boundary required by compliance or side-channel concerns
- estimate cache reuse at that boundary
- avoid accidental isolation from request IDs, session IDs, or per-request salts
- do not recommend broader sharing unless the data and threat model allow it

## Self-Hosted Economics

For vLLM/SGLang/self-hosted inference, cache savings appear as:
- lower prefill compute
- lower TTFT
- higher throughput
- less GPU pressure

Ask for:
- prefix-cache hit/query metrics
- KV block pressure and eviction metrics
- TTFT by route and prompt family
- replica routing behavior
- traffic volume and concurrency

Do not translate managed-provider token discounts directly into self-hosted cost. Use workload throughput and GPU capacity as the economic surface.

## Questions To Ask

1. What are p50/p95 `S`, `D`, and `O` by route?
2. Which cache read/write fields are visible in raw usage?
3. What fraction of total cost is output?
4. Is traffic steady enough for the selected TTL or cache lifetime?
5. Are there many prompt variants or prefix families splitting reuse?
6. Is this managed API billing or self-hosted compute?
7. What hit rate should be assumed during migration before production evidence exists?
