# z.ai Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- current GLM model names and cache support
- cached input pricing and storage pricing
- cache hit trigger behavior and retention language
- usage field names
- API endpoint differences for general API vs Coding Plan

Official sources:
- Context caching: https://docs.z.ai/guides/capabilities/cache
- Chat Completion API: https://docs.z.ai/api-reference/llm/chat-completion
- Pricing: https://docs.z.ai/guides/overview/pricing
- FAQ: https://docs.z.ai/help/faq
- API introduction/endpoints: https://docs.z.ai/api-reference/introduction

## Stable Mechanics

z.ai docs describe automatic context caching for repeated context content. The response exposes cached token counts in `usage.prompt_tokens_details.cached_tokens` for supported routes.

The docs also indicate that cache trigger/retention details may not be fully specified. Treat it as provider-managed/best-effort unless current docs say otherwise.

## Provider Checks

### API Endpoint

Confirm whether the project uses the general endpoint or a Coding Plan endpoint. Do not mix endpoint assumptions.

### Cache Field

Check whether `usage.prompt_tokens_details.cached_tokens` exists for the model and SDK path in use.

### Similarity Vs Exact Prefix

z.ai docs describe identifying identical or highly similar content. Do not assume OpenAI-style exact-prefix behavior unless current docs state it. Still apply universal prefix-stability rules, because identical stable content should maximize hit probability.

### Pricing

Pricing includes separate cached-input columns for many models. Always verify current pricing before giving cost estimates.

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
- endpoint type
- TTFT by prompt length

Alert on cache drops after endpoint switch, model upgrade, prompt/schema/tool changes, or SDK changes.
