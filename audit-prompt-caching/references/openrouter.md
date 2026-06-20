# OpenRouter Prompt Cache Reference

Last reviewed: 2026-04-30. Verify official docs before exact claims about model/provider support, cache read/write pricing, sticky routing, `provider.order`, `provider.only`, `provider.ignore`, fallback, `openrouter/auto`, `cache_control`, usage fields, ZDR, or context compression.

Official sources:
- Prompt caching: https://openrouter.ai/docs/guides/best-practices/prompt-caching
- Provider routing: https://openrouter.ai/docs/guides/routing/provider-selection
- Usage accounting: https://openrouter.ai/docs/guides/administration/usage-accounting
- Generation metadata: https://openrouter.ai/docs/api/api-reference/generations/get-generation
- Message transforms: https://openrouter.ai/docs/guides/features/message-transforms

## Mechanics

OpenRouter is an OpenAI-compatible router, not one provider. Prompt-cache behavior depends on the downstream provider/model plus OpenRouter route stability. Detect it before generic OpenAI advice:

```bash
rg -n "openrouter|OPENROUTER_API_KEY|openrouter.ai/api/v1|@openrouter/sdk|OpenRouter|openrouter/auto" .
```

OpenRouter can expose `usage.prompt_tokens_details.cached_tokens` and `cache_write_tokens` when available. `cache_write_tokens > 0` with repeated `cached_tokens == 0` means writes are not turning into reads; missing fields are not automatically failures.

## Audit Checklist

- Inspect `model`, `models`, `provider`, `plugins`, `messages`, `cache_control`, and account provider preferences.
- Measure actual routed provider/model; manual provider ordering, `provider.only`, `provider.ignore`, sorting, fallback, `allow_fallbacks`, and `openrouter/auto` can fragment cache locality.
- Keep first system/developer and first non-system messages stable because sticky routing can be conversation-scoped.
- A stable operation anchor as the first non-system message is only a measured pilot, not a universal fix.
- Prefer keyed hashes such as HMAC-SHA256 for first-message and prefix fingerprints.
- Check current docs before assuming direct Anthropic/Gemini/OpenAI cache controls pass through unchanged.
- Privacy filters, `zdr`, `data_collection`, and provider allow/ignore lists can correctly remove cache-capable routes.
- Disable or log context-compression plugin behavior during diagnosis; compressed and uncompressed prompts are different cache inputs.

## Diagnostics

Ask for raw request body, `cached_tokens`, `cache_write_tokens`, generation id, routed model/provider, cache discount/cost details, first-message and prefix hashes, and account privacy/provider settings.

If writes exist but reads stay low, check opening-message drift, provider fallback, auto-router changes, unsupported provider cache behavior, ignored `cache_control`, context compression, or TTL expiry.
