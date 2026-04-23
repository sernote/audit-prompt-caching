# Azure OpenAI Prompt Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- supported Azure OpenAI models and deployment types
- minimum cacheable token count and cache increment size
- cache lifetime and inactivity behavior
- usage field names by API surface
- routing behavior and whether `user` or other parameters influence cache affinity
- image, tool, and structured-output caching semantics

Official sources:
- Azure OpenAI prompt caching: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/prompt-caching
- Azure OpenAI docs: https://learn.microsoft.com/en-us/azure/ai-services/openai/
- Azure OpenAI pricing: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/

## Stable Mechanics

Azure OpenAI prompt caching is similar in shape to OpenAI prompt caching but must be treated as a separate provider surface. Do not assume every OpenAI public API parameter or retention feature exists in Azure.

As of the last review, Azure docs say prompt caching requires a minimum prompt length and identical early prompt content, and that caches are temporary. Verify current thresholds and lifetime before repeating exact numbers.

## Provider Checks

### Threshold And Early Prefix

If repeated prompts show `cached_tokens = 0`, first check whether the prompt reaches the current Azure cacheable threshold and whether the early prefix is identical. Azure docs explicitly emphasize early-prefix identity; do not debug routing before ruling out prefix mismatch.

### Cache Lifetime

Azure prompt caches are temporary and tied to recent use. Compare the user's repeated-request cadence with current Azure retention docs. A daily or sparse repeat may be a cold-cache workload even with a stable prompt.

### Routing Affinity

Check current docs for how Azure routes cacheable requests. If the project uses the `user` parameter or any affinity-like field, verify whether it groups true shared prefixes without over-fragmenting by request/session/user.

### Tools, Images, And Schemas

Treat tool definitions, structured outputs, and image representation as part of the cacheable input unless current docs say otherwise. Keep ordering, JSON serialization, `detail`, URL/base64 representation, and signed URL query strings stable.

### Azure Is Not Generic OpenAI

Do not recommend `prompt_cache_key`, extended retention, or OpenAI-only parameters on Azure unless current Azure docs support them. If the code uses the OpenAI SDK with an Azure endpoint, load this reference rather than only `openai.md`.

## Diagnostics

Inspect usage metadata for cached-token fields exposed by the selected API surface. For Chat Completions style responses:

```python
usage = response.usage
details = getattr(usage, "prompt_tokens_details", None)
cached = getattr(details, "cached_tokens", 0) if details else 0
total = getattr(usage, "prompt_tokens", 0)
ratio = cached / total if total else 0
```

If `cached == 0` for repeated prompts:
- prompt below current cacheable threshold
- first cacheable prefix differs
- tools/schema/image representation differs
- cache lifetime expired between calls
- route or affinity field fragmented reuse
- unsupported model/deployment/API surface

## Monitoring

Track:
- cached tokens and total prompt tokens
- prompt version, tool hash, schema hash, image representation hash
- Azure deployment, region, model, API version
- affinity parameter cardinality, if used
- request cadence vs documented cache lifetime
