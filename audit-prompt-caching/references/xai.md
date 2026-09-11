# xAI Grok Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- which Grok models cache (docs say all `grok` language models)
- cached-input price per model and the long-context threshold that doubles rates
- usage field names per surface (Chat Completions, Responses, gRPC)
- routing-affinity header/parameter names
- cache field behavior on the Anthropic-compatible Messages route

Official sources:
- Prompt caching: https://docs.x.ai/developers/advanced-api-usage/prompt-caching
- Usage and pricing for cached tokens: https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing
- Maximizing cache hits: https://docs.x.ai/developers/advanced-api-usage/prompt-caching/maximizing-cache-hits
- Pricing: https://docs.x.ai/developers/pricing

## Stable Mechanics

xAI caching is **automatic**: consecutive requests sharing the same starting messages are cached, with no opt-in, no documented minimum token count, and no TTL ("entries can be evicted at any time due to server load or restarts"). Prefix stability and request cadence are the levers; there is no explicit cache object.

Routing affinity is explicit: header `x-grok-conv-id` on Chat Completions (gRPC metadata too) or `prompt_cache_key` on Responses, which the chat reference describes as plumbed to `x-grok-conv-id`. Use a stable, non-secret grouping value per shared prefix family; do not mint one per request.

## Provider Checks

- Fields: Chat Completions `usage.prompt_tokens_details.cached_tokens`; Responses `usage.input_tokens_details.cached_tokens`; gRPC `usage.cached_prompt_text_tokens`. All are inclusive subsets of the prompt total; label records `provider: xai` for `analyze_usage_logs.py`.
- Reasoning models: the multi-turn guide names omitting prior `reasoning_content` as the top cause of cache misses. Audit reasoning round-tripping with the prefix.
- Long context doubles every rate, including cached input, once total prompt tokens **including cached tokens** cross the model's threshold (200k at the last review). A hit does not protect against the tier switch.
- Cached-input multipliers are model-specific (about 0.16x-0.25x of input at the last review); OpenRouter publishes a flat 0.25x for Grok and Bedrock-hosted Grok lists `input_cache_write: 0`. Use the vendor row.
- The Anthropic-compatible Messages route is advertised but its cache usage fields are not documented; treat `cache_read_input_tokens` there as unverified until captured.

## Diagnostics

Compare `cached_tokens` across consecutive calls with identical opening messages, then check `x-grok-conv-id`/`prompt_cache_key` cardinality, reasoning round-tripping, idle gaps (eviction is undocumented), model swaps, and the long-context threshold when cost does not fall with hits.

## Monitoring

Track cached tokens by model and surface, affinity key cardinality, prompt tokens vs long-context threshold, reasoning policy, and prompt/tool/schema hash. Alert on drops after model or affinity changes.
