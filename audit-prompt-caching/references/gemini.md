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

Official sources:
- Gemini context caching: https://ai.google.dev/gemini-api/docs/caching
- Gemini API docs: https://ai.google.dev/gemini-api/docs
- Vertex AI context caching: https://cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview
- Pricing: https://ai.google.dev/gemini-api/docs/pricing

## Stable Mechanics

Gemini has two relevant caching modes:

- **Implicit caching**: automatic/best-effort for qualifying prompts.
- **Explicit context caching**: create and reuse a cache object with a TTL.

Use explicit caching when the application repeatedly uses a large stable context and needs deterministic cache reuse. Use implicit caching as an optimization, not a guarantee.

## Provider Checks

### Implicit Cache Expectations

Do not assume 100% hit rate for identical-looking prompts. Check docs and usage metadata, then measure real traffic.

### Explicit Cache Lifecycle

When using explicit caches, verify:
- cache object creation
- TTL
- cache name/ID reuse
- cleanup of stale cache objects
- storage pricing

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

For OpenAI-compatible routes, check whether `usage.prompt_tokens_details.cached_tokens` is exposed.

## Monitoring

Track:
- cached token count
- prompt token count
- cache object ID/name
- TTL and expiration
- storage cost for explicit caches
- cache hit behavior by model and region

Alert on zero cached tokens for repeated large contexts, and on stale explicit caches that keep incurring storage cost.
