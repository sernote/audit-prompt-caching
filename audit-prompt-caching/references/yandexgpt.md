# Yandex Cloud AI Studio (YandexGPT) Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- which models carry a cached-token price that is actually lower than the input price
- response usage fields for REST, gRPC, SDK, OpenAI-compatible Chat Completions, and Responses routes
- supported model names, context windows, and lifecycle branches
- pricing (synchronous vs asynchronous vs batch)
- tokenization APIs

Official sources (Yandex Foundation Models became Yandex Cloud AI Studio; the old `yandex.cloud/.../foundation-models` links redirect to the docs root, so use these):
- Models: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/models
- Tokens: https://aistudio.yandex.ru/docs/en/ai-studio/concepts/generation/tokens.html
- Text Generation API (native): https://aistudio.yandex.ru/docs/en/ai-studio/text-generation/api-ref/TextGeneration/completion
- OpenAI-compatible API: https://aistudio.yandex.ru/docs/en/ai-studio/api/ and https://aistudio.yandex.ru/docs/en/ai-studio/chat/createChatCompletion.html
- Pricing: https://aistudio.yandex.ru/docs/en/ai-studio/pricing
- Release notes: https://aistudio.yandex.ru/docs/en/ai-studio/release-notes/

## Current Position

As of the last review, AI Studio documents **implicit** prompt caching: the pricing page bills four token types (input, output, cached, tool) and says caching "is enabled automatically where possible and applicable", "is not guaranteed", and "does not apply to output tokens". There is no `cache_control`, `prompt_cache_key`, TTL, or minimum-prefix parameter, and no cache-write or storage line.

Cached-token pricing exists only in the synchronous table (none for async or batch). A cached rate lower than the input rate is documented only for a few models (Alice AI LLM Flash, DeepSeek V4 Flash, Qwen3.6 35B at about 25% of input at the last review); for YandexGPT Pro/Lite, Alice AI LLM, Qwen3 235B, and gpt-oss the cached price equals the input price, so a hit saves nothing on the bill. Check the model's row before promising savings.

Cache visibility depends on the surface: the OpenAI-compatible Chat Completions schema at `https://ai.api.cloud.yandex.net/v1` exposes `usage.prompt_tokens_details.cached_tokens` (and `completion_tokens_details.reasoning_tokens`), while the native Text Generation `ContentUsage` (`inputTextTokens`, `completionTokens`, `totalTokens`) has no cache field. Whether the Responses route exposes `input_tokens_details.cached_tokens`, and whether any model returns a nonzero `cached_tokens` in practice, is unverified: documented examples show only totals. Treat the ratio as non-decision-grade until a captured response shows the details object.

## What Still Matters

Universal prompt-stability rules apply because the cache is implicit and prefix-based:
- stable instructions first, volatile values late
- deterministic token/cost accounting per model row (cached price may equal input price)
- cleaner migration to providers or engines with richer cache metrics
- self-hosted or OpenAI-compatible routes behind Yandex infrastructure

## Provider Checks

### API Surface

Identify whether the project uses:
- Yandex Foundation Models REST/gRPC
- Yandex Cloud ML SDK
- OpenAI-compatible endpoint
- a third-party model hosted through Yandex Cloud

Each surface can expose different usage fields.

### Token Accounting

Use the Yandex tokenizer docs/API for token estimation. Do not infer cache behavior from token counts alone.

### Cache Metrics By Surface

On the native Text Generation API, report that cache hit rate cannot be measured directly and focus on TTFT, prompt token count, total token cost, and billing "cached tokens" lines. On the OpenAI-compatible route, read `prompt_tokens_details.cached_tokens` when present and treat an absent details object as "not observed", not as zero.

## Diagnostics

Look for usage fields in actual responses and compare with current docs. For the OpenAI-compatible route use the OpenAI-shaped adapter (`cached_tokens` inclusive of `prompt_tokens`). If no cached-token fields exist, use:

- prompt/input token count
- total token count
- TTFT/prefill latency where observable
- model URI/version
- prompt hash for drift detection

## Monitoring

Track:
- model URI and lifecycle branch (`latest`, `rc`, `deprecated`); there is no automatic version switching
- prompt token count and `cached_tokens` where exposed, joined with the model's cached price
- billing "cached tokens" line vs input tokens for the sync route
- output token count
- TTFT
- prompt/tool/schema hash

Alert on token/latency regressions after prompt-template, SDK, model URI, or region changes.
