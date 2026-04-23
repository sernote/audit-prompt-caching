# DeepSeek Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- current model aliases and context limits
- cache hit/miss prices
- cache storage unit size
- cache retention language
- usage field names
- compatibility of self-hosted DeepSeek models with vLLM/SGLang prefix caching

Official sources:
- Context caching guide: https://api-docs.deepseek.com/guides/kv_cache/
- Create Chat Completion API: https://api-docs.deepseek.com/api/create-chat-completion
- Models and pricing: https://api-docs.deepseek.com/quick_start/pricing
- Token usage: https://api-docs.deepseek.com/quick_start/token_usage

## Stable Mechanics

DeepSeek API exposes automatic context caching. No request-body opt-in is needed for the managed API.

The official docs describe disk-backed context caching, prefix matching, cache hit/miss usage fields, and best-effort behavior. Do not describe cache hits as guaranteed.

As of the last review, the docs say the cache uses 64 tokens as a storage unit and content below that unit is not cached. Verify before repeating this number.

## Provider Checks

### OpenAI-Compatible Does Not Mean OpenAI-Identical

Many projects call DeepSeek through the OpenAI SDK with a custom `base_url`. Do not assume OpenAI thresholds, fields, TTL, or `prompt_cache_key` behavior apply.

### Prefix Stability Still Matters

Even though caching is automatic, all universal anti-patterns still apply:
- timestamps/user data in prefix
- dynamic tools/schema
- history mutation
- route fragmentation when self-hosted

### Managed Vs Self-Hosted

For managed DeepSeek API, use DeepSeek docs. For self-hosted DeepSeek-family models on vLLM/SGLang, use the inference-engine reference too.

### MLA And Engine Compatibility

DeepSeek-family MLA models can have engine-specific cache behavior. Check the exact vLLM/SGLang version and model support notes before recommending prefix-cache features.

## Diagnostics

Inspect:

```python
usage = response.usage
hit = usage.prompt_cache_hit_tokens
miss = usage.prompt_cache_miss_tokens
total = hit + miss
ratio = hit / total if total else 0
```

If fields are missing, check SDK version, API mode, streaming usage options, and current DeepSeek API docs.

## Monitoring

Track:
- `prompt_cache_hit_tokens`
- `prompt_cache_miss_tokens`
- hit ratio by prompt family
- TTFT by prompt length
- model alias and backend fingerprint when available

Alert on sudden miss-token spikes after prompt, SDK, schema, or model alias changes.
