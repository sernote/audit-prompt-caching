# OpenAI Prefix Cache Reference

Last reviewed: 2026-09-22 against the live provider guides. Verify official docs before exact claims about model support, prices, thresholds, `prompt_cache_key`, cache controls, `configuration_update`, usage fields, ZDR, Data Residency, Regional Inference, tools, images, or structured outputs.

Official sources:
- Prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching
- Cache diagnostics: https://developers.openai.com/api/docs/guides/prompt-caching/diagnostics
- GPT-6 Sol model and current prices: https://developers.openai.com/api/docs/models/gpt-6-sol
- GPT-6 Sol launch and caching note: https://openai.com/index/introducing-gpt-6-sol-and-luna/
- GPT-5.6 guidance: https://developers.openai.com/api/docs/guides/latest-model
- GPT-6 Astra guide: https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md
- Reasoning guide (change reasoning mid-conversation): https://developers.openai.com/api/docs/guides/reasoning#change-reasoning-mid-conversation
- Models: https://developers.openai.com/api/docs/models/all
- Data controls: https://developers.openai.com/api/docs/guides/your-data
- API reference: https://developers.openai.com/api/docs/api-reference
- Tool/function calling: https://developers.openai.com/api/docs/guides/function-calling
- Tool search: https://developers.openai.com/api/docs/guides/tools-tool-search
- API changelog: https://developers.openai.com/api/docs/changelog
- Organization Usage API completions: https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions
- Pricing: https://openai.com/api/pricing/

Dashboard and Organization Usage API section reviewed: 2026-08-23.

## Mechanics

OpenAI prompt caching is automatic on supported recent models. Cache hits need exact reusable prefixes; put stable instructions, examples, tools, schemas, images, and documents before dynamic user/request data. Caching starts only when the current model/API surface meets the minimum prompt length, commonly 1024 tokens in the docs current at review time. For GPT-5.6 and later that 1,024-token minimum is documented as strict; on GPT-5.5 and earlier it varies by model between roughly 1,024 and 2,048, so prompts just over 1,024 may cache inconsistently there.

Important current behaviors to verify:
- The initial prefix hash participates in routing. OpenAI documents first-prefix affinity; this reference keeps the phrase prefix hash for audits.
- On models before GPT-5.6, `prompt_cache_key` helps cache routing; on GPT-5.6+ it is optional for separate cache accounting and cross-user hit-probing isolation, not a prefix-stability fix.
- Very hot key traffic can overflow locality on earlier models; the guide discusses an approximate 15 requests per minute envelope across all prefixes for each `prompt_cache_key`. Cache state lives on individual machines, so model, region, load, and expiry matter too.
- `prompt_cache_retention` values include `in_memory` and `"24h"` on supported surfaces.
- For `gpt-5.5` and `gpt-5.5-pro`, current docs make `"24h"` the default and do not support `in_memory`; GPT-5.6 uses the separate contract below.
- Cached prompt tokens still count toward TPM rate limits.
- Extended retention is compatible with Zero Data Retention in the documented posture, but other ZDR constraints such as `store=True` still matter.
- In-memory retention keeps data in memory; extended retention can use GPU-local storage.

## GPT-5.6 Contract Snapshot

Direct GPT-5.6 models add paid writes and optional explicit cache boundaries:

- `prompt_cache_options.mode` is `implicit` (the default) or `explicit`; the only currently documented TTL is `"30m"`.
- An explicit boundary is attached to a supported input content block as `"prompt_cache_breakpoint": {"mode": "explicit"}`. In implicit mode OpenAI also considers the latest message; explicit mode writes only marked prefixes. Explicit mode with no marker is cache-disabled rather than an API syntax error, but the linter reports it because it is commonly accidental.
- **`prompt_cache_key` is optional on GPT-5.6+.** Use it for separate customer/user accounting or hit-probing isolation. OpenAI routes automatically; diagnose low `cached_tokens` from prefix, breakpoint, region, and cadence first. The 15 requests-per-minute key guidance is for earlier models.
- **Implicit mode can reuse earlier message boundaries.** The guide checks the implicit point, up to 20 earlier eligible message endings, and the initial developer-message block. Explicit-only mode checks marked points. A volatile suffix can still cause low-value writes; measure before switching modes.
- Each request creates at most four writes; implicit mode consumes one slot. The cache guide says the first 2 and latest 50 explicit markers are read candidates, while create references mention 80. Check the target API before relying on a lookback count.
- `prompt_cache_retention` is the older automatic-cache contract and is deprecated for GPT-5.6; `ttl: "30m"` is a minimum reuse lifetime, not a maximum retention guarantee.
- Cache writes are billed separately; at review time the model guide states 1.25x the uncached input rate. Supply current prices to the ROI helper rather than copying that multiplier into code.

## GPT-6 Astra Contract Snapshot

`gpt-6-astra` (family alias `gpt-6`; verify routing) uses the GPT-5.6+ cache contract, including optional keys, `prompt_cache_options`, explicit markers, and paid writes. Replace legacy `prompt_cache_retention` with `prompt_cache_options.ttl: "30m"`. The official model page lists $10/$1/$12.50/$50 per MTok (ordinary/read/write/output) below 272K input tokens; a long-context tier applies above it.

For GPT-6 standard single-agent conversations, keep request-level `reasoning.effort` constant and insert `{"type":"configuration_update","reasoning":{"effort":"high"}}` before the next user turn. It preserves earlier context; pro mode rejects it. `reasoning.context` changes can also alter the prefix. GPT-6 Astra does not support effort `none`; check the effective effort when migrating. `layout_linter.py` reports incompatible updates as AP-15. Use `prompt_cache_options.comparison_response_id` for diagnostics, then usage fields for actual reads.

## GPT-6 Sol Snapshot

`gpt-6-sol` uses the GPT-5.6+ contract. Current prices per MTok: $2 ordinary input, $0.20 read, $2.50 write, $10 output. Its minimum is 1,024 visible tokens; `cached_tokens` reports the exact eligible boundary. `"30m"` is the only documented TTL and refreshes on reuse.

In standard single-agent Responses, keep request-level effort constant and append `configuration_update` for changes. Keep tools stable; use supported `allowed_tools`, `tool_choice: "none"`, deferred search, or append-only `additional_tools` (no explicit marker there). `prompt_cache_options.prewarm: true` prepares a prefix without output but bills a write; verify the later read.

For Responses, read `cached_tokens` and `cache_write_tokens` under `usage.input_tokens_details`; for Chat Completions, use `usage.prompt_tokens_details`. Both are breakdowns of the reported input total, so do not add them to `input_tokens` or `prompt_tokens`.

Keep data-control layers separate. Cache entries are organization-scoped. ZDR, response storage, cache application state, and Regional Inference have different contracts; encrypted GPU-local storage is not a Regional processing guarantee. Re-check the data-controls guide before making a residency or ZDR claim.

## Audit Checklist

- Detect Responses vs Chat Completions and wrapper layers before choosing usage fields.
- Apply GPT-5.6 controls only to confirmed direct OpenAI routes; an OpenAI-compatible wrapper is not proof of support.
- On pre-GPT-5.6 models, keep `prompt_cache_key` stable at route or prompt-family granularity; avoid per-request keys and over-broad hot keys. On GPT-5.6+, use keys for accounting or isolation only when needed.
- Check whether `reasoning.effort` (or Chat `reasoning_effort`) varies between requests of one conversation; on GPT-6 standard single-agent mode expect `configuration_update` items instead, elsewhere expect a constant level (AP-15).
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

For GPT-5.6+ supported Responses requests, `prompt_cache_options.comparison_response_id` requests a comparison with an earlier completed response from the same organization; it does not load that conversation or force a cache hit. Use the diagnostic reason to locate a changed component, then `usage` to confirm actual read/write tokens. If `cached_tokens == 0`, check prefix drift, prompt length, tools/schema drift, image drift, breakpoint mode/placement, region, cadence, a request-level `reasoning.effort` or `reasoning.context` change, wrapper routing, or model/API changes. On earlier models, also check key/retention and hot-key routing. If cached tokens are high but savings are low, check output-token share, decode/final latency, TPM rate limits, and traffic cadence.

## Prompt Caching dashboard and aggregate evidence

The Dashboard UI shows cache-hit trends and reads per write. It is a
`provider_dashboard_aggregate`, useful for corroboration but not causal proof:
its public formula, denominator, weighting, and route scope are unspecified.
Record `evidence_definition_status=unknown`,
`evidence_denominator_status=unknown`, and
`evidence_accounting_semantics=unknown` for this UI.

The documented OpenAI Organization Usage API is a separate
`provider_usage_api_aggregate`. Record bucket boundaries, filters, and groups.
`input_tokens` is inclusive of cache reads and writes; `input_cached_tokens`
counts reads; `input_cache_write_tokens` counts writes; `input_uncached_tokens`
is uncached input excluding cache-write tokens, neither cache reads nor writes.
The OpenAI prompt-caching guide documents a request-level read/write/neither partition;
do not add breakdowns onto inclusive `input_tokens`, or infer a residual from
missing fields or mismatched bucket/group/filter scope.

For the documented OpenAI Organization Usage API, set `evidence_definition_status=provider_documented`,
`evidence_denominator_status=unknown` unless the provider documents the denominator,
and `evidence_accounting_semantics=provider_defined`. This documented mixed decomposition
is not permission to sum fields. Optional or missing fields stay absent/unknown;
never replace them with zero. An auditor-defined ratio needs scope proof.
No same formula is assumed across Dashboard and Usage API; the Dashboard
denominator is not inferred from Usage API fields. Keep request-level
`cached_tokens`/`cache_write_tokens`, prefix hashes, and route evidence for a causal finding.
