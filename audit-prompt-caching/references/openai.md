# OpenAI Prefix Cache Reference

Last reviewed: 2026-07-20. Verify official docs before exact claims about model support, prices, thresholds, `prompt_cache_key`, cache controls, usage fields, ZDR, Data Residency, Regional Inference, tools, images, or structured outputs.

Official sources:
- Prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching
- GPT-5.6 guidance: https://developers.openai.com/api/docs/guides/latest-model
- Models: https://developers.openai.com/api/docs/models/all
- Data controls: https://developers.openai.com/api/docs/guides/your-data
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
- For `gpt-5.5` and `gpt-5.5-pro`, current docs make `"24h"` the default and do not support `in_memory`; GPT-5.6 uses the separate contract below.
- Cached prompt tokens still count toward TPM rate limits.
- Extended retention is compatible with Zero Data Retention in the documented posture, but other ZDR constraints such as `store=True` still matter.
- In-memory retention keeps data in memory; extended retention can use GPU-local storage.

## GPT-5.6 Contract Snapshot

Direct GPT-5.6 models add paid writes and optional explicit cache boundaries:

- `prompt_cache_options.mode` is `implicit` (the default) or `explicit`; the only currently documented TTL is `"30m"`.
- An explicit boundary is attached to a supported input content block as `"prompt_cache_breakpoint": {"mode": "explicit"}`. In implicit mode OpenAI also considers the latest message; explicit mode writes only marked prefixes. Explicit mode with no marker is cache-disabled rather than an API syntax error, but the linter reports it because it is commonly accidental.
- OpenAI creates at most four new writes per request. Do not turn that write budget into a hard marker-count or read-lookback limit: earlier markers can remain read candidates, and the published read-limit wording has changed across documentation surfaces.
- `prompt_cache_retention` is the older automatic-cache contract and is deprecated for GPT-5.6; `ttl: "30m"` is a minimum reuse lifetime, not a maximum retention guarantee.
- Cache writes are billed separately; at review time the model guide states 1.25x the uncached input rate. Supply current prices to the ROI helper rather than copying that multiplier into code.

For Responses, read `cached_tokens` and `cache_write_tokens` under `usage.input_tokens_details`; for Chat Completions, use `usage.prompt_tokens_details`. Both are breakdowns of the reported input total, so do not add them to `input_tokens` or `prompt_tokens`.

Keep data-control layers separate. Cache entries are organization-scoped. ZDR, response storage, cache application state, and Regional Inference have different contracts; encrypted GPU-local storage is not a Regional processing guarantee. Re-check the data-controls guide before making a residency or ZDR claim.

## Audit Checklist

- Detect Responses vs Chat Completions and wrapper layers before choosing usage fields.
- Apply GPT-5.6 controls only to confirmed direct OpenAI routes; an OpenAI-compatible wrapper is not proof of support.
- Keep `prompt_cache_key` stable at route or prompt-family granularity; avoid per-request keys and over-broad hot keys.
- Remove request IDs, timestamps, tenant IDs, and per-request constants from tools, JSON schema, and `response_format`.
- Sort tools and schema serialization where app code controls order.
- Keep image representation and `detail` stable.
- Bucket metrics by model, API surface, `prompt_cache_key`, `prompt_cache_retention`, prompt version, tool hash, schema hash, and route family.

## Diagnostics

Responses API:

```python
cached = response.usage.input_tokens_details.cached_tokens
written = response.usage.input_tokens_details.cache_write_tokens
total = response.usage.input_tokens
```

Chat Completions:

```python
cached = completion.usage.prompt_tokens_details.cached_tokens
written = completion.usage.prompt_tokens_details.cache_write_tokens
total = completion.usage.prompt_tokens
```

If `cached_tokens == 0`, check prefix drift, prompt length, tools/schema drift, image drift, inconsistent key/retention, wrapper routing, model/API changes, or a hot prefix/key. If cached tokens are high but savings are low, check output-token share, decode/final latency, TPM rate limits, and traffic cadence.
