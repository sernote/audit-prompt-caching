# z.ai Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- current GLM model names and cache support
- cached input pricing and storage pricing
- cache hit trigger behavior and retention language
- usage field names
- API endpoint differences for general API vs Coding Plan

Official sources:
- Context caching: https://docs.z.ai/guides/capabilities/cache
- Chat Completion API: https://docs.z.ai/api-reference/llm/chat-completion
- Thinking mode / preserved thinking: https://docs.z.ai/guides/capabilities/thinking-mode
- Coding Plan credits and endpoints: https://docs.z.ai/devpack/overview , https://docs.z.ai/devpack/quick-start
- Pricing: https://docs.z.ai/guides/overview/pricing
- FAQ: https://docs.z.ai/help/faq
- API introduction/endpoints: https://docs.z.ai/api-reference/introduction

## Stable Mechanics

z.ai docs describe automatic context caching for repeated context content. The response exposes cached token counts in `usage.prompt_tokens_details.cached_tokens` for supported routes.

The docs also indicate that cache trigger/retention details may not be fully specified. Treat it as provider-managed/best-effort unless current docs say otherwise. There is still no explicit cache-create API, no `cache_control` request parameter, and no minimum-token or TTL number; the docs only say the cache "will recalculate after expiration".

As of the last review the cache guide names GLM-5.3, GLM-5.3-Flash, GLM-5.x, GLM-4.7, GLM-4.6, and GLM-4.5 series as cache-capable. Verify the model list before claiming support for a new alias.

## Provider Checks

### API Endpoint

Confirm which surface the project uses; do not mix endpoint assumptions:
- general API: `https://api.z.ai/api/paas/v4`
- Coding Plan, OpenAI Chat Completions: `https://api.z.ai/api/coding/paas/v4`
- Coding Plan, OpenAI Responses: `https://api.z.ai/api/v1`
- Anthropic protocol: `https://api.z.ai/api/anthropic`

Coding Plan docs describe silent model routing (requests for GLM-5.2/GLM-5.1 served by GLM-5.3, GLM-4.7 by GLM-5.3-Flash). Attribute cache telemetry to the served model, not only to the requested model name.

The Anthropic-protocol route does not document `cache_control` handling or Anthropic-style cache usage fields. Treat its cache behavior as unverified until a wire capture shows the usage object.

### Cache Field

Check whether `usage.prompt_tokens_details.cached_tokens` exists for the model and SDK path in use.

### Similarity Vs Exact Prefix

z.ai docs describe identifying identical or highly similar content. Do not assume OpenAI-style exact-prefix behavior unless current docs state it. Still apply universal prefix-stability rules, because identical stable content should maximize hit probability.

### Preserved Thinking Affects Cache Hits

For thinking-capable GLM routes, the documented mechanism is `thinking: {"type": "enabled", "clear_thinking": false}` plus returning every prior `reasoning_content` block unmodified and in order. The thinking-mode guide says this "increases cache hit rates" and that editing or reordering reasoning blocks "may affect" them. With tools, thinking blocks must be returned together with tool results.

The default differs by endpoint: preserved thinking is on by default on the Coding Plan endpoint and off by default on the general API. The same client code therefore has different effective prefixes on the two surfaces. GLM-5.3 and GLM-5.3-Flash use forced thinking that cannot be disabled. Audit `clear_thinking`, reasoning round-tripping, and endpoint default separately from visible message text; dropping that state can make a cache regression look like a prompt-text issue.

### Pricing

The pricing table lists a cached-input column for every paid text/vision model; cached input is roughly 0.2x the standard input price (for example GLM-5.3 $1.4 input vs $0.26 cached per MTok at the last review), while the cache guide still says "usually 50%" and the FAQ says "1/5". Use the pricing table for estimates and say the docs disagree. Cached-input storage is "limited-time free"; recheck before assuming zero storage cost.

Coding Plan usage is credit-based: `(input x input multiplier + cached input x cached multiplier + output x output multiplier) / 10,000`, with the cached multiplier about 0.25x the input multiplier, and legacy plans add peak/off-peak multipliers. Cache ratio therefore drives credit burn directly, but credits are not USD; do not convert them with general-API prices.

## Diagnostics

```python
usage = response.usage
details = getattr(usage, "prompt_tokens_details", None)
cached = getattr(details, "cached_tokens", 0) if details else 0
total = usage.prompt_tokens
ratio = cached / total if total else 0
```

If `cached_tokens` is absent, inspect the raw `usage` object and check current docs for the route/model.

## Monitoring

Track:
- `usage.prompt_tokens_details.cached_tokens`
- cache ratio by model and endpoint
- prompt/tool/schema hash
- model name
- endpoint type and served model
- `clear_thinking` value and reasoning round-trip policy
- TTFT by prompt length

Alert on cache drops after endpoint switch, model upgrade, prompt/schema/tool changes, or SDK changes.
