# Tencent Hunyuan / TokenHub Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- whether Hunyuan (Hy3, Hy4-preview) caching is automatic or explicit; the docs state neither
- cache-hit price per model and region (about 0.05x of input for Hy4-preview at the last review)
- usage field spelling: `prompt_tokens_details.cached_tokens` vs a singular `cached_token`
- minimum tokens and TTL, which are undocumented

Official sources:
- TokenHub OpenAI-compatible API: https://www.tencentcloud.com/document/product/1300/80695
- Hunyuan model and pricing notes: https://www.tencentcloud.com/techpedia/148044

## Stable Mechanics

Tencent's Hunyuan models are served through TokenHub (`https://tokenhub-intl.tencentcloudmaas.com/v1`, OpenAI- and Anthropic-protocol compatible). Usage exposes cached tokens as `prompt_tokens_details.cached_tokens`, but at least one TokenHub example shows a singular `cached_token` key; read both spellings before declaring a route "no telemetry". The FAQ says a cache hit must not be assumed, and the docs give no minimum, TTL, or explicit marker, so treat caching as implicit and best-effort.

Third-party snapshots of OpenRouter rankings at the last review placed Tencent (Hy4-preview and Hy3) among the highest-volume vendors, while OpenRouter's caching table does not list it; the single Tencent endpoint publishes an `input_cache_read` price, so router-level behavior is unverified beyond pricing.

## Provider Checks

- Label records `provider: tencent` (or `hunyuan`) for inclusive semantics in `analyze_usage_logs.py`; the adapter reads both `cached_tokens` and the singular `cached_token`, and `source_fields` shows which spelling was present. A record with neither stays ambiguous.
- The cache-hit price is a small fraction of input, so uneconomic hits are unlikely; a high `cached_tokens` share with no cost drop points to output/tool dominance or the wrong model row.
- Region matters (Singapore vs mainland hosts) for both price and cache locality.

## Diagnostics

Compare repeated calls with identical opening messages on one host; check region, model alias (Hy3 vs Hy4-preview), field spelling, and served provider when routed.

## Monitoring

Track cached tokens by model, region, and host; prompt/tool/schema hash; cadence. Alert on drops after model, region, or router changes.
