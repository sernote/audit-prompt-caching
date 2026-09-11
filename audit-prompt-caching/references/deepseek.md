# DeepSeek Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

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
- Responses API: https://api-docs.deepseek.com/guides/responses_api/
- Anthropic-compatible API: https://api-docs.deepseek.com/guides/anthropic_api/
- Thinking mode: https://api-docs.deepseek.com/guides/thinking_mode/
- Changelog: https://api-docs.deepseek.com/updates/

## Stable Mechanics

DeepSeek API exposes automatic context caching. No request-body opt-in is needed for the managed API.

The official docs describe disk-backed context caching, prefix matching, cache hit/miss usage fields, and best-effort behavior. Do not describe cache hits as guaranteed.

The older "64 tokens as a storage unit" rule is no longer in the guide. Under Sliding Window Attention each cached prefix is an independent unit that must match completely; units are persisted at the end of user input and model output, by common-prefix detection, and at unstated fixed token intervals for long inputs. Retention is still "a few hours to a few days", best-effort.

DeepSeek documents prefix-oriented cache persistence. In its SWA scenario, the first two closely related document requests can be misses while the third reuses an established prefix unit. Do not classify a two-request sample as a permanent miss: run a sequential warm-up/control experiment and compare cache telemetry across at least three ordered requests.

Current aliases at the last review are `deepseek-flash` (V4.1-Flash) and `deepseek-v4-pro`; `deepseek-chat` and `deepseek-reasoner` were discontinued on 2026-07-24, and retired names such as `deepseek-v4-flash` are silently served by the current Flash model. Pricing has peak/off-peak tiers (off-peak is half) with separate cache-hit and cache-miss prices, so a hit ratio alone does not give the bill; join usage with request time. Official pages disagree about `deepseek-v4-pro` routing after 2026-09-14; re-check before attributing a cache change to a model swap.

## Provider Checks

### OpenAI-Compatible Does Not Mean OpenAI-Identical

Many projects call DeepSeek through the OpenAI SDK with a custom `base_url`. Do not assume OpenAI thresholds, fields, TTL, or `prompt_cache_key` behavior apply: the Responses guide says `prompt_cache_key` and `prompt_cache_retention` are not supported and unsupported parameters are silently ignored.

### API Surfaces

- Chat Completions: `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens` (required, hit + miss = `prompt_tokens`) plus `prompt_tokens_details.cached_tokens` as an alias of the hit count and `completion_tokens_details.reasoning_tokens`. Streaming usage arrives only on the last chunk with `stream_options.include_usage`.
- Responses API (stateless: `previous_response_id`, `conversation`, and `store` unsupported): `usage.input_tokens_details.cached_tokens` only, with no miss counter, so the denominator is `input_tokens`.
- Anthropic-compatible `https://api.deepseek.com/anthropic`: `cache_control` is documented as ignored on text, tools, `tool_use`, and `tool_result`; caching stays automatic, and the guide does not document the returned cache usage fields. Treat `cache_read_input_tokens`/`cache_creation_input_tokens` on this route as unverified until captured.

### Thinking Mode And Tools

Thinking is on by default (`reasoning_effort` low/high/max, `none` disables). Without `tools`, prior `reasoning_content` is ignored server-side; with `tools`, all prior `reasoning_content` must be passed back and is concatenated into the context. In tool-using agents, stripping or editing earlier reasoning therefore changes the served prefix; audit reasoning round-tripping together with tool/schema stability. Changing effort or thinking type between turns is a prefix change too.

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

If fields are missing, check SDK version, API mode (Chat vs Responses vs Anthropic-compatible), streaming usage options, and current DeepSeek API docs. Do not add `cached_tokens` to `prompt_cache_hit_tokens`; they are the same count.

## Monitoring

Track:
- `prompt_cache_hit_tokens` / `prompt_tokens_details.cached_tokens` (same count)
- `prompt_cache_miss_tokens` (Chat only; Responses has no miss counter)
- request time vs peak/off-peak window, served model alias
- hit ratio by prompt family
- TTFT by prompt length
- model alias and backend fingerprint when available

Alert on sudden miss-token spikes after prompt, SDK, schema, or model alias changes.
