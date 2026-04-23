# Gemini Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- supported models for implicit and explicit caching
- minimum token counts by API surface/model
- TTL defaults and limits
- storage pricing for explicit caches
- usage metadata fields
- Vertex AI vs Gemini API differences
- whether implicit caching has a cost-saving guarantee for the selected model/API surface

Official sources:
- Gemini context caching: https://ai.google.dev/gemini-api/docs/caching
- Gemini API docs: https://ai.google.dev/gemini-api/docs
- Vertex AI context caching: https://cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview
- Pricing: https://ai.google.dev/gemini-api/docs/pricing

## Stable Mechanics

Gemini has two relevant caching modes:

- **Implicit caching**: automatic for qualifying Gemini models, with no guaranteed savings unless the provider reports a hit.
- **Explicit context caching**: create and reuse a cache object with a TTL and a more predictable cost-saving surface.

Use explicit caching when the application repeatedly uses a large stable context and needs deterministic cache reuse. Use implicit caching as an optimization, not a guarantee. Cached content is still part of the effective prompt prefix; put large shared content early.

## Provider Checks

### Implicit Cache Expectations

Do not assume 100% hit rate for identical-looking prompts. Check docs and usage metadata, then measure real traffic. If implicit caching does not hit, first verify prompt length, shared-prefix placement, request cadence, model support, and whether the beginning of the prompt is truly stable.

### Explicit Cache Lifecycle

When using explicit caches, verify:
- cache object creation
- TTL
- cache name/ID reuse
- cleanup of stale cache objects
- storage pricing
- whether cached content is treated as a prefix to the prompt

### Gemini API Vs Vertex AI

Thresholds, regions, pricing, and supported models can differ. Identify the exact surface before recommending changes.

### Large Stable Documents

If the same document/context is sent repeatedly, prefer explicit context caching after verifying it is supported for the model and region.

## Diagnostics

Usage field names vary by SDK/API surface. Check current docs.

Typical checks:

```python
usage = response.usage_metadata
cached = getattr(usage, "cached_content_token_count", None)
prompt = getattr(usage, "prompt_token_count", None)
```

SDK naming can differ. Also check camelCase forms such as `cachedContentTokenCount` if the SDK returns dict-like metadata.

For OpenAI-compatible routes, check whether `usage.prompt_tokens_details.cached_tokens` is exposed.

If `cached` is zero for repeated large contexts:
- request is below current minimum token count for the model/API surface
- shared content is not at the beginning
- requests are too far apart for implicit reuse
- explicit cache name/ID is not reused
- cache TTL expired or cache object was deleted
- API surface or region differs from the one that created the cache

## Monitoring

Track:
- cached token count
- prompt token count
- cache object ID/name
- TTL and expiration
- storage cost for explicit caches
- cache hit behavior by model and region
- request cadence for implicit caching

Alert on zero cached tokens for repeated large contexts, and on stale explicit caches that keep incurring storage cost.
