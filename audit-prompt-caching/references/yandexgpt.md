# YandexGPT Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- whether Yandex Cloud documents prompt/context caching for the selected API surface
- response usage fields for REST, gRPC, SDK, and OpenAI-compatible routes
- supported model names, context windows, and lifecycle branches
- pricing
- tokenization APIs

Official sources:
- Text generation models: https://yandex.cloud/en/docs/foundation-models/concepts/generation/models
- Tokens and usage notes: https://yandex.cloud/en/docs/foundation-models/concepts/yandexgpt/tokens
- Text Generation API reference: https://yandex.cloud/en/docs/foundation-models/text-generation/api-ref/
- OpenAI compatibility docs: https://yandex.cloud/en/docs/foundation-models/operations/yandexgpt/openai
- Pricing: https://yandex.cloud/en/prices

## Current Position

As of the last review, no official YandexGPT prompt/prefix caching mechanism comparable to OpenAI or Anthropic was found in the Yandex Foundation Models docs searched for this skill.

Do not claim YandexGPT has provider-visible prompt caching unless current Yandex docs show it. If the user uses an OpenAI-compatible route to a third-party model through Yandex Cloud, verify that route separately.

## What Still Matters

Universal prompt-stability rules can still help with:
- future provider-side optimizations
- deterministic token/cost accounting
- cleaner migration to providers or engines with visible cache metrics
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

### No Cache Metrics

If no cache fields exist, report that cache hit rate cannot be measured directly for this provider path. Focus on TTFT, prompt token count, total token cost, and migration readiness.

## Diagnostics

Look for usage fields in actual responses and compare with current docs. If no cached-token fields exist, use:

- prompt/input token count
- total token count
- TTFT/prefill latency where observable
- model URI/version
- prompt hash for drift detection

## Monitoring

Track:
- model URI and lifecycle branch (`latest`, `rc`, `deprecated`)
- prompt token count
- output token count
- TTFT
- prompt/tool/schema hash

Alert on token/latency regressions after prompt-template, SDK, model URI, or region changes.
