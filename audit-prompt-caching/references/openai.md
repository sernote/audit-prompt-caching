# OpenAI Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- supported models and whether extended prompt cache retention is available
- pricing and cache discounts
- minimum cacheable token count and cache increment size
- request parameters such as `prompt_cache_key` and `prompt_cache_retention`
- usage object shape for Responses API vs Chat Completions
- tool, image, and structured-output caching semantics

Official sources:
- Prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching
- API reference: https://developers.openai.com/api/docs/api-reference
- Function/tool calling: https://developers.openai.com/api/docs/guides/function-calling
- Tool search: https://developers.openai.com/api/docs/guides/tools-tool-search
- Tool search / hosted tools docs, when relevant: https://developers.openai.com/
- Pricing: https://openai.com/api/pricing/

## Stable Mechanics

OpenAI prompt caching is automatic for supported models. Cache hits require exact prefix matches, so static content should be at the beginning and dynamic content at the end.

Cacheable content can include:
- messages
- images, with identical representation and `detail`
- tool definitions
- structured output schemas

As of the last review, OpenAI docs state that prompts below the minimum threshold still expose `usage.prompt_tokens_details.cached_tokens`, but the value is zero. Confirm current details before relying on the exact threshold or increment.

## Provider Checks

### Cache Key And Retention

Check whether repeated long-prefix traffic should use `prompt_cache_key`. This is a routing hint; choose a granularity that groups true shared prefixes without creating hot spots.

Check `prompt_cache_retention` only after verifying current model support. Do not add it blindly: unsupported models or SDK versions may reject the parameter.

### Structured Outputs

Structured output schemas can be part of the cacheable prefix. Do not put `request_id`, timestamps, tenant IDs, or per-request constants into the schema.

### Tools

Sort tools and keep their definitions stable. If the app needs a dynamic subset of tools, check current OpenAI docs for supported mechanisms such as allowed tools or tool search before changing the request body on every step.

### Images

Keep image representation stable. Changing `detail`, signed URL query strings, or base64 vs URL representation can fragment cache reuse.

### Reasoning Or Model Settings

Changing model, reasoning effort, or request settings can create separate cache buckets. Verify current docs and measure by route/model/settings.

## Diagnostics

For Responses API or Chat Completions, inspect:

```python
usage = response.usage
cached = usage.prompt_tokens_details.cached_tokens
total = usage.prompt_tokens
ratio = cached / total if total else 0
```

If `cached == 0` for repeated long prompts, check:
- prefix changed before user-specific content
- tools or response schema changed
- image representation changed
- request reached a different cache route
- prompt is below the current cacheable threshold

## Monitoring

Track:
- `usage.prompt_tokens_details.cached_tokens`
- `cached_tokens / prompt_tokens`
- model, `prompt_cache_key`, prompt version, tool hash, schema hash
- TTFT or prefill latency by route

Alert on cache ratio drops after prompt, SDK, model, tool, schema, or routing changes.
