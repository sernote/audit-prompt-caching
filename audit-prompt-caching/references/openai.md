# OpenAI Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-27.

Verify before exact claims:
- supported models and whether extended prompt cache retention is available
- pricing, cache discounts, and whether retention policy changes pricing
- minimum cacheable token count and cache granularity
- request parameters such as `prompt_cache_key` and `prompt_cache_retention`
- usage object shape for Responses API vs Chat Completions
- tool, image, and structured-output caching semantics
- ZDR, Data Residency, Regional Inference, and retention behavior
- reasoning-model and Chat Completions caveats

Official sources:
- Prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching
- API reference: https://developers.openai.com/api/docs/api-reference
- Function/tool calling: https://developers.openai.com/api/docs/guides/function-calling
- Tool search: https://developers.openai.com/api/docs/guides/tools-tool-search
- Tool search / hosted tools docs, when relevant: https://developers.openai.com/
- Pricing: https://openai.com/api/pricing/

## Stable Mechanics

OpenAI prompt caching is automatic for supported recent models. Cache hits require exact prefix matches, so static content should be at the beginning and dynamic content at the end.

Caching is available for prompts containing 1024 tokens or more. Requests below the threshold still expose a cached-token usage field, but the value is zero.

Cacheable content can include:
- messages
- images, with identical representation and `detail`
- tool definitions
- structured output schemas, which serve as a prefix to the system message

OpenAI routing is cache-aware:
- requests are routed to a machine based on a hash of the initial prompt prefix
- the hash typically uses the first 256 tokens, but the exact length can vary by model
- `prompt_cache_key` is combined with the prefix hash, so it can improve locality when many requests share long common prefixes
- if requests for the same prefix and `prompt_cache_key` combination exceed roughly **15 requests per minute**, some can overflow to additional machines, reducing cache effectiveness
- a cache miss processes the full prompt and caches the prefix afterward on the selected machine

## Provider Checks

### Prefix Layout

Place stable instructions, examples, tools, schemas, and reusable documents before dynamic user-specific content. Any difference before the shared prefix boundary can drop `cached_tokens` to zero.

### Cache Key

Use `prompt_cache_key` consistently only for requests that truly share common prefixes. Choose a granularity that avoids both over-fragmentation and hot spots:
- too fine-grained, such as per-request or per-user keys for shared public content, can destroy reuse
- too broad, such as one global key for very high traffic, can exceed the approximate 15 requests per minute prefix/key locality envelope and cause overflow routing

Do not use `prompt_cache_key` as a privacy boundary. Treat it as a routing locality hint whose behavior still depends on the initial prefix hash and provider routing.

### Cache Retention

Use `prompt_cache_retention` only after checking current model and API-surface support. Allowed values in the current public docs are:

```json
{ "prompt_cache_retention": "in_memory" }
```

```json
{ "prompt_cache_retention": "24h" }
```

For most supported models, the default is `in_memory`. For `gpt-5.5`, `gpt-5.5-pro`, and future models, the default is `"24h"` and `in_memory` is not supported. Extended retention can keep cached prefixes active longer, up to 24 hours.

Prompt cache pricing is the same for both retention policies in the current docs. OpenAI prompt caching does not add a separate cache-write fee, but cached prompt tokens still count toward TPM rate limits.

### ZDR And Data Residency

Prompt caches are not shared between organizations. In-memory retention keeps cached prefixes in volatile GPU memory. Extended retention can temporarily store key/value tensors on GPU-local storage; those tensors are derived from customer content, while the original prompt text remains only in memory.

Extended prompt caching can be used when Zero Data Retention is enabled for the project, but other Zero Data Retention restrictions still apply, such as restrictions around `store=True`. For Data Residency, in-memory caching does not store data; extended retention locality depends on using Regional Inference.

### Structured Outputs

Structured output schemas can be part of the cacheable prefix. Do not put `request_id`, timestamps, tenant IDs, or per-request constants into the schema.

### Tools

Sort tools and keep their definitions stable. If the app needs a dynamic subset of tools, check current OpenAI docs for supported mechanisms such as allowed tools or tool search before changing the request body on every step.

### Images

Keep image representation stable. Changing `detail`, signed URL query strings, or base64 vs URL representation can fragment cache reuse.

### Reasoning Or Model Settings

Changing model, reasoning effort, retention policy, or request settings can create separate cache buckets. Verify current docs and measure by route/model/settings.

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
- `prompt_cache_key` is missing, inconsistent, too fine-grained, or too hot
- `prompt_cache_retention` is unsupported or changed across otherwise comparable calls
- reasoning effort, API surface, or request settings changed

If `cached_tokens` is high but latency or cost did not improve as expected, check:
- output token share and decode/final-token latency
- TPM rate limits, because cached prompt tokens still count
- traffic cadence versus retention policy
- overflow from a hot prefix/key combination

## Monitoring

Track:
- Responses: `usage.input_tokens_details.cached_tokens`
- Chat Completions: `usage.prompt_tokens_details.cached_tokens`
- `cached_tokens / input_tokens` for Responses or `cached_tokens / prompt_tokens` for Chat Completions
- model, API surface, `prompt_cache_key`, `prompt_cache_retention`, prompt version, tool hash, schema hash
- route family or workload bucket that maps to the prefix/key combination
- approximate request rate per prefix/key combination
- TTFT or prefill latency by route
- ZDR, Data Residency, and Regional Inference posture when extended retention is used

Alert on cache ratio drops after prompt, SDK, model, tool, schema, retention, or routing changes.
