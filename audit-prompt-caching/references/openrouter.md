# OpenRouter Prompt Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-30.

Verify before exact claims:
- which model/provider endpoints support prompt caching
- cache read/write pricing and model metadata fields
- provider sticky routing behavior and granularity
- `provider.order`, `provider.only`, `provider.ignore`, fallback, and `openrouter/auto` semantics
- `cache_control` behavior for Anthropic, Gemini, and other provider families through OpenRouter
- usage object field names and generation/activity metadata
- data policy, ZDR, and context-compression behavior

Official sources:
- Prompt caching: https://openrouter.ai/docs/guides/best-practices/prompt-caching
- Provider selection and routing: https://openrouter.ai/docs/guides/routing/provider-selection
- Usage accounting: https://openrouter.ai/docs/guides/administration/usage-accounting
- Generation metadata: https://openrouter.ai/docs/api/api-reference/generations/get-generation
- Models/pricing metadata: https://openrouter.ai/docs/models
- API reference: https://openrouter.ai/docs/api/reference/overview
- Message transforms/context compression: https://openrouter.ai/docs/guides/features/message-transforms

## Stable Mechanics

OpenRouter is an OpenAI-compatible routing layer, not a single model provider. Prompt caching depends on both the underlying provider/model and OpenRouter's route selection.

As of the last review, OpenRouter documents provider sticky routing for prompt caching. Sticky routing can keep later requests on the same provider endpoint after a cached request, but manual `provider.order`, sorting, and fallback/model routing can override or fragment that behavior. Treat route stability as part of prefix-cache stability.

OpenRouter's cache metrics are exposed in normalized usage fields when available:

```python
details = response.usage.prompt_tokens_details
cached = getattr(details, "cached_tokens", 0)
written = getattr(details, "cache_write_tokens", 0)
```

`cache_write_tokens > 0` with repeated `cached_tokens == 0` means the system may be creating cache entries that are not reused. `cache_write_tokens` is only returned for models with explicit caching and cache write pricing, so missing fields are not automatically failures.

## Provider Checks

### Detect OpenRouter Before Generic OpenAI

OpenRouter often uses OpenAI-compatible SDKs and `chat.completions`, so generic OpenAI detection can be misleading.

Search:

```bash
rg -n "openrouter|OPENROUTER_API_KEY|openrouter.ai/api/v1|@openrouter/sdk|OpenRouter|openrouter/auto" .
```

If present, load this reference before `openai.md`. Then load the underlying provider reference only when the request is pinned to a specific provider/model family.

### Sticky Routing And Provider Overrides

Inspect:
- `provider.order`
- `provider.only`
- `provider.ignore`
- `provider.allow_fallbacks` / `allowFallbacks`
- `provider.sort`
- `models` list
- `model: "openrouter/auto"`
- account-level provider preferences

Manual provider ordering, explicit provider allow/ignore lists, auto-router model selection, provider sorting, or fallback behavior can change the provider endpoint that owns the warm cache. For cache-critical routes, measure cache behavior by actual model/provider route and decide whether fallback resilience or cache locality matters more. Do not pin providers or disable fallback before telemetry shows that routing, not prefix shape or cache lifetime, is the blocker.

### Conversation Identity

OpenRouter sticky routing is conversation-scoped. Verify the opening messages used for conversation identity are stable. Dynamic timestamps, session IDs, user names, tenant facts, or A/B variants in the first system/developer message or first non-system message can fragment sticky routing even when later content is stable.

A short stable operation anchor as the first non-system message can be a useful OpenRouter experiment for one-shot calls, but it is not a guaranteed prompt-cache fix. It can improve sticky-route locality while leaving the provider-native cacheable prefix too short to matter if a large dynamic payload immediately follows. Recommend it as a measured pilot on hot operations, not as a blanket best practice.

Log keyed hashes such as HMAC-SHA256 for sensitive fingerprints; plain hashes can leak low-entropy prompt or tenant facts by guessing. Log:
- first system/developer message
- first non-system message
- stable prompt prefix
- model and routed provider, when visible

### Provider-Specific Cache Controls

Do not assume direct-provider cache semantics map one-to-one through OpenRouter.

Check current docs for:
- automatic caching for provider families such as OpenAI, DeepSeek, Grok, Groq, Moonshot, or Gemini implicit caching
- Anthropic top-level `cache_control` vs explicit per-block breakpoints
- Gemini explicit breakpoint behavior and the final-breakpoint rule
- minimum token thresholds and TTL by model/provider
- `require_parameters` when unsupported parameters must not be silently ignored

If `cache_control` changes routing eligibility, report that as an OpenRouter routing effect, not only a provider cache-control issue.

### Data Policy, ZDR, And Provider Filters

`data_collection`, `zdr`, account privacy settings, and provider allow/ignore lists can remove cache-capable endpoints from the route set. This may be correct for privacy or compliance. Treat it like cache isolation: document the trade-off and measure the cost/latency impact.

### Context Compression Plugin

OpenRouter context compression can remove or truncate middle messages to fit context limits. This can be useful, but it changes the prompt sent downstream and can invalidate prefix-cache assumptions.

For cache diagnosis, disable context compression or log whether it ran. Do not compare cached-token metrics across compressed and uncompressed routes as if the prefix were identical.

## Diagnostics

Ask for:
- raw request body including `model`, `models`, `provider`, `plugins`, `messages`, and `cache_control`
- response `usage.prompt_tokens_details.cached_tokens`
- response `usage.prompt_tokens_details.cache_write_tokens`
- `cache_discount` or generation/activity cost details when available
- response `id` / generation id
- actual response model and routed provider/endpoint when available; if not present on the completion response, fetch generation metadata for `provider_name`, `router`, `cache_discount`, `native_tokens_cached`, and cost fields
- first-message and prefix fingerprints
- account-level provider, ZDR, and data-policy settings

If cache writes exist but reads stay low:
- opening messages changed
- provider route changed or fallback occurred
- manual provider ordering disabled sticky behavior
- model auto-router selected different models
- provider does not support the requested cache behavior
- `cache_control` was ignored or changed provider eligibility
- context compression changed the downstream prompt
- cache TTL expired before reuse

## Monitoring

Track by route:
- OpenRouter model slug and actual response model
- provider endpoint or provider family when visible
- `cached_tokens`, `cache_write_tokens`, and cache discount/cost
- first system/developer hash and first non-system hash
- provider routing settings
- cache-control placement
- context-compression plugin state
- data/ZDR/provider-filter settings
