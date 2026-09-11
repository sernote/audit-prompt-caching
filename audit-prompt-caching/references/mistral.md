# Mistral Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- whether hits occur without `prompt_cache_key` (docs frame caching as key-driven)
- the 64-token cache block size
- cached-token price (10% of input at the last review) per model
- supported models and surfaces (only Chat Completions is shown)
- TTL, which is undocumented

Official sources:
- Prompt caching: https://docs.mistral.ai/studio-api/conversations/advanced/prompt-caching
- Chat Completions endpoint: https://docs.mistral.ai/api/endpoint/chat

## Stable Mechanics

Mistral does have prompt caching, contrary to older assumptions. The documented control is `prompt_cache_key`: set the same key on requests likely to share a prefix; it "increases the chance of a cache hit" but does not guarantee one. Cache blocks are 64 tokens, so `usage.prompt_tokens_details.cached_tokens` is always a multiple of 64 and prompts under 64 tokens never hit. Billable uncached input is `prompt_tokens - cached_tokens` (inclusive); cached tokens are billed at 10% of the input price.

No TTL, model list, or minimum beyond the block size is documented; whether requests without a key can hit is unstated. Treat key-less traffic as unmeasured rather than uncached.

## Provider Checks

- Label records `provider: mistral` so `analyze_usage_logs.py` applies inclusive semantics.
- Key hygiene: one stable key per shared prefix family, never per request or per raw user ID; a per-request key fragments reuse, and a raw identifier leaks into cache scope.
- Because matching is in 64-token blocks, a prefix change inside the first block wipes every later block; put volatile values after the stable prefix and verify with `prefix_stability_check.py`.
- OpenRouter's caching table omits Mistral even though Mistral endpoints publish 0.1x `input_cache_read`; router-level `cache_discount` behavior is unverified, and third-party hosts of Mistral models may have no cache pricing at all.

## Diagnostics

```python
usage = response.usage
details = getattr(usage, "prompt_tokens_details", None)
cached = getattr(details, "cached_tokens", 0) if details else 0
uncached = usage.prompt_tokens - cached
```

If `cached == 0` on repeated calls with a shared key: prefix under 64 tokens, first-block drift, different keys across the cohort, or a surface/model without documented caching.

## Monitoring

Track cached tokens by model and `prompt_cache_key` cardinality, prompt tokens, prompt/tool/schema hash, and served host when routed. Alert on drops after key policy or model changes.
