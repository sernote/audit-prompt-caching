# Prompt Cache Pre-Deploy And Incident Checklist

Use this reference for release reviews, incidents, observability plans, and self-hosted deployment audits. It turns the anti-patterns into an operational flow.

## Three Conditions

Prefix caching works only when all three are true:

1. The beginning of the request is token-identical enough for the provider or engine.
2. The request reaches a worker or cache domain where that prefix is warm.
3. The cache entry survives long enough to be reused.

Map every cache incident to one or more of those conditions before recommending fixes.

## Blocking Pre-Deploy Checks

Block or require explicit signoff when a hot LLM path adds any of these:

- timestamp, `request_id`, `run_id`, `trace_id`, user/company/tenant data in system prompt, tools, schema, or early messages
- dynamic or unordered `tools`
- `response_format` or JSON schema containing per-request constants
- prompt A/B test or feature flag before the stable prefix
- mode switch implemented by changing system prompt or tool list
- early-history summarization or truncation that rewrites the anchor
- vLLM/SGLang replica scaling without sticky or prefix-aware routing
- OpenRouter provider/model routing changes on a cache-critical route without sticky-routing and fallback review
- per-request or per-user cache salt/key that was not reviewed as a security trade-off
- `max_model_len` much larger than observed p99 without KV-capacity review
- fan-out batch over a cold long prefix without safe warm-up strategy
- context compression or message transforms enabled without prompt-prefix regression tests

## Release Checklist

### Prefix

- stable and shared content is first
- dynamic user/session facts are late or provider-supported metadata
- one canonical prompt renderer is used by all routes
- rendered prefix hash is stable across users, timestamps, and equivalent requests

### API Envelope

- tools are stable in content and sorted order
- schema serialization is deterministic
- `response_format` has no request-specific constants
- multimodal representation is stable, including image detail and URL/base64 strategy
- SDK or framework injection does not add dynamic fields before the prefix

### History

- conversation growth is append-only where possible
- compaction preserves the stable anchor
- bulky tool results are compacted before lossy summarization
- truncation does not silently remove the stable anchor

### Routing

- managed APIs use provider-supported cache keys or routing hints only after current docs are checked
- OpenRouter routes review `provider.order`, `provider.only`, `provider.ignore`, fallback, `openrouter/auto`, ZDR/data filters, and first-message conversation identity
- self-hosted inference uses sticky, prefix-aware, or consistent-hash routing for long shared prefixes
- route keys avoid over-fragmenting into per-user caches unless isolation requires it
- cache salts or affinity keys match the intended trust boundary
- hot spots are monitored when routing by prefix family

### Lifetime And Capacity

- TTL or cache lifetime matches traffic cadence
- prefix-family working set fits the KV/cache budget
- `max_model_len` is sized for the workload, not only for model marketing context
- eviction and repeated warm-up are observable

## Incident Triage

Start with the timeline:
- deploy time
- SDK/model/provider change
- prompt/template change
- tool/schema change
- replica count or gateway change
- traffic shape or batch/fan-out change
- compaction/summarization rollout

Then isolate:
- Did the prefix hash change?
- Did tool count or tool-name hash change?
- Did requests move across replicas/routes?
- Did cache key, salt, `user`, or affinity cardinality change?
- Did cache writes increase while reads stayed low?
- Did TTFT rise only for long-prefix routes?
- Did output share dominate cost even though cache reads worked?

## Observability Dimensions

Track cache metrics by:
- route or prompt family
- model and provider
- region or endpoint
- prompt version
- tool/schema hash
- prefix hash
- cache key or prefix family
- cache salt / affinity key family
- deployment version
- replica or worker
- agent step number

Core metrics:
- total input tokens
- cache read tokens
- cache creation/write tokens
- output tokens
- TTFT or prefill latency
- cache ratio by cacheable route
- cache writes without later reads
- cache discount or effective cache savings when available
- KV block pressure and eviction metrics for self-hosted inference

## CI Smoke Tests

Add a synthetic prompt-prefix test for hot routes:

1. Render the same route for several users, timestamps, tenants, and trace IDs.
2. Extract canonical `system + tools + response_format + stable early messages`.
3. Hash with deterministic JSON serialization.
4. Fail if the hash changes unexpectedly.
5. Include a 3-5 step agent session when tools or compaction are involved.

Provider usage metadata remains the source of truth. Prefix hashes are release guardrails, not proof of provider cache hits.
