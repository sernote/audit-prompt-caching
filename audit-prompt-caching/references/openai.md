# OpenAI Prefix Cache Reference

Last reviewed: 2026-04-27. Verify official docs before exact claims about model support, prices, thresholds, `prompt_cache_key`, `prompt_cache_retention`, usage fields, ZDR, Data Residency, Regional Inference, tools, images, or structured outputs.

Official sources:
- Prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching
- API reference: https://developers.openai.com/api/docs/api-reference
- Tool/function calling: https://developers.openai.com/api/docs/guides/function-calling
- Tool search: https://developers.openai.com/api/docs/guides/tools-tool-search
- Pricing: https://openai.com/api/pricing/

## Mechanics

OpenAI prompt caching is automatic on supported recent models. Cache hits need exact reusable prefixes; put stable instructions, examples, tools, schemas, images, and documents before dynamic user/request data. Caching starts only when the current model/API surface meets the minimum prompt length, commonly 1024 tokens in the docs current at review time.

Important current behaviors to verify:
- The initial prefix hash participates in routing. OpenAI documents first-prefix affinity; this reference keeps the phrase prefix hash for audits.
- `prompt_cache_key` is a routing-locality hint, not a privacy boundary or prefix-stability fix.
- Very hot identical prefix/key traffic can overflow locality; current docs discussed an approximate 15 requests per minute envelope.
- `prompt_cache_retention` values include `in_memory` and `"24h"` on supported surfaces.
- For `gpt-5.5`, `gpt-5.5-pro`, and future models, current docs make `"24h"` the default and do not support `in_memory`.
- Cached prompt tokens still count toward TPM rate limits.
- Extended retention is compatible with Zero Data Retention in the documented posture, but other ZDR constraints such as `store=True` still matter.
- In-memory retention keeps data in memory; extended retention can use GPU-local storage.

## Audit Checklist

- Detect Responses vs Chat Completions and wrapper layers before choosing usage fields.
- Keep `prompt_cache_key` stable at route or prompt-family granularity; avoid per-request keys and over-broad hot keys.
- Remove request IDs, timestamps, tenant IDs, and per-request constants from tools, JSON schema, and `response_format`.
- Sort tools and schema serialization where app code controls order.
- Keep image representation and `detail` stable.
- Bucket metrics by model, API surface, `prompt_cache_key`, `prompt_cache_retention`, prompt version, tool hash, schema hash, and route family.

## Diagnostics

Responses API:

```python
cached = response.usage.input_tokens_details.cached_tokens
total = response.usage.input_tokens
```

Chat Completions:

```python
cached = completion.usage.prompt_tokens_details.cached_tokens
total = completion.usage.prompt_tokens
```

If `cached_tokens == 0`, check prefix drift, prompt length, tools/schema drift, image drift, inconsistent key/retention, wrapper routing, model/API changes, or a hot prefix/key. If cached tokens are high but savings are low, check output-token share, decode/final latency, TPM rate limits, and traffic cadence.
