# OpenAI Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-25.

Verify before exact claims:
- supported models and whether extended prompt cache retention is available
- pricing and cache discounts
- minimum cacheable token count and cache increment size
- request parameters such as `prompt_cache_key` and `prompt_cache_retention`
- usage object shape for Responses API vs Chat Completions
- tool, image, and structured-output caching semantics
- reasoning-model and Chat Completions caveats

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

As of the last review, OpenAI docs state that caching is available for prompts containing 1024 tokens or more. Requests below the threshold still expose a cached-token usage field, but the value is zero. Confirm current details before relying on the exact threshold, model list, or retention support.

## Provider Checks

### Cache Key And Retention

Check whether repeated long-prefix traffic should use `prompt_cache_key`. It is combined with the initial prefix hash for routing, so choose a granularity that groups true shared prefixes without creating hot spots or cache overflow.

Check `prompt_cache_retention` only after verifying current model support. Do not add it blindly: unsupported models, API surfaces, or SDK versions may reject the parameter. When extended retention is relevant, check data residency and ZDR implications in current docs.

### Structured Outputs

Structured output schemas can be part of the cacheable prefix. Do not put `request_id`, timestamps, tenant IDs, or per-request constants into the schema.

### Tools

Sort tools and keep their definitions stable. If the app needs a dynamic subset of tools, check current OpenAI docs for supported mechanisms such as allowed tools or tool search before changing the request body on every step.

### Images

Keep image representation stable. Changing `detail`, signed URL query strings, or base64 vs URL representation can fragment cache reuse.

### Reasoning Or Model Settings

Changing model, reasoning effort, or request settings can create separate cache buckets. Verify current docs and measure by route/model/settings.

For reasoning models, compare Responses API vs Chat Completions behavior using current OpenAI docs. If troubleshooting mentions lower caching for a given API/model combination, report it as provider-specific and verify with usage metadata before changing architecture.

## Diagnostics

For Responses API, inspect:

```python
usage = response.usage
cached = usage.input_tokens_details.cached_tokens
total = usage.input_tokens
ratio = cached / total if total else 0
```

For Chat Completions, inspect:

```python
usage = completion.usage
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
- reasoning effort, API surface, or request settings changed

## Monitoring

Track:
- Responses: `usage.input_tokens_details.cached_tokens`
- Chat Completions: `usage.prompt_tokens_details.cached_tokens`
- `cached_tokens / input_tokens` for Responses or `cached_tokens / prompt_tokens` for Chat Completions
- model, `prompt_cache_key`, prompt version, tool hash, schema hash
- `prompt_cache_retention` policy when used
- TTFT or prefill latency by route

Alert on cache ratio drops after prompt, SDK, model, tool, schema, or routing changes.
