# Azure OpenAI Prompt Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- supported Azure OpenAI models and deployment types
- minimum cacheable token count and cache increment size
- cache lifetime and inactivity behavior
- usage field names by API surface
- routing behavior and whether `user` or other parameters influence cache affinity
- image, tool, and structured-output caching semantics

Official sources:
- Azure OpenAI prompt caching (canonical Foundry path; the old `ai-services/openai` path redirects here): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching
- Azure OpenAI docs: https://learn.microsoft.com/en-us/azure/foundry/openai/
- Azure OpenAI pricing: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/

## Stable Mechanics

Azure OpenAI prompt caching is similar in shape to OpenAI prompt caching but must be treated as a separate provider surface. Do not assume every OpenAI public API parameter or retention feature exists in Azure.

As of the last review, Azure docs say prompt caching requires a minimum prompt length (1,024 tokens) and identical early prompt content, and that in-memory caches typically clear after 5 to 10 minutes of inactivity and always within one hour. Verify current thresholds and lifetime before repeating exact numbers.

Behavior is gated by model family and deployment type, so record both before any exact claim:
- GPT-5.5 and earlier: implicit caching only, no cache-write charge, cache hits after the first 1,024 tokens land in 128-token increments; `prompt_cache_retention` (`in_memory` or `24h`) is documented for gpt-4.1 and gpt-5 through gpt-5.5, with `24h` the default on gpt-5.5.
- GPT-5.6 and later (including GPT-6): explicit breakpoints via `prompt_cache_options` and `prompt_cache_breakpoint` on Responses and Chat Completions, a separate `cache_write_tokens` usage field, paid cache writes, no 128-token rounding, and `prompt_cache_retention` deprecated. Pre-5.6 models return `400` for these parameters.
- Provisioned (PTU-M) deployments support caching but not breakpoints or `cache_write_tokens`; cached tokens do not consume PTU capacity.

## Provider Checks

### Threshold And Early Prefix

If repeated prompts show `cached_tokens = 0`, first check whether the prompt reaches the current Azure cacheable threshold and whether the early prefix is identical. Azure docs explicitly emphasize early-prefix identity; do not debug routing before ruling out prefix mismatch.

### Cache Lifetime

Azure prompt caches are temporary and tied to recent use. Compare the user's repeated-request cadence with current Azure retention docs. A daily or sparse repeat may be a cold-cache workload even with a stable prompt.

### `prompt_cache_key` And Routing Affinity

For GPT-5.6, Azure documents `prompt_cache_key` as the affinity key for reliable matching. Use a stable, non-secret key for requests that may safely share a prefix; do not create a per-request key or embed a raw user/session identifier. Hash or HMAC an appropriate grouping value when isolation is needed.

Azure documents a rate cap: above roughly 15 requests per minute for one prefix plus `prompt_cache_key` pair, some requests may miss. Distribute high-volume traffic across several keys with a stable key-to-prefix mapping instead of one global key.

### GPT-5.6+ Breakpoints And Paid Writes

On Standard GPT-5.6+ deployments, `prompt_cache_options.mode` is `implicit` (default: automatic breakpoint on the latest message plus any explicit ones) or `explicit` (only marked blocks; with no marks the request neither caches nor pays writes, which is also the documented way to disable caching). `prompt_cache_options.ttl` accepts only `30m` and does not select the retention tier. `prompt_cache_breakpoint: {"mode": "explicit"}` goes on `input_text`/`input_image`/`input_file` (Responses) or `text`/`image_url`/`input_audio`/`file` (Chat) blocks. Each request can create up to four new writes (three explicit in implicit mode), reads consider up to the latest 50 breakpoints, and earlier-turn breakpoints are read-only.

Cache writes on GPT-5.6+ are billed in addition to discounted reads (published launch tables show writes at about 1.25x input and reads at about 0.1x); treat those multipliers as pricing-page facts to re-verify, not constants. Do not send these parameters to pre-5.6 models or PTU-M deployments.

### Tools, Images, And Schemas

Treat tool definitions, structured outputs, and image representation as part of the cacheable input unless current docs say otherwise. Keep ordering, JSON serialization, `detail`, URL/base64 representation, and signed URL query strings stable.

## Responses endpoint capability gate

Section reviewed: 2026-08-23.

The Responses endpoint is a separate Azure deployment surface. Before considering
`allowed_tools`, load current Azure docs and record the endpoint, deployment/model,
and `api-version`. Verify the exact API version's Responses `tool_choice` schema
and final request wire. Do not infer support from direct OpenAI or Vercel SDK
behavior; make no universal Azure support claim.

## Azure Is Not Generic OpenAI

Gate `prompt_cache_key`, `prompt_cache_retention`, `prompt_cache_options`, and `prompt_cache_breakpoint` on the deployed model family, deployment type, and current Azure docs rather than on OpenAI behavior. The Responses REST reference lags the how-to (it lists `prompt_cache_key`/`prompt_cache_retention` but not the GPT-5.6 parameters or `cache_write_tokens`), and community reports of `cached_tokens=0` on `/openai/v1/responses` while Chat Completions hit exist; verify the surface with a wire capture. If the code uses the OpenAI SDK with an Azure endpoint, load this reference rather than only `openai.md`. Non-OpenAI Foundry Models have no documented prompt caching.

## Diagnostics

Inspect usage metadata for cached-token fields exposed by the selected API surface. For Chat Completions style responses:

```python
usage = response.usage
details = getattr(usage, "prompt_tokens_details", None)
cached = getattr(details, "cached_tokens", 0) if details else 0
total = getattr(usage, "prompt_tokens", 0)
ratio = cached / total if total else 0
```

For Responses, read `usage.input_tokens_details.cached_tokens` instead. On Standard GPT-5.6+ deployments also read `cache_write_tokens` in the same details object; `cached_tokens` and `cache_write_tokens` are inclusive subsets of the prompt total, so use the existing OpenAI-shape adapter rather than adding them to the input count. Pre-5.6 models and PTU-M expose no write field: do not infer write volume from `cached_tokens`; record the first request in a prefix cohort as an expected cold write and use billing/export data when exact write cost is required.

If `cached == 0` for repeated prompts:
- prompt below current cacheable threshold
- first cacheable prefix differs
- tools/schema/image representation differs
- cache lifetime expired between calls
- route or affinity field fragmented reuse, or more than ~15 RPM on one prefix+key pair
- `prompt_cache_options.mode: explicit` with no marked blocks (caching disabled by design)
- unsupported model/deployment/API surface (PTU-M or pre-5.6 model with GPT-5.6 parameters)

## Monitoring

Track:
- cached tokens and total prompt tokens
- prompt version, tool hash, schema hash, image representation hash
- Azure deployment type (Standard vs PTU-M), region, model family, API version
- `cache_write_tokens` per prefix cohort on GPT-5.6+
- affinity parameter cardinality, if used
- request cadence vs documented cache lifetime
