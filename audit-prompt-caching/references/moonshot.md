# Moonshot AI / Kimi Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- current Kimi model names and which accept automatic prefix caching
- the 256-token prefix threshold and chunk alignment
- cache hit/miss prices per model (no write or storage price at the last review)
- usage field names per API surface (Chat Completions vs Messages)
- whether the legacy explicit Context Caching API still answers

Official sources (the `platform.moonshot.ai`/`.cn` hosts redirect to `platform.kimi.ai`/`.com`):
- Automatic context caching: https://platform.kimi.ai/docs/guide/use-context-caching-feature-of-kimi-api
- Chat Completions API: https://platform.kimi.ai/docs/api/chat
- Messages (Anthropic-compatible) API: https://platform.kimi.ai/docs/api/messages
- Pricing: https://platform.kimi.ai/docs/pricing/chat

## Stable Mechanics

Kimi API caching is **automatic prefix caching** with no cache object, cache ID, or TTL management. The guide says a request can hit only when the previous request's prompt exceeded 256 tokens; unofficial probes report matching aligned to 256-token chunks and a TTL in the 5-30 minute range. Treat both as heuristics, not guarantees.

The older explicit Context Caching API (`POST /v1/caching`, `role: "cache"` messages with `cache_id=...;reset_ttl=...`) is no longer in the current docs index and reportedly rejects `kimi-k2.*` models. If a codebase still uses it, verify it against the live API before treating cache reads as real, and do not port it to new models.

`prompt_cache_key` exists on Chat Completions as a session hint for coding agents, but the docs do not promise it changes cache decisions and probes report it (and Anthropic `cache_control` markers) being ignored. Prefix stability and request cadence are the levers.

## Provider Checks

### Surfaces And Fields

- Chat Completions (`https://api.moonshot.ai/v1`): `usage.cached_tokens` at the **top level** ("tokens served from cache"), sometimes mirrored in `prompt_tokens_details.cached_tokens`; the count is a subset of `prompt_tokens` (inclusive). Label records `provider: moonshot` so `analyze_usage_logs.py` applies the inclusive OpenAI-compatible adapter; an unlabeled top-level `cached_tokens` stays ambiguous.
- Messages (`https://api.moonshot.ai/anthropic`): `cache_read_input_tokens` and `cache_creation_input_tokens`, additive to `input_tokens`. Probes report `cache_creation_input_tokens` always 0 because writes are implicit; do not read that as "nothing cached". The cache is shared between the two surfaces.

### Reasoning Effort Changes Break Hits

The Messages docs state that changing the reasoning effort level between requests breaks prefix-cache hits. Audit effort/thinking settings as part of the prefix, alongside tools and system text.

### Pricing Shape

Cache hits are priced per model at roughly 0.1-0.17x of the miss price at the last review (for example kimi-k2.6 $0.16 hit vs $0.95 miss per MTok); OpenRouter publishes a generic 0.25x multiplier for Moonshot, so use the vendor row, not the router table, for savings estimates. No write or storage fee is listed.

### Through OpenRouter

`moonshotai/*` slugs fan out to many hosts with different cache-read prices, and only sticky routing keeps a warm prefix; router probes have shown `cached_tokens: 0` for Kimi where the direct API hits. Join usage with the served provider before comparing.

## Diagnostics

```python
usage = response.usage
cached = getattr(usage, "cached_tokens", None)
if cached is None:
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details else 0
ratio = cached / usage.prompt_tokens if usage.prompt_tokens else 0
```

If `cached == 0` on repeated calls: prior prompt under 256 tokens, prefix drift before the first 256-token boundary, effort/thinking change, idle gap beyond the observed TTL, host change through a router, or a legacy `/v1/caching` path that no longer applies.

## Monitoring

Track `cached_tokens` (or `cache_read_input_tokens`) by model and surface, `prompt_tokens`, reasoning effort, prompt/tool/schema hash, request cadence, and served provider when routed. Alert on drops after model alias, effort, or host changes.
