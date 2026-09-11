# Xiaomi MiMo Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- current MiMo model names and cache-hit prices (about 0.02x of input at the last review)
- whether cache writes stay "limited-time free"
- block alignment (community reports 4096-token blocks; not official)
- the Anthropic-compatible path and its `cache_control` handling

Official sources:
- OpenAI-compatible API: https://mimo.mi.com/docs/en-US/api/chat/openai-api
- Pricing: https://mimo.mi.com/docs/en-US/price/pay-as-you-go

## Stable Mechanics

MiMo (`https://api.xiaomimimo.com/v1`) documents **automatic** prefix caching: when the requested prefix hits the cache it is billed at the cache-hit price, `usage.prompt_tokens_details.cached_tokens` reports "tokens served from cache", and cache writes are listed as limited-time free. There is no `prompt_cache_key`, `cache_control`, minimum, or TTL in the reference.

The cache-hit price is unusually low (about 2% of the miss price), so the economics differ from most vendors: hits are almost free, and the audit question becomes hit *rate* and prefix layout rather than write cost. Community reports describe 4096-token block alignment and a hosted-API hit-rate drop in mid-2026; treat both as unverified operational signals to test, not facts.

## Provider Checks

- Label records `provider: xiaomi` (or `mimo`) for inclusive semantics in `analyze_usage_logs.py`.
- With coarse block alignment, a prefix must be long and stable in large blocks; short shared prefixes may never hit. Measure `cached_tokens` granularity on your own traffic before setting expectations.
- An Anthropic-compatible path that accepts `cache_control` is reported by tooling but not officially documented; verify the usage object before relying on `cache_read_input_tokens`.
- OpenRouter's caching table omits Xiaomi although its endpoints publish `input_cache_read`; the same slug fans out to hosts with different block behavior.

## Diagnostics

Compare `cached_tokens` across repeated calls; record its granularity, the prompt length, model alias (`mimo-v2.5`, `mimo-v2.5-pro`), host, and time. If hits are always zero, check prompt length against the observed block size and prefix drift.

## Monitoring

Track cached tokens by model and host, `cached_tokens` granularity, prompt/tool/schema hash, cadence, and cache-write price status. Alert on hit-rate drops not explained by prompt changes (provider-side behavior can change).
